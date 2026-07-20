"""JavaScript Data Flow Graph (DFG) via Reaching Definitions Analysis."""

import copy
from collections import defaultdict

import networkx as nx

from utils import DFG_utils
from utils.js_nodes import statement_types

# ---- JS-specific AST type lists --------------------------------------------

assignment = ["assignment_expression"]
def_statement = ["variable_declarator"]
increment_statement = ["update_expression", "augmented_assignment_expression"]
variable_type = ["identifier", "this", "super"]
method_calls = ["call_expression", "new_expression"]

# AST nodes that constitute a variable definition
_DEF_PARENT_TYPES = def_statement + ["formal_parameters"]

# AST nodes we walk *through* when determining def/use context
# (destructuring patterns, pairs in destructuring, shorthand properties)
_WALK_THROUGH_TYPES = frozenset([
    "object_pattern",
    "array_pattern",
    "shorthand_property_identifier",
])

# Parent types under which *all* children are USEs (fast path)
_USE_PARENT_TYPES = frozenset([
    "return_statement",
    "throw_statement",
    "yield_expression",
    "await_expression",
    "template_substitution",
    "spread_element",
    "computed_property_name",
    "subscript_expression",
    "member_expression",
    "binary_expression",
    "ternary_expression",
    "unary_expression",
    "arguments",
    "new_expression",
    "call_expression",
    "sequence_expression",
    "switch_statement",
    "while_statement",
    "do_statement",
    "parenthesized_expression",
])


# ---- helpers ---------------------------------------------------------------


def _st(node):
    """Safe text decode."""
    if node is None:
        return ""
    return node.text.decode("utf-8")


def _get_index(parser, node):
    """Look up the CFG integer id for an AST node (by position + type)."""
    return parser.index.get((node.start_point, node.end_point, node.type))


def _traverse_variables(node, parser, callback):
    """Walk *node* and call *callback(node, parser)* for every identifier/this/super."""
    if node.is_named and node.type in variable_type:
        callback(node, parser)
    for child in node.children:
        _traverse_variables(child, parser, callback)


def _return_first_parent_of_types(node, parent_types):
    """Walk ancestors until a node whose ``.type`` is in *parent_types*."""
    while node is not None:
        if node.type in parent_types:
            return node
        node = node.parent
    return None


def _find_enclosing_function(node):
    """Walk ancestors until a function_declaration / arrow_function / function_expression."""
    while node is not None:
        if node.type in (
            "function_declaration", "arrow_function", "function_expression",
            "method_definition", "generator_function_declaration",
        ):
            return node
        node = node.parent
    return None


# ---- identifier classification ---------------------------------------------


def _classify_identifier(node):
    """Classify an identifier/this/super as (is_def, is_use) by walking ancestors.

    Returns ``(is_def, is_use)`` -- both may be True for increment operators.
    """
    current = node

    while current is not None:
        parent = current.parent
        if parent is None:
            return (False, True)

        pt = parent.type

        # ── Direct DEF contexts ─────────────────────────────────────────
        if pt == "formal_parameters":
            return (True, False)

        if pt == "variable_declarator":
            # Only the ``name`` child is a definition; the ``value`` child is a use
            if parent.child_by_field_name("name") == current:
                return (True, False)
            return (False, True)

        if pt == "catch_clause":
            if parent.child_by_field_name("parameter") == current:
                return (True, False)
            return (False, True)

        if pt in ("for_in_statement", "for_of_statement"):
            if parent.child_by_field_name("left") == current:
                return (True, False)
            return (False, True)

        if pt == "assignment_expression":
            if parent.child_by_field_name("left") == current:
                return (True, False)
            return (False, True)

        # ── Function / class / method names are definitions ─────────────
        if pt in ("function_declaration", "function_expression",
                  "generator_function_declaration", "class_declaration",
                  "method_definition"):
            if parent.child_by_field_name("name") == current:
                return (True, False)
            return (False, True)

        # ── Both DEF and USE (increment / compound assignment) ──────────
        if pt == "augmented_assignment_expression":
            if parent.child_by_field_name("left") == current:
                return (True, True)
            return (False, True)

        if pt == "update_expression":
            return (True, True)

        # ── Import bindings are defs ────────────────────────────────────
        if pt in ("import_specifier", "namespace_import"):
            # import { x }  or  import * as x
            return (True, False)

        if pt == "import_statement":
            # import x from '...'  -- the default-import identifier is a named child
            # (skip source string children which are not identifiers anyway)
            return (True, False)

        if pt == "import_clause":
            return (True, False)

        # ── Walk-through types (destructuring / patterns) ───────────────
        if pt in _WALK_THROUGH_TYPES:
            current = parent
            continue

        # ── Pair in an object literal / destructuring ───────────────────
        if pt == "pair":
            if parent.child_by_field_name("value") == current:
                # Walk up to see if pair is inside a destructuring pattern
                gp = parent.parent
                while gp is not None:
                    if gp.type in ("object_pattern", "array_pattern"):
                        current = parent  # walk through
                        break
                    if gp.type == "object":
                        return (False, True)  # object literal -- value is a USE
                    gp = gp.parent
                else:
                    return (False, True)
                continue  # walk-through to destructuring parent
            else:
                # property key -- always a USE (reading a property name)
                return (False, True)

        # ── Assignment pattern (x = default_value in destructuring) ─────
        if pt == "assignment_pattern":
            if parent.child_by_field_name("left") == current:
                current = parent  # walk through, the left side is being defined
                continue
            # right side (default value) -- USE
            return (False, True)

        # ── Rest pattern (...rest in destructuring or parameters) ──────
        if pt == "rest_pattern":
            # The rest element is being defined
            current = parent
            continue

        # ── Conditional expression -- condition is a USE ────────────────
        if pt in ("if_statement", "while_statement", "do_statement"):
            if parent.child_by_field_name("condition") == current:
                return (False, True)
            return (False, True)

        # ── for_statement -- initializer may contain declarations ───────
        if pt == "for_statement":
            initializer = parent.child_by_field_name("initializer")
            if initializer is not None and initializer == current:
                # Could be a lexical_declaration or variable_declaration
                # Let normal walking handle it
                return (False, True)
            return (False, True)

        # ── Fast-path USE types ─────────────────────────────────────────
        if pt in _USE_PARENT_TYPES:
            return (False, True)

        # ── Default: treat as USE ───────────────────────────────────────
        return (False, True)

    return (False, True)


# ---- parameter extraction --------------------------------------------------


def _find_parameters(func_node):
    """Extract formal parameter names from a function AST node.

    Handles simple identifiers, object/array destructuring, rest patterns,
    and default values (assignment patterns).
    """
    params = []
    param_list = func_node.child_by_field_name("parameters")
    if param_list is None:
        return params

    def _extract(node, into):
        if node.type == "identifier":
            into.append(_st(node))
        elif node.type == "rest_pattern":
            # ...rest
            for child in node.named_children:
                _extract(child, into)
        elif node.type == "assignment_pattern":
            # x = default_value
            left = node.child_by_field_name("left")
            if left is not None:
                _extract(left, into)
        elif node.type == "object_pattern":
            for child in node.named_children:
                if child.type == "shorthand_property_identifier":
                    for sub in child.named_children:
                        _extract(sub, into)
                elif child.type == "pair":
                    val = child.child_by_field_name("value")
                    if val is not None:
                        _extract(val, into)
                elif child.type == "rest_pattern":
                    _extract(child, into)
                elif child.type == "assignment_pattern":
                    _extract(child, into)
        elif node.type == "array_pattern":
            for child in node.named_children:
                _extract(child, into)
        elif node.type == "spread_element":
            for child in node.named_children:
                _extract(child, into)

    for child in param_list.named_children:
        _extract(child, params)
    return params


# ---- misc helpers ----------------------------------------------------------


def _read_index(index, node):
    """Reverse-lookup: given a node id, find the corresponding index key."""
    for key, val in index.items():
        if val == node:
            return key
    return None


def _is_node_inside_loop(node_id, parser, CFG_results):
    """Check if a CFG node is inside a loop structure."""
    index = parser.index
    node_key = _read_index(index, node_id)
    if node_key is None:
        return False
    node_list = getattr(CFG_results, "node_list", None)
    ast_node = node_list.get(node_key) if node_list else None
    if ast_node is None:
        return False
    current = ast_node
    while current is not None and current.parent is not None:
        if current.parent.type in (
            "for_statement", "while_statement", "do_statement", "for_in_statement",
            "for_of_statement",
        ):
            return True
        current = current.parent
    return False


# ---- RDA table builder -----------------------------------------------------


def _build_rda_table(parser, CFG_results):
    """Build a Reaching Definitions table keyed by CFG node id.

    Each entry: ``{"use": set(var_names), "def": set(var_names)}``.

    Uses ancestor-walking classification to correctly handle:
      - Variable declarations (let/const/var)
      - Destructuring patterns (object and array)
      - Assignment expressions (left=def, right=use)
      - Augmented assignment and update expressions (both def and use)
      - Function parameters, catch clause parameters, for-in loop variables
      - Import bindings
      - Member expressions, subscript expressions (use the object)
      - Template substitutions, spread elements, computed property names
      - Return/throw/yield/await values
      - Conditional and loop conditions
      - Binary, ternary, unary expressions
      - Arrow functions, function expressions, method definitions
    """
    rda = defaultdict(lambda: {"use": set(), "def": set()})

    # -- Phase 1: walk every identifier / this / super --------------------
    def handler(node, p):
        var_name = _st(node)
        if not var_name:
            return

        # Find the enclosing CFG-level statement (must be in index)
        parent_stmt = _return_first_parent_of_types(
            node, statement_types["node_list_type"]
        )
        if parent_stmt is None:
            return
        stmt_id = _get_index(parser, parent_stmt)
        if stmt_id is None:
            return

        is_def, is_use = _classify_identifier(node)

        if is_def:
            rda[stmt_id]["def"].add(var_name)
        if is_use:
            rda[stmt_id]["use"].add(var_name)

    _traverse_variables(CFG_results.root_node, parser, handler)

    # -- Phase 2: annotate function / method entry nodes with param defs --
    _add_parameter_defs(parser, rda, CFG_results.root_node)

    return rda


def _add_parameter_defs(parser, rda, root_node):
    """For every function in the AST, add its formal parameters as DEFs
    at the function's CFG entry node."""
    index = parser.index

    def walk(node):
        if node.type in (
            "function_declaration", "function_expression",
            "arrow_function", "method_definition",
            "generator_function_declaration",
        ):
            func_id = index.get((node.start_point, node.end_point, node.type))
            params = _find_parameters(node)
            if func_id is not None and params:
                for p in params:
                    rda[func_id]["def"].add(p)
        for child in node.children:
            walk(child)

    walk(root_node)


# ---- dataflow solver -------------------------------------------------------


def _solve_dataflow(cfg_graph, rda_table):
    """Iterative RDA solver: compute IN/OUT sets (of variable *names*) per node.

    OUT[n] = GEN[n]  |  (IN[n] - KILL[n])
    IN[n]  = union of OUT of all CFG predecessors.
    """
    node_ids = list(cfg_graph.nodes())
    in_sets = {nid: set() for nid in node_ids}
    out_sets = {nid: set() for nid in node_ids}

    changed = True
    while changed:
        changed = False
        for nid in node_ids:
            new_in = set()
            for pred in cfg_graph.predecessors(nid):
                new_in |= out_sets.get(pred, set())
            if new_in != in_sets[nid]:
                in_sets[nid] = new_in
                changed = True

            entry = rda_table.get(nid, {"use": set(), "def": set()})
            gen = entry["def"]
            kill = entry["def"]
            new_out = gen | (in_sets[nid] - kill)
            if new_out != out_sets[nid]:
                out_sets[nid] = new_out
                changed = True

    return in_sets, out_sets


# ---- DFG edge builder ------------------------------------------------------


def _find_def_nodes(var_name, target_nid, cfg_graph, rda_table):
    """Walk CFG predecessors to find ALL nodes whose GEN contains *var_name*.

    Returns a list of (node_id, is_self) tuples.  The ``is_self`` flag
    indicates the definition is at *target_nid* itself (common in for-loops
    where the update clause is part of the for-statement node).

    For loops and other merge points multiple reaching definitions may
    exist (e.g. the initialiser and the loop back-edge).  We return all of
    them so the DFG can show the complete dataflow picture.
    """
    results = []
    if var_name in rda_table.get(target_nid, {}).get("def", set()):
        results.append((target_nid, True))

    visited = set()
    worklist = list(cfg_graph.predecessors(target_nid))
    while worklist:
        pred = worklist.pop(0)
        if pred in visited:
            continue
        visited.add(pred)
        if var_name in rda_table.get(pred, {}).get("def", set()):
            if (pred, False) not in results:
                results.append((pred, False))
        else:
            # Continue search backwards
            for pp in cfg_graph.predecessors(pred):
                if pp not in visited:
                    worklist.append(pp)
    return results


def _build_dfg_edges(
    cfg_graph, rda_table, in_sets, out_sets, properties, parser, CFG_results,
):
    """Create DFG edges using the RDA solution.

    Produces:
      - ``comesFrom``    — reaching definition → use
      - ``loop_carried`` — self-loop (def and use at same node, inside loop)
      - ``lastDef``      — definition killed at this node  (last_def=True)
      - ``lastUse``      — previous use of same variable   (last_use=True)
      - ``parameter``    — function entry → first statement (parameter flow)
    """
    final_graph = copy.deepcopy(cfg_graph)
    last_def = properties.get("last_def", False)
    last_use = properties.get("last_use", False)

    for nid, entry in rda_table.items():
        uses = entry.get("use", set())
        defs = entry.get("def", set())

        # ---- comesFrom: for each use, find the reaching definition node ----
        for var in uses:
            def_nodes = _find_def_nodes(var, nid, cfg_graph, rda_table)
            for def_node, _ in def_nodes:
                final_graph.add_edge(
                    def_node,
                    nid,
                    edge_type="DFG_edge",
                    color="#00A3FF",
                    dataflow_type="comesFrom",
                    used_def=var,
                )

        # ---- loop_carried: same node defines AND uses inside loop ---------
        for var in defs & uses:
            if _is_node_inside_loop(nid, parser, CFG_results):
                final_graph.add_edge(
                    nid,
                    nid,
                    edge_type="DFG_edge",
                    color="#FFA500",
                    dataflow_type="loop_carried",
                    used_def=var,
                )

        # ---- lastDef: variable killed at this point -----------------------
        if last_def:
            # Variables that are in IN but not in OUT → killed here
            killed = in_sets.get(nid, set()) - out_sets.get(nid, set())
            for var_name in killed:
                def_nodes = _find_def_nodes(var_name, nid, cfg_graph, rda_table)
                for def_node, _ in def_nodes:
                    final_graph.add_edge(
                        def_node,
                        nid,
                        edge_type="DFG_edge",
                        color="orange",
                        dataflow_type="lastDef",
                        used_def=var_name,
                    )

        # ---- lastUse: preceding use of the same variable ------------------
        if last_use:
            for var in uses:
                for pred in cfg_graph.predecessors(nid):
                    if pred == nid:
                        continue
                    pred_uses = rda_table.get(pred, {}).get("use", set())
                    if var in pred_uses:
                        final_graph.add_edge(
                            pred,
                            nid,
                            edge_type="DFG_edge",
                            color="green",
                            dataflow_type="lastUse",
                            used_def=var,
                        )
                        break

    # ---- parameter edges: function parameter flow --------------------------
    for u, v, k, data in cfg_graph.edges(keys=True, data=True):
        label = str(data.get("label", ""))
        cft = str(data.get("controlflow_type", ""))
        if "first_next_line" in label or "first_next_line" in cft:
            func_defs = rda_table.get(u, {}).get("def", set())
            if func_defs:
                for param_name in func_defs:
                    final_graph.add_edge(
                        u,
                        v,
                        edge_type="DFG_edge",
                        dataflow_type="parameter",
                        used_def=param_name,
                    )
            elif not final_graph.has_edge(u, v):
                final_graph.add_edge(
                    u, v,
                    edge_type="DFG_edge",
                    dataflow_type="parameter",
                )

    return final_graph


# ---- main driver -----------------------------------------------------------


def dfg_javascript(properties, CFG_results):
    """Main DFG driver for JavaScript.

    Returns ``(final_graph, debug_graph, rda_table, rda_result)``.
    """
    parser = CFG_results.parser

    cfg_graph = copy.deepcopy(CFG_results.graph)
    # Mark DFG nodes
    for nid in cfg_graph.nodes():
        cfg_graph.nodes[nid]["node_type"] = "DFG"
        cfg_graph.nodes[nid]["fillcolor"] = "#F5E0C6"
        cfg_graph.nodes[nid]["color"] = "#C98A5A"

    rda_table = _build_rda_table(parser, CFG_results)

    in_sets, out_sets = _solve_dataflow(cfg_graph, rda_table)
    rda_result = (in_sets, out_sets)

    final_graph = _build_dfg_edges(
        cfg_graph, rda_table, in_sets, out_sets, properties, parser, CFG_results,
    )
    debug_graph = copy.deepcopy(final_graph)

    return final_graph, debug_graph, rda_table, rda_result
