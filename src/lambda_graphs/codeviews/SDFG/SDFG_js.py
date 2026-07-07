"""JavaScript Data Flow Graph (DFG) via Reaching Definitions Analysis."""

import copy
from collections import defaultdict

import networkx as nx

from ...utils import DFG_utils
from ...utils.js_nodes import statement_types

# ---- JS-specific AST type lists --------------------------------------------

assignment = ["assignment_expression"]
def_statement = ["variable_declarator"]
increment_statement = ["update_expression"]
variable_type = ["identifier", "this"]
method_calls = ["call_expression"]

handled_types = (
    assignment
    + def_statement
    + increment_statement
    + method_calls
    + [
        "return_statement",
        "throw_statement",
        "arrow_function",
        "new_expression",
        "binary_expression",
    ]
)


# ---- helpers ---------------------------------------------------------------


def _st(node):
    """Safe text decode."""
    if node is None:
        return ""
    return node.text.decode("utf-8")


def _get_index(parser, node):
    return parser.index.get((node.start_point, node.end_point, node.type))


def _traverse_variables(node, parser, callback):
    """Walk *node* and call *callback(node, parser)* for every identifier/this."""
    if node.is_named and node.type in variable_type:
        callback(node, parser)
    for child in node.children:
        _traverse_variables(child, parser, callback)


def _return_first_parent_of_types(node, parent_types):
    while node is not None:
        if node.type in parent_types:
            return node
        node = node.parent
    return None


# ---- RDA entry -------------------------------------------------------------


class RDAEntry:
    __slots__ = ("name", "line", "use", "def_", "declaration", "method_call")

    def __init__(
        self, name, line, use=None, def_=None, declaration=False, method_call=False
    ):
        self.name = name
        self.line = line
        self.use = use or set()
        self.def_ = def_ or set()
        self.declaration = declaration
        self.method_call = method_call

    def __repr__(self):
        return (
            f"RDA({self.name!r}, line={self.line}, " f"use={self.use}, def={self.def_})"
        )


def _build_rda_table(parser, CFG_results):
    """Walk the AST and build a Reaching Definitions table keyed by statement id."""
    rda = defaultdict(lambda: {"use": set(), "def": set()})

    index = parser.index
    symbol_table = parser.symbol_table

    def handler(node, p):
        node_id = _get_index(parser, node)
        if node_id is None:
            return
        line = node.start_point[0]
        var_name = _st(node)

        parent_stmt = _return_first_parent_of_types(
            node, statement_types["node_list_type"]
        )
        if parent_stmt is None:
            return
        stmt_id = _get_index(parser, parent_stmt)
        if stmt_id is None:
            return

        parent = node.parent
        if parent is not None and parent.type in def_statement:
            rda[stmt_id]["def"].add(var_name)
        elif parent is not None and parent.type in method_calls:
            rda[stmt_id]["use"].add(var_name)
        elif parent is not None and parent.type in assignment:
            left = parent.child_by_field_name("left")
            right = parent.child_by_field_name("right")
            if left is not None and node_id == _get_index(parser, left):
                rda[stmt_id]["def"].add(var_name)
            elif right is not None:
                rda[stmt_id]["use"].add(var_name)
        elif parent is not None and parent.type in increment_statement:
            rda[stmt_id]["def"].add(var_name)
            rda[stmt_id]["use"].add(var_name)
        else:
            rda[stmt_id]["use"].add(var_name)

    _traverse_variables(CFG_results.root_node, parser, handler)
    return rda


# ---- dataflow solver -------------------------------------------------------


def _solve_dataflow(cfg_graph, rda_table):
    """Iterative dataflow: compute IN/OUT sets for each CFG node."""
    node_ids = list(cfg_graph.nodes())
    in_sets = {nid: set() for nid in node_ids}
    out_sets = {nid: set() for nid in node_ids}

    changed = True
    while changed:
        changed = False
        for nid in node_ids:
            # IN = union of OUT of all predecessors
            new_in = set()
            for pred in cfg_graph.predecessors(nid):
                new_in |= out_sets.get(pred, set())
            if new_in != in_sets[nid]:
                in_sets[nid] = new_in
                changed = True

            # OUT = GEN  |  (IN - KILL)
            entry = rda_table.get(nid, {"use": set(), "def": set()})
            gen = entry["def"]
            kill = entry["def"]  # definitions kill previous definitions of same var
            new_out = gen | (in_sets[nid] - kill)
            if new_out != out_sets[nid]:
                out_sets[nid] = new_out
                changed = True

    return in_sets, out_sets


# ---- DFG edge building -----------------------------------------------------


def _build_dfg_edges(cfg_graph, rda_table, in_sets):
    """Create DFG edges: for each use of variable v at node n, add an edge
    from the definition node that reaches n."""
    final_graph = copy.deepcopy(cfg_graph)
    # Keep CFG edges in place; add DFG edges on top.

    for nid, entry in rda_table.items():
        uses = entry.get("use", set())
        for var in uses:
            # Walk CFG predecessors to find the nearest definition of *var*
            visited = set()
            worklist = list(cfg_graph.predecessors(nid))
            while worklist:
                pred = worklist.pop(0)
                if pred in visited:
                    continue
                visited.add(pred)
                pred_entry = rda_table.get(pred)
                if pred_entry and var in pred_entry.get("def", set()):
                    # Found the defining node — add DFG edge
                    final_graph.add_edge(
                        pred,
                        nid,
                        edge_type="DFG_edge",
                        color="#00A3FF",
                        dataflow_type="comesFrom",
                        used_def=var,
                    )
                    break
                else:
                    # Keep searching backward through CFG
                    worklist.extend(cfg_graph.predecessors(pred))

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
        cfg_graph.nodes[nid]["source"] = "DFG"
        cfg_graph.nodes[nid]["fillcolor"] = "#F5E0C6"
        cfg_graph.nodes[nid]["color"] = "#C98A5A"

    rda_table = _build_rda_table(parser, CFG_results)

    in_sets, out_sets = _solve_dataflow(cfg_graph, rda_table)
    rda_result = (in_sets, out_sets)

    final_graph = _build_dfg_edges(cfg_graph, rda_table, in_sets)
    debug_graph = copy.deepcopy(final_graph)

    return final_graph, debug_graph, rda_table, rda_result
