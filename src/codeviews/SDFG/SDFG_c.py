import copy
import time
from collections import defaultdict

import networkx as nx
from deepdiff import DeepDiff
from loguru import logger

from utils.c_nodes import statement_types
from utils.src_parser import traverse_tree

assignment = ["assignment_expression"]
def_statement = ["init_declarator"]
declaration_statement = ["declaration"]
increment_statement = ["update_expression"]
variable_type = ["identifier"]
function_calls = ["call_expression"]
literal_types = [
    "number_literal",
    "string_literal",
    "char_literal",
    "true",
    "false",
    "null",
]

input_functions = [
    "scanf",
    "gets",
    "fgets",
    "getline",
    "fscanf",
    "sscanf",
    "fread",
    "read",
    "recv",
    "recvfrom",
    "getchar",
    "fgetc",
]

inner_types = ["declaration", "expression_statement"]
handled_types = (
    assignment
    + def_statement
    + increment_statement
    + function_calls
    + ["function_definition", "return_statement", "for_statement", "switch_statement"]
)

debug = False


def st(child):
    """Get text from AST node"""
    if child is None:
        return ""
    else:
        return child.text.decode()


def get_index(node, index):
    """Get unique index for AST node"""
    try:
        return index[(node.start_point, node.end_point, node.type)]
    except:
        return None


def read_index(index, idx):
    """Get AST node key from index value"""
    return list(index.keys())[list(index.values()).index(idx)]


def scope_check(parent_scope, child_scope):
    """
    Check if a definition's scope can reach a use's scope.

    A definition at scope [0, 1, 2] can reach uses at:
    - [0, 1, 2] (same scope)
    - [0, 1, 2, 3] (nested scope)

    But NOT:
    - [0, 1] (parent scope)
    - [0, 1, 3] (sibling scope)
    """
    for p in parent_scope:
        if p not in child_scope:
            return False
    return True


def set_add(lst, item):
    """Add item to list if not already present (set-like behavior)"""
    for entry in lst:
        if item == entry:
            return
    lst.append(item)


def set_union(first_list, second_list):
    """Union of two lists (set-like)"""
    resulting_list = list(first_list)
    resulting_list.extend(x for x in second_list if x not in resulting_list)
    return resulting_list


def set_difference(first_list, second_list):
    """Difference of two lists (set-like)"""
    return [item for item in first_list if item not in second_list]


def return_first_parent_of_types(node, parent_types, stop_types=None):
    """Find first parent of given types"""
    if stop_types is None:
        stop_types = []

    if node.type in parent_types:
        return node

    while node.parent is not None:
        if node.type in stop_types:
            return None
        if node.parent.type in parent_types:
            return node.parent
        node = node.parent

    return None


def recursively_get_children_of_types(
    node, st_types, check_list=None, index=None, result=None, stop_types=None
):
    """Recursively find child nodes of given types"""
    if isinstance(st_types, str):
        st_types = [st_types]
    if stop_types is None:
        stop_types = []
    if result is None:
        result = []

    if node.type in stop_types:
        return result

    if check_list and index:
        result.extend(
            [
                child
                for child in node.children
                if child.type in st_types and get_index(child, index) in check_list
            ]
        )
    else:
        result.extend([child for child in node.children if child.type in st_types])

    for child in node.named_children:
        if child.type not in stop_types:
            result = recursively_get_children_of_types(
                child,
                st_types,
                result=result,
                stop_types=stop_types,
                index=index,
                check_list=check_list,
            )

    return result


class Identifier:
    """Represents a variable at a specific line with scope information"""

    def __init__(self, parser, node, line=None, declaration=False, full_ref=None):
        self.core = st(node)
        self.unresolved_name = st(full_ref) if full_ref else st(node)
        self.name = self._resolve_name(node, full_ref, parser)
        self.line = line
        self.declaration = declaration
        self.satisfied = False

        variable_index = get_index(node, parser.index)
        if variable_index and variable_index in parser.symbol_table["scope_map"]:
            self.variable_scope = parser.symbol_table["scope_map"][variable_index]
            if variable_index in parser.declaration_map:
                decl_index = parser.declaration_map[variable_index]
                self.scope = parser.symbol_table["scope_map"].get(decl_index, [0])
            else:
                self.scope = [0]

            if declaration:
                self.scope = self.variable_scope
        else:
            self.variable_scope = [0]
            self.scope = [0]

        if line is not None:
            self.real_line_no = read_index(parser.index, line)[0][0]

    def _resolve_name(self, node, full_ref, parser):
        """Resolve identifier name for C"""
        if full_ref is None:
            return st(node)

        if full_ref.type == "field_expression":
            obj = full_ref.child_by_field_name("argument")
            field = full_ref.child_by_field_name("field")
            return st(obj) + "." + st(field)

        if full_ref.type == "pointer_expression":
            arg = full_ref.child_by_field_name("argument")
            return "*" + st(arg)

        if full_ref.type == "subscript_expression":
            arg = full_ref.child_by_field_name("argument")
            return st(arg)

        return st(node)

    def __eq__(self, other):
        return (
            self.name == other.name
            and self.line == other.line
            and sorted(self.scope) == sorted(other.scope)
        )

    def __hash__(self):
        return hash((self.name, self.line, str(self.scope)))

    def __str__(self):
        result = [self.name]
        if self.line:
            result += [str(self.real_line_no)]
            result += ["|".join(map(str, self.scope))]
        else:
            result += ["?"]
        return f"{{{','.join(result)}}}"


class Literal:
    """Represents a literal constant (number, string, etc.) as a data flow source"""

    def __init__(self, parser, node, line=None):
        self.core = st(node)
        self.name = f"LITERAL_{st(node)}"
        self.value = st(node)
        self.line = line
        self.declaration = True
        self.satisfied = False
        self.scope = [0]
        self.variable_scope = [0]

        if line is not None:
            self.real_line_no = read_index(parser.index, line)[0][0]

    def __eq__(self, other):
        return self.name == other.name and self.line == other.line

    def __hash__(self):
        return hash((self.name, self.line))

    def __str__(self):
        result = [f"Literal({self.value})"]
        if self.line:
            result += [str(self.real_line_no)]
        else:
            result += ["?"]
        return f"{{{','.join(result)}}}"


def extract_identifier_from_declarator(declarator_node):
    """Extract identifier from declarator (may be wrapped in pointer/array)"""
    if declarator_node.type == "identifier":
        return declarator_node
    elif declarator_node.type == "pointer_declarator":
        for child in declarator_node.children:
            if child.type in ["identifier", "pointer_declarator", "array_declarator"]:
                return extract_identifier_from_declarator(child)
    elif declarator_node.type == "array_declarator":
        if declarator_node.children:
            return extract_identifier_from_declarator(declarator_node.children[0])
    elif declarator_node.type == "function_declarator":
        for child in declarator_node.children:
            if child.type in [
                "identifier",
                "pointer_declarator",
                "parenthesized_declarator",
            ]:
                return extract_identifier_from_declarator(child)
    elif declarator_node.type == "parenthesized_declarator":
        for child in declarator_node.children:
            if child.type in ["identifier", "pointer_declarator", "array_declarator"]:
                return extract_identifier_from_declarator(child)
    return None


def extract_param_identifier(param_node):
    """Extract identifier from parameter_declaration"""
    for child in param_node.children:
        if child.type == "identifier":
            return child
        elif child.type in [
            "pointer_declarator",
            "array_declarator",
            "function_declarator",
        ]:
            return extract_identifier_from_declarator(child)
    return None


def extract_operator_text(assign_node, left_node, right_node):
    """Extract operator from assignment (=, +=, -=, etc.)"""
    left_text = left_node.text
    right_text = right_node.text
    operator_bytes = (
        assign_node.text.split(left_text, 1)[-1].rsplit(right_text, 1)[0].strip()
    )
    return operator_bytes.decode()


def add_entry(
    parser,
    rda_table,
    statement_id,
    used=None,
    defined=None,
    declaration=False,
    core=None,
):
    """
    Add variable USE or DEF to RDA table.

    Args:
        parser: C parser
        rda_table: RDA table
        statement_id: Statement where this occurs
        used: Variable being used (read)
        defined: Variable being defined (written)
        declaration: True if declaration
        core: Full reference node
    """
    if statement_id not in rda_table:
        rda_table[statement_id] = defaultdict(list)

    if not used and not defined:
        return

    current_node = used or defined
    if core is None:
        core = current_node

    if current_node.type in literal_types:
        if used:
            set_add(
                rda_table[statement_id]["use"],
                Literal(parser, current_node, statement_id),
            )
        return

    if current_node.type == "field_expression":
        if defined is not None:
            set_add(
                rda_table[statement_id]["def"],
                Identifier(
                    parser,
                    current_node.child_by_field_name("argument"),
                    statement_id,
                    full_ref=None,
                    declaration=declaration,
                ),
            )
        else:
            set_add(
                rda_table[statement_id]["use"],
                Identifier(
                    parser, current_node.child_by_field_name("argument"), full_ref=None
                ),
            )
        return

    if used and used.type == "unary_expression":
        operator = None
        argument = None
        for child in used.children:
            if child.type == "&":
                operator = child
            elif child.is_named:
                argument = child

        if operator is not None and argument is not None:
            if argument.type in variable_type:
                arg_index = get_index(argument, parser.index)
                if arg_index and arg_index in parser.symbol_table["scope_map"]:
                    set_add(
                        rda_table[statement_id]["use"],
                        Identifier(parser, argument, full_ref=argument),
                    )
                elif arg_index and arg_index in parser.method_map:
                    set_add(
                        rda_table[statement_id]["use"],
                        Identifier(parser, argument, full_ref=argument),
                    )
            return

    if current_node.type == "pointer_expression":
        pointer = current_node.child_by_field_name("argument")

        if defined is not None:
            pointer_index = get_index(pointer, parser.index)
            if pointer_index and pointer_index in parser.symbol_table["scope_map"]:
                set_add(
                    rda_table[statement_id]["use"],
                    Identifier(parser, pointer, full_ref=pointer),
                )

            set_add(
                rda_table[statement_id]["def"],
                Identifier(
                    parser,
                    pointer,
                    statement_id,
                    full_ref=core,
                    declaration=declaration,
                ),
            )
        else:
            set_add(
                rda_table[statement_id]["use"],
                Identifier(parser, pointer, full_ref=core),
            )
        return

    if current_node.type == "subscript_expression":
        array = current_node.child_by_field_name("argument")
        index_expr = current_node.child_by_field_name("index")

        if defined is not None:
            set_add(
                rda_table[statement_id]["def"],
                Identifier(
                    parser, array, statement_id, full_ref=core, declaration=declaration
                ),
            )
        set_add(
            rda_table[statement_id]["use"], Identifier(parser, array, full_ref=core)
        )

        if index_expr:
            if index_expr.type in variable_type:
                index_id = get_index(index_expr, parser.index)
                if index_id and index_id in parser.symbol_table["scope_map"]:
                    set_add(
                        rda_table[statement_id]["use"],
                        Identifier(parser, index_expr, full_ref=index_expr),
                    )
            elif index_expr.type in literal_types:
                set_add(
                    rda_table[statement_id]["use"],
                    Literal(parser, index_expr, statement_id),
                )
            else:
                identifiers_in_index = recursively_get_children_of_types(
                    index_expr,
                    variable_type + ["field_expression"],
                    index=parser.index,
                    check_list=parser.symbol_table["scope_map"],
                )
                for identifier in identifiers_in_index:
                    set_add(
                        rda_table[statement_id]["use"],
                        Identifier(parser, identifier, full_ref=identifier),
                    )
                literals_in_index = recursively_get_children_of_types(
                    index_expr, literal_types, index=parser.index
                )
                for literal in literals_in_index:
                    set_add(
                        rda_table[statement_id]["use"],
                        Literal(parser, literal, statement_id),
                    )
        return

    node_index = get_index(current_node, parser.index)
    if node_index is None or node_index not in parser.symbol_table["scope_map"]:
        return

    if defined is not None:
        set_add(
            rda_table[statement_id]["def"],
            Identifier(
                parser, defined, statement_id, full_ref=core, declaration=declaration
            ),
        )
    else:
        set_add(
            rda_table[statement_id]["use"],
            Identifier(parser, used, full_ref=core, declaration=declaration),
        )


def is_return_value_used(call_expr_statement):
    """
    Check if a function call's return value is actually used.

    Args:
        call_expr_statement: The expression_statement or parent node containing the call

    Returns:
        True if return value is used (assigned, passed as argument, returned, in conditional)
        False if return value is discarded (standalone statement like fn();)
    """
    if call_expr_statement.type == "expression_statement":
        if len(call_expr_statement.named_children) == 1:
            child = call_expr_statement.named_children[0]
            if child.type == "call_expression":
                return False

    parent = call_expr_statement.parent
    while parent:
        parent_type = parent.type

        if parent_type in ["init_declarator", "assignment_expression"]:
            return True

        if parent_type == "return_statement":
            return True

        if parent_type == "argument_list":
            return True

        if parent_type in [
            "if_statement",
            "while_statement",
            "for_statement",
            "do_while_statement",
            "switch_statement",
        ]:
            return True

        if parent_type == "expression_statement":
            return False

        parent = parent.parent

    return False


def collect_function_metadata(parser):
    """
    Collect metadata about all functions in the program.

    For each function, track:
    - Function name
    - Parameter names and whether they're pointers
    - Parameter indices

    Returns:
        Dict mapping function_name -> {
            "params": [(param_name, is_pointer, param_index), ...],
            "node": function_definition AST node
        }
    """
    metadata = {}

    for node in traverse_tree(parser.tree.root_node):
        if node.type == "function_definition":
            func_name = None
            params = []

            for child in node.named_children:
                if child.type == "function_declarator":
                    declarator = child.child_by_field_name("declarator")
                    if declarator:
                        if declarator.type == "identifier":
                            func_name = st(declarator)
                        elif declarator.type == "pointer_declarator":
                            inner = declarator
                            while inner and inner.type == "pointer_declarator":
                                inner_declarator = inner.child_by_field_name(
                                    "declarator"
                                )
                                if inner_declarator:
                                    inner = inner_declarator
                                else:
                                    break
                            if inner and inner.type == "identifier":
                                func_name = st(inner)

                    param_list = child.child_by_field_name("parameters")
                    if param_list:
                        param_idx = 0
                        for param in param_list.named_children:
                            if param.type == "parameter_declaration":
                                param_name = None
                                is_pointer = False

                                for p_child in param.named_children:
                                    if p_child.type == "pointer_declarator":
                                        is_pointer = True
                                        inner = p_child
                                        while inner:
                                            if inner.type == "identifier":
                                                param_name = st(inner)
                                                break
                                            elif inner.type == "pointer_declarator":
                                                inner_decl = inner.child_by_field_name(
                                                    "declarator"
                                                )
                                                if inner_decl:
                                                    inner = inner_decl
                                                else:
                                                    break
                                            else:
                                                break
                                    elif p_child.type == "array_declarator":
                                        is_pointer = True
                                        param_name = st(
                                            extract_identifier_from_declarator(p_child)
                                        )
                                    elif p_child.type == "identifier":
                                        if param_name is None:
                                            param_name = st(p_child)

                                if param_name:
                                    params.append((param_name, is_pointer, param_idx))
                                    param_idx += 1
                    break

            if func_name:
                metadata[func_name] = {"params": params, "node": node}

    return metadata


def analyze_pointer_modifications(parser, function_metadata):
    """
    Analyze which pointer parameters are modified within each function.

    A pointer parameter is considered "modified" if:
    - It's dereferenced on the left side of an assignment: *param = ...
    - Used in pointer arithmetic with assignment: param[i] = ...
    - Passed to another function that modifies it (transitive)

    Args:
        parser: Parser with AST
        function_metadata: Dict from collect_function_metadata()

    Returns:
        Dict mapping function_name -> set of parameter indices that are modified
    """
    modifications = {}

    for func_name, meta in function_metadata.items():
        modified_params = set()
        func_node = meta["node"]

        param_name_to_idx = {}
        for param_name, is_pointer, param_idx in meta["params"]:
            if is_pointer:
                param_name_to_idx[param_name] = param_idx

        if not param_name_to_idx:
            modifications[func_name] = modified_params
            continue

        for node in traverse_tree(func_node):
            if node.type == "assignment_expression":
                left = node.child_by_field_name("left")
                if left:
                    if left.type == "pointer_expression":
                        arg = left.child_by_field_name("argument")
                        if arg and arg.type == "identifier":
                            var_name = st(arg)
                            if var_name in param_name_to_idx:
                                modified_params.add(param_name_to_idx[var_name])

                    elif left.type == "subscript_expression":
                        array_arg = left.child_by_field_name("argument")
                        if array_arg and array_arg.type == "identifier":
                            var_name = st(array_arg)
                            if var_name in param_name_to_idx:
                                modified_params.add(param_name_to_idx[var_name])

                    elif left.type == "field_expression":
                        obj = left.child_by_field_name("argument")
                        if obj and obj.type == "identifier":
                            var_name = st(obj)
                            if var_name in param_name_to_idx:
                                modified_params.add(param_name_to_idx[var_name])

            elif node.type == "update_expression":
                arg = node.child_by_field_name("argument")
                if arg:
                    if arg.type == "parenthesized_expression":
                        inner_children = [c for c in arg.named_children if c.is_named]
                        if inner_children:
                            arg = inner_children[0]

                    if arg.type == "pointer_expression":
                        inner_arg = arg.child_by_field_name("argument")
                        if inner_arg and inner_arg.type == "identifier":
                            var_name = st(inner_arg)
                            if var_name in param_name_to_idx:
                                modified_params.add(param_name_to_idx[var_name])
                    elif arg.type == "subscript_expression":
                        array_arg = arg.child_by_field_name("argument")
                        if array_arg and array_arg.type == "identifier":
                            var_name = st(array_arg)
                            if var_name in param_name_to_idx:
                                modified_params.add(param_name_to_idx[var_name])
                    elif arg.type == "field_expression":
                        obj = arg.child_by_field_name("argument")
                        if obj and obj.type == "identifier":
                            var_name = st(obj)
                            if var_name in param_name_to_idx:
                                modified_params.add(param_name_to_idx[var_name])

        modifications[func_name] = modified_params

    return modifications


def build_rda_table(
    parser, CFG_results, function_metadata=None, pointer_modifications=None
):
    """
    Build RDA table by traversing AST and tracking DEF/USE.

    Follows Java SDFG pattern: traverse tree stopping at identifiers,
    check each node's type to determine DEF/USE relationships.

    Returns:
        rda_table: Dict mapping statement_id to {"def": set, "use": set}
    """
    rda_table = {}
    index = parser.index
    tree = parser.tree

    inner_types = ["parenthesized_expression", "binary_expression", "unary_expression"]
    handled_cases = ["compound_statement", "translation_unit"]

    for root_node in traverse_tree(tree, variable_type):
        if not root_node.is_named:
            continue

        if root_node.type == "return_statement":
            parent_id = get_index(root_node, index)
            if parent_id is None or parent_id not in CFG_results.graph.nodes:
                continue

            return_expr = (
                root_node.named_children[0] if root_node.named_children else None
            )
            if (
                return_expr
                and return_expr.type
                in variable_type
                + ["field_expression", "pointer_expression", "subscript_expression"]
                + literal_types
            ):
                add_entry(parser, rda_table, parent_id, used=return_expr)
            else:
                vars_used = recursively_get_children_of_types(
                    root_node,
                    variable_type
                    + [
                        "field_expression",
                        "pointer_expression",
                        "subscript_expression",
                    ],
                    index=parser.index,
                    check_list=parser.symbol_table["scope_map"],
                )
                for var in vars_used:
                    add_entry(parser, rda_table, parent_id, used=var)

            literals_used = recursively_get_children_of_types(
                root_node, literal_types, index=parser.index
            )
            for literal in literals_used:
                add_entry(parser, rda_table, parent_id, used=literal)

        elif root_node.type in def_statement:
            parent_statement = return_first_parent_of_types(
                root_node, statement_types["node_list_type"]
            )
            if parent_statement is None:
                continue

            parent_id = get_index(parent_statement, index)
            if parent_id is None or parent_id not in CFG_results.graph.nodes:
                if parent_statement and parent_statement.type in inner_types:
                    parent_statement = return_first_parent_of_types(
                        parent_statement, statement_types["node_list_type"]
                    )
                    parent_id = get_index(parent_statement, index)
                elif parent_statement.type in handled_cases:
                    continue
                else:
                    continue

            declarator = root_node.child_by_field_name("declarator")
            if declarator is None and len(root_node.children) > 0:
                declarator = root_node.children[0]

            var_identifier = extract_identifier_from_declarator(declarator)

            if var_identifier:
                add_entry(
                    parser,
                    rda_table,
                    parent_id,
                    defined=var_identifier,
                    declaration=True,
                )

            initializer = root_node.child_by_field_name("value")
            if initializer:
                if (
                    initializer.type
                    in variable_type
                    + [
                        "field_expression",
                        "pointer_expression",
                        "subscript_expression",
                        "unary_expression",
                    ]
                    + literal_types
                ):
                    add_entry(parser, rda_table, parent_id, used=initializer)
                else:
                    vars_used = recursively_get_children_of_types(
                        initializer,
                        variable_type + ["field_expression"],
                        index=parser.index,
                        check_list=parser.symbol_table["scope_map"],
                    )
                    for var in vars_used:
                        add_entry(parser, rda_table, parent_id, used=var)
                    literals_used = recursively_get_children_of_types(
                        initializer, literal_types, index=parser.index
                    )
                    for literal in literals_used:
                        add_entry(parser, rda_table, parent_id, used=literal)

        elif root_node.type in declaration_statement:
            parent_id = get_index(root_node, index)
            if parent_id is None or parent_id not in CFG_results.graph.nodes:
                continue

            has_init_declarator = any(
                child.type == "init_declarator" for child in root_node.named_children
            )
            if has_init_declarator:
                continue

            for child in root_node.named_children:
                if child.type == "identifier":
                    child_id = get_index(child, index)
                    if child_id:
                        from collections import defaultdict

                        if parent_id not in rda_table:
                            rda_table[parent_id] = defaultdict(list)
                        ident = Identifier(parser, child, parent_id, declaration=True)
                        ident.scope = [0]
                        ident.variable_scope = [0]
                        set_add(rda_table[parent_id]["def"], ident)
                elif child.type in [
                    "pointer_declarator",
                    "array_declarator",
                    "function_declarator",
                    "parenthesized_declarator",
                ]:
                    var_identifier = extract_identifier_from_declarator(child)
                    if var_identifier:
                        var_id = get_index(var_identifier, index)
                        if var_id:
                            add_entry(
                                parser,
                                rda_table,
                                parent_id,
                                defined=var_identifier,
                                declaration=True,
                            )

        elif root_node.type in assignment:
            parent_statement = return_first_parent_of_types(
                root_node, statement_types["node_list_type"]
            )
            if parent_statement is None:
                continue

            parent_id = get_index(parent_statement, index)
            if parent_id is None or parent_id not in CFG_results.graph.nodes:
                if parent_statement and parent_statement.type in inner_types:
                    parent_statement = return_first_parent_of_types(
                        parent_statement, statement_types["node_list_type"]
                    )
                    parent_id = get_index(parent_statement, index)
                elif parent_statement.type in handled_cases:
                    continue
                else:
                    continue

            left_node = root_node.child_by_field_name("left")
            right_node = root_node.child_by_field_name("right")

            if left_node is None or right_node is None:
                continue

            operator_text = extract_operator_text(root_node, left_node, right_node)

            if operator_text != "=":
                add_entry(parser, rda_table, parent_id, used=left_node)
            else:
                if left_node.type == "field_expression":
                    add_entry(parser, rda_table, parent_id, used=left_node)
                elif left_node.type in variable_type:
                    left_node_index = get_index(left_node, index)
                    if (
                        left_node_index
                        and left_node_index in parser.symbol_table["scope_map"]
                    ):
                        is_init_declarator = False
                        check_parent = root_node.parent
                        while check_parent:
                            if check_parent.type == "init_declarator":
                                is_init_declarator = True
                                break
                            if check_parent.type in statement_types.get(
                                "node_list_type", []
                            ):
                                break
                            check_parent = check_parent.parent

                        if not is_init_declarator:
                            add_entry(parser, rda_table, parent_id, used=left_node)

            add_entry(parser, rda_table, parent_id, defined=left_node)

            if (
                right_node.type
                in variable_type
                + [
                    "field_expression",
                    "pointer_expression",
                    "subscript_expression",
                    "unary_expression",
                ]
                + literal_types
            ):
                add_entry(parser, rda_table, parent_id, used=right_node)
            else:
                vars_used = recursively_get_children_of_types(
                    right_node,
                    variable_type + ["field_expression"],
                    index=parser.index,
                    check_list=parser.symbol_table["scope_map"],
                )
                for var in vars_used:
                    add_entry(parser, rda_table, parent_id, used=var)
                literals_used = recursively_get_children_of_types(
                    right_node, literal_types, index=parser.index
                )
                for literal in literals_used:
                    add_entry(parser, rda_table, parent_id, used=literal)

        elif root_node.type in increment_statement:
            parent_statement = return_first_parent_of_types(
                root_node, statement_types["node_list_type"]
            )
            if parent_statement is None:
                continue

            parent_id = get_index(parent_statement, index)
            if parent_id is None or parent_id not in CFG_results.graph.nodes:
                if parent_statement and parent_statement.type in inner_types:
                    parent_statement = return_first_parent_of_types(
                        parent_statement, statement_types["node_list_type"]
                    )
                    parent_id = get_index(parent_statement, index)
                elif parent_statement.type in handled_cases:
                    continue
                else:
                    continue

            if root_node.type in variable_type + ["field_expression"]:
                add_entry(parser, rda_table, parent_id, used=root_node)
                add_entry(parser, rda_table, parent_id, defined=root_node)
            else:
                identifiers = recursively_get_children_of_types(
                    root_node,
                    variable_type + ["field_expression"],
                    index=parser.index,
                    check_list=parser.symbol_table["scope_map"],
                )
                for identifier in identifiers:
                    add_entry(parser, rda_table, parent_id, used=identifier)
                    add_entry(parser, rda_table, parent_id, defined=identifier)

        elif root_node.type in function_calls:
            parent_statement = return_first_parent_of_types(
                root_node, statement_types["node_list_type"]
            )
            if parent_statement is None:
                continue

            parent_id = get_index(parent_statement, index)
            if parent_id is None or parent_id not in CFG_results.graph.nodes:
                if parent_statement and parent_statement.type in inner_types:
                    parent_statement = return_first_parent_of_types(
                        parent_statement, statement_types["node_list_type"]
                    )
                    parent_id = get_index(parent_statement, index)
                elif parent_statement.type in handled_cases:
                    continue
                else:
                    continue

            function_name = None
            if root_node.children and root_node.children[0].type == "identifier":
                function_name = st(root_node.children[0])

            is_input_function = function_name in input_functions

            for child in root_node.children[1:]:
                if is_input_function and child.type == "argument_list":
                    for arg in child.named_children:
                        if arg.type == "pointer_expression":
                            inner_arg = arg.child_by_field_name("argument")
                            if inner_arg:
                                if inner_arg.type in variable_type:
                                    add_entry(
                                        parser,
                                        rda_table,
                                        parent_id,
                                        defined=inner_arg,
                                        declaration=False,
                                    )
                                elif inner_arg.type in [
                                    "field_expression",
                                    "subscript_expression",
                                ]:
                                    add_entry(
                                        parser,
                                        rda_table,
                                        parent_id,
                                        defined=inner_arg,
                                        declaration=False,
                                    )
                                    if inner_arg.type == "subscript_expression":
                                        index_expr = inner_arg.child_by_field_name(
                                            "index"
                                        )
                                        if index_expr:
                                            vars_in_index = (
                                                recursively_get_children_of_types(
                                                    index_expr,
                                                    variable_type
                                                    + ["field_expression"],
                                                    index=parser.index,
                                                    check_list=parser.symbol_table[
                                                        "scope_map"
                                                    ],
                                                )
                                            )
                                            for var in vars_in_index:
                                                add_entry(
                                                    parser,
                                                    rda_table,
                                                    parent_id,
                                                    used=var,
                                                )
                        elif arg.type in variable_type + ["field_expression"]:
                            add_entry(parser, rda_table, parent_id, used=arg)
                        elif arg.type in literal_types:
                            add_entry(parser, rda_table, parent_id, used=arg)
                        else:
                            identifiers_used = recursively_get_children_of_types(
                                arg,
                                variable_type + ["field_expression"],
                                index=parser.index,
                                check_list=parser.symbol_table["scope_map"],
                            )
                            for identifier in identifiers_used:
                                add_entry(parser, rda_table, parent_id, used=identifier)
                            literals_used = recursively_get_children_of_types(
                                arg, literal_types, index=parser.index
                            )
                            for literal in literals_used:
                                add_entry(parser, rda_table, parent_id, used=literal)
                elif not is_input_function and child.type == "argument_list":
                    modifies_params = set()
                    if (
                        function_name
                        and function_metadata
                        and function_name in function_metadata
                    ):
                        if (
                            pointer_modifications
                            and function_name in pointer_modifications
                        ):
                            modifies_params = pointer_modifications[function_name]

                    for arg_idx, arg in enumerate(child.named_children):
                        is_modified_param = arg_idx in modifies_params

                        if is_modified_param and arg.type == "pointer_expression":
                            inner_arg = arg.child_by_field_name("argument")
                            if inner_arg:
                                if inner_arg.type in variable_type:
                                    add_entry(
                                        parser, rda_table, parent_id, used=inner_arg
                                    )
                                    add_entry(
                                        parser,
                                        rda_table,
                                        parent_id,
                                        defined=inner_arg,
                                        declaration=False,
                                    )
                                elif inner_arg.type in [
                                    "field_expression",
                                    "subscript_expression",
                                ]:
                                    add_entry(
                                        parser, rda_table, parent_id, used=inner_arg
                                    )
                                    add_entry(
                                        parser,
                                        rda_table,
                                        parent_id,
                                        defined=inner_arg,
                                        declaration=False,
                                    )
                                    if inner_arg.type == "subscript_expression":
                                        index_expr = inner_arg.child_by_field_name(
                                            "index"
                                        )
                                        if index_expr:
                                            vars_in_index = (
                                                recursively_get_children_of_types(
                                                    index_expr,
                                                    variable_type
                                                    + ["field_expression"],
                                                    index=parser.index,
                                                    check_list=parser.symbol_table[
                                                        "scope_map"
                                                    ],
                                                )
                                            )
                                            for var in vars_in_index:
                                                add_entry(
                                                    parser,
                                                    rda_table,
                                                    parent_id,
                                                    used=var,
                                                )
                        elif arg.type in variable_type + ["field_expression"]:
                            add_entry(parser, rda_table, parent_id, used=arg)
                        elif arg.type in literal_types:
                            add_entry(parser, rda_table, parent_id, used=arg)
                        else:
                            identifiers_used = recursively_get_children_of_types(
                                arg,
                                variable_type + ["field_expression"],
                                index=parser.index,
                                check_list=parser.symbol_table["scope_map"],
                            )
                            for identifier in identifiers_used:
                                add_entry(parser, rda_table, parent_id, used=identifier)
                            literals_used = recursively_get_children_of_types(
                                arg, literal_types, index=parser.index
                            )
                            for literal in literals_used:
                                add_entry(parser, rda_table, parent_id, used=literal)

                elif child.type in variable_type + ["field_expression"]:
                    add_entry(parser, rda_table, parent_id, used=child)
                elif child.type in literal_types:
                    add_entry(parser, rda_table, parent_id, used=child)
                else:
                    identifiers_used = recursively_get_children_of_types(
                        child,
                        variable_type + ["field_expression"],
                        index=parser.index,
                        check_list=parser.symbol_table["scope_map"],
                    )
                    for identifier in identifiers_used:
                        add_entry(parser, rda_table, parent_id, used=identifier)
                    literals_used = recursively_get_children_of_types(
                        child, literal_types, index=parser.index
                    )
                    for literal in literals_used:
                        add_entry(parser, rda_table, parent_id, used=literal)

        elif root_node.type == "function_definition":
            parent_id = get_index(root_node, index)
            if parent_id is None:
                continue

            for child in root_node.named_children:
                if child.type == "function_declarator":
                    func_name_node = child.child_by_field_name("declarator")
                    if func_name_node and func_name_node.type in variable_type:
                        func_name_idx = get_index(func_name_node, index)
                        if (
                            func_name_idx
                            and func_name_idx in parser.symbol_table["scope_map"]
                        ):
                            add_entry(
                                parser,
                                rda_table,
                                parent_id,
                                defined=func_name_node,
                                declaration=True,
                            )

                    param_list = child.child_by_field_name("parameters")
                    if param_list:
                        for param in param_list.named_children:
                            if param.type == "parameter_declaration":
                                param_id = extract_param_identifier(param)
                                if param_id:
                                    add_entry(
                                        parser,
                                        rda_table,
                                        parent_id,
                                        defined=param_id,
                                        declaration=True,
                                    )
                    break

        elif root_node.type == "switch_statement":
            parent_id = get_index(root_node, index)
            if parent_id is None or parent_id not in CFG_results.graph.nodes:
                continue

            condition = root_node.child_by_field_name("condition")
            if condition:
                identifiers_used = recursively_get_children_of_types(
                    condition,
                    variable_type + ["field_expression"],
                    index=parser.index,
                    check_list=parser.symbol_table["scope_map"],
                )
                for identifier in identifiers_used:
                    add_entry(parser, rda_table, parent_id, used=identifier)

        elif root_node.type == "for_statement":
            parent_id = get_index(root_node, index)
            if parent_id is None or parent_id not in CFG_results.graph.nodes:
                continue

            condition = root_node.child_by_field_name("condition")
            if condition:
                identifiers_used = recursively_get_children_of_types(
                    condition,
                    variable_type + ["field_expression"],
                    index=parser.index,
                    check_list=parser.symbol_table["scope_map"],
                )
                for identifier in identifiers_used:
                    add_entry(parser, rda_table, parent_id, used=identifier)

        elif root_node.type == "while_statement":
            parent_id = get_index(root_node, index)
            if parent_id is None or parent_id not in CFG_results.graph.nodes:
                continue

            condition = root_node.child_by_field_name("condition")
            if condition:
                identifiers_used = recursively_get_children_of_types(
                    condition,
                    variable_type + ["field_expression"],
                    index=parser.index,
                    check_list=parser.symbol_table["scope_map"],
                )
                for identifier in identifiers_used:
                    add_entry(parser, rda_table, parent_id, used=identifier)

        elif (
            root_node.type == "parenthesized_expression"
            and root_node.parent is not None
            and root_node.parent.type == "do_statement"
        ):
            parent_id = get_index(root_node, index)
            if parent_id is None or parent_id not in CFG_results.graph.nodes:
                continue

            identifiers_used = recursively_get_children_of_types(
                root_node,
                variable_type + ["field_expression"],
                index=parser.index,
                check_list=parser.symbol_table["scope_map"],
            )
            for identifier in identifiers_used:
                add_entry(parser, rda_table, parent_id, used=identifier)

        elif root_node.type == "do_statement":
            pass

        elif root_node.type == "if_statement":
            parent_id = get_index(root_node, index)
            if parent_id is None or parent_id not in CFG_results.graph.nodes:
                continue

            condition = root_node.child_by_field_name("condition")
            if condition:
                identifiers_used = recursively_get_children_of_types(
                    condition,
                    variable_type + ["field_expression"],
                    index=parser.index,
                    check_list=parser.symbol_table["scope_map"],
                )
                for identifier in identifiers_used:
                    add_entry(parser, rda_table, parent_id, used=identifier)

        elif root_node.type == "conditional_expression":
            parent_statement = return_first_parent_of_types(
                root_node, statement_types["node_list_type"]
            )
            if parent_statement is None:
                continue

            parent_id = get_index(parent_statement, index)
            if parent_id is None or parent_id not in CFG_results.graph.nodes:
                continue

            condition = root_node.child_by_field_name("condition")
            if condition:
                if condition.type in variable_type + ["field_expression"]:
                    add_entry(parser, rda_table, parent_id, used=condition)
                else:
                    identifiers_used = recursively_get_children_of_types(
                        condition,
                        variable_type + ["field_expression"],
                        index=parser.index,
                        check_list=parser.symbol_table["scope_map"],
                    )
                    for identifier in identifiers_used:
                        add_entry(parser, rda_table, parent_id, used=identifier)
                    literals_used = recursively_get_children_of_types(
                        condition, literal_types, index=parser.index
                    )
                    for literal in literals_used:
                        add_entry(parser, rda_table, parent_id, used=literal)

            consequence = root_node.child_by_field_name("consequence")
            if consequence:
                if consequence.type in variable_type + ["field_expression"]:
                    add_entry(parser, rda_table, parent_id, used=consequence)
                else:
                    identifiers_used = recursively_get_children_of_types(
                        consequence,
                        variable_type + ["field_expression"],
                        index=parser.index,
                        check_list=parser.symbol_table["scope_map"],
                    )
                    for identifier in identifiers_used:
                        add_entry(parser, rda_table, parent_id, used=identifier)
                    literals_used = recursively_get_children_of_types(
                        consequence, literal_types, index=parser.index
                    )
                    for literal in literals_used:
                        add_entry(parser, rda_table, parent_id, used=literal)

            alternative = root_node.child_by_field_name("alternative")
            if alternative:
                if alternative.type in variable_type + ["field_expression"]:
                    add_entry(parser, rda_table, parent_id, used=alternative)
                else:
                    identifiers_used = recursively_get_children_of_types(
                        alternative,
                        variable_type + ["field_expression"],
                        index=parser.index,
                        check_list=parser.symbol_table["scope_map"],
                    )
                    for identifier in identifiers_used:
                        add_entry(parser, rda_table, parent_id, used=identifier)
                    literals_used = recursively_get_children_of_types(
                        alternative, literal_types, index=parser.index
                    )
                    for literal in literals_used:
                        add_entry(parser, rda_table, parent_id, used=literal)

        else:
            if root_node.type not in variable_type:
                continue

            in_do_while_condition = False
            temp_parent = root_node.parent
            while temp_parent is not None:
                if (
                    temp_parent.type == "parenthesized_expression"
                    and temp_parent.parent is not None
                    and temp_parent.parent.type == "do_statement"
                ):
                    in_do_while_condition = True
                    break
                temp_parent = temp_parent.parent

            if in_do_while_condition:
                continue

            handled_types = (
                def_statement
                + assignment
                + increment_statement
                + function_calls
                + ["return_statement"]
            )
            parent_statement = return_first_parent_of_types(
                root_node,
                statement_types["non_control_statement"]
                + statement_types["control_statement"],
                stop_types=statement_types.get("statement_holders", []) + handled_types,
            )

            if parent_statement is None:
                continue

            parent_id = get_index(parent_statement, index)
            if parent_id is None or parent_id not in CFG_results.graph.nodes:
                continue

            immediate_parent = root_node.parent
            if immediate_parent and immediate_parent.type == "pointer_expression":
                continue

            add_entry(parser, rda_table, parent_id, used=root_node)

    return rda_table


def start_rda(index, rda_table, cfg_graph, pre_solve=False):
    """
    Perform Reaching Definitions Analysis.

    Fixed-point iteration algorithm:
        Initialize all IN/OUT to empty
        Repeat until convergence:
            For each statement s:
                IN[s] = union of OUT[p] for predecessors p
                OUT[s] = (IN[s] - KILL[s]) ∪ DEF[s]
    """
    graph = copy.deepcopy(cfg_graph)
    if pre_solve:
        remove_edges = []
        for edge in graph.edges:
            edge_data = graph.edges[edge]
            if "label" in edge_data and edge_data["label"] in [
                "function_call",
                "function_return",
            ]:
                remove_edges.append(edge)
        graph.remove_edges_from(remove_edges)

    cfg = graph
    nodes = graph.nodes

    old_result = {}
    for node in nodes:
        old_result[node] = {"IN": set(), "OUT": set()}

    new_result = copy.deepcopy(old_result)
    iteration = 0

    while True:
        iteration += 1

        for node in nodes:
            predecessors = [s for (s, t) in cfg.in_edges(node)]

            in_set = set()
            for pred in predecessors:
                in_set = in_set.union(old_result[pred]["OUT"])

            new_result[node]["IN"] = in_set

            def_info = rda_table[node]["def"] if node in rda_table else set()
            names_defined = [d.name for d in def_info]

            surviving_defs = set()
            for incoming_def in in_set:
                if incoming_def.name not in names_defined:
                    surviving_defs.add(incoming_def)

            new_result[node]["OUT"] = surviving_defs.union(def_info)

        ddiff = DeepDiff(old_result, new_result, ignore_order=True)
        if ddiff == {}:
            if debug:
                logger.info("RDA: Converged in {} iterations", iteration)
            break

        old_result = copy.deepcopy(new_result)

    return new_result


def add_edge(final_graph, source, target, attrib=None):
    """Add edge to graph with attributes, preventing duplicates"""
    if attrib is not None:
        used_def = attrib.get("used_def", None)
        edge_type = attrib.get("edge_type", None)
        dataflow_type = attrib.get("dataflow_type", None)

        for u, v, k, data in final_graph.edges(keys=True, data=True):
            if (
                u == source
                and v == target
                and data.get("used_def") == used_def
                and data.get("edge_type") == edge_type
                and data.get("dataflow_type") == dataflow_type
            ):
                return

    final_graph.add_edge(source, target)
    if attrib is not None:
        edge_keys = [
            k for u, v, k in final_graph.edges(keys=True) if u == source and v == target
        ]
        if edge_keys:
            edge_key = max(edge_keys)
        else:
            edge_key = 0
        nx.set_edge_attributes(final_graph, {(source, target, edge_key): attrib})


def name_match_with_fields(name1, name2):
    """Check if two names match (handling struct fields)"""
    if name1 == name2:
        return True

    if name1.startswith(name2 + ".") or name2.startswith(name1 + "."):
        return True

    return False


def get_required_edges_from_def_to_use(
    index, cfg, rda_solution, rda_table, graph_nodes, processed_edges, properties
):
    """
    Generate DFG edges from RDA solution.

    For each statement s:
        For each use u in USE[s]:
            For each def d in IN[s]:
                If d.name == u.name and scope_check(d.scope, u.scope):
                    Add edge: d.line → s
    """
    final_graph = copy.deepcopy(cfg)
    final_graph.remove_edges_from(list(final_graph.edges()))

    for node in graph_nodes:
        if node not in rda_table:
            continue

        use_info = rda_table[node]["use"]

        for used in use_info:
            if isinstance(used, Literal):
                used.satisfied = True
                continue

            for available_def in rda_solution[node]["IN"]:
                if available_def.name == used.name:
                    if scope_check(available_def.scope, used.scope):
                        add_edge(
                            final_graph,
                            available_def.line,
                            node,
                            {
                                "dataflow_type": "comesFrom",
                                "edge_type": "DFG_edge",
                                "color": "#00A3FF",
                                "used_def": used.name,
                            },
                        )
                        used.satisfied = True

                elif "." in used.name or "." in available_def.name:
                    if name_match_with_fields(used.name, available_def.name):
                        if scope_check(available_def.scope, used.scope):
                            add_edge(
                                final_graph,
                                available_def.line,
                                node,
                                {
                                    "dataflow_type": "comesFrom",
                                    "edge_type": "DFG_edge",
                                    "color": "#00A3FF",
                                    "used_def": used.name,
                                },
                            )
                            used.satisfied = True

            if not used.satisfied:
                for def_node in graph_nodes:
                    if def_node not in rda_table:
                        continue
                    for definition in rda_table[def_node]["def"]:
                        if definition.name == used.name:
                            node_type = (
                                read_index(index, def_node)[-1]
                                if def_node in index.values()
                                else None
                            )
                            if node_type == "function_definition":
                                add_edge(
                                    final_graph,
                                    def_node,
                                    node,
                                    {
                                        "dataflow_type": "comesFrom",
                                        "edge_type": "DFG_edge",
                                        "color": "#00A3FF",
                                        "used_def": used.name,
                                    },
                                )
                                used.satisfied = True
                                break

        if properties.get("last_def", False):
            killed_defs = rda_solution[node]["IN"] - rda_solution[node]["OUT"]
            for killed_def in killed_defs:
                node_type = read_index(index, node)[-1]
                def_node_type = read_index(index, killed_def.line)[-1]
                ignore_types = [
                    "for_statement",
                    "while_statement",
                    "if_statement",
                    "switch_statement",
                ]
                if node_type not in ignore_types and def_node_type not in ignore_types:
                    add_edge(
                        final_graph,
                        killed_def.line,
                        node,
                        {"color": "orange", "dataflow_type": "lastDef"},
                    )

    for edge in processed_edges:
        add_edge(
            final_graph,
            edge[0],
            edge[1],
            {"dataflow_type": "parameter", "edge_type": "DFG_edge"},
        )

    return final_graph


def rda_cfg_map(rda_solution, CFG_results):
    """Create debug graph showing RDA info on CFG edges"""
    graph = copy.deepcopy(CFG_results.graph)

    for edge in list(graph.edges):
        out_set = rda_solution[edge[0]]["OUT"]
        in_set = rda_solution[edge[1]]["IN"]

        intersection = [d for d in out_set if d in in_set]

        if intersection:
            edge_data = graph.get_edge_data(*edge)
            edge_data["rda_info"] = ",".join([str(d) for d in intersection])
        else:
            graph.remove_edge(*edge)

    return graph


def collect_call_site_information(parser, function_metadata, cfg_graph):
    """
    Collect information about function call sites for interprocedural analysis.

    For each call site, track:
    - Which function is called
    - Which arguments are passed by reference (&var)
    - The mapping of actual arguments to formal parameters

    Returns:
        List of dicts with call site information:
        {
            "call_site_node": AST node,
            "call_site_id": CFG node ID,
            "function_name": str,
            "pass_by_ref_args": [(arg_idx, var_name, var_node), ...]
        }
    """
    call_sites = []
    index = parser.index

    for node in traverse_tree(parser.tree.root_node):
        if node.type == "call_expression":
            function_name = None
            if node.children and node.children[0].type == "identifier":
                function_name = st(node.children[0])

            if not function_name or function_name not in function_metadata:
                continue

            parent_statement = return_first_parent_of_types(
                node, statement_types["node_list_type"]
            )
            if not parent_statement:
                continue

            call_site_id = get_index(parent_statement, index)
            if call_site_id is None or call_site_id not in cfg_graph.nodes:
                continue

            pass_by_ref_args = []
            for child in node.children[1:]:
                if child.type == "argument_list":
                    func_params = function_metadata[function_name]["params"]

                    for arg_idx, arg in enumerate(child.named_children):
                        if arg_idx < len(func_params):
                            param_name, is_pointer, param_idx = func_params[arg_idx]

                            if is_pointer:
                                if arg.type == "pointer_expression":
                                    has_ampersand = False
                                    arg_node = None
                                    for arg_child in arg.children:
                                        if arg_child.type == "&":
                                            has_ampersand = True
                                        elif arg_child.is_named:
                                            arg_node = arg_child

                                    if has_ampersand and arg_node:
                                        if arg_node.type == "identifier":
                                            var_name = st(arg_node)
                                            pass_by_ref_args.append(
                                                (arg_idx, var_name, arg_node)
                                            )
                                elif arg.type == "identifier":
                                    var_name = st(arg)
                                    arg_index = get_index(arg, index)
                                    if (
                                        arg_index
                                        and arg_index
                                        in parser.symbol_table["scope_map"]
                                    ):
                                        pass_by_ref_args.append(
                                            (arg_idx, var_name, arg)
                                        )

            if pass_by_ref_args:
                call_sites.append(
                    {
                        "call_site_node": node,
                        "call_site_id": call_site_id,
                        "function_name": function_name,
                        "pass_by_ref_args": pass_by_ref_args,
                    }
                )

    return call_sites


def find_modification_sites(parser, function_metadata, pointer_modifications):
    """
    Find all modification sites for pointer parameters inside functions.

    For each function, find all statements where a pointer parameter is modified.

    Returns:
        Dict mapping function_name -> list of (param_idx, modification_node, statement_id)
    """
    modification_sites = {}
    index = parser.index

    for func_name, meta in function_metadata.items():
        modifications = []
        func_node = meta["node"]
        modified_params = pointer_modifications.get(func_name, set())

        param_name_to_idx = {}
        for param_name, is_pointer, param_idx in meta["params"]:
            if is_pointer and param_idx in modified_params:
                param_name_to_idx[param_name] = param_idx

        if not param_name_to_idx:
            modification_sites[func_name] = modifications
            continue

        for node in traverse_tree(func_node):
            modification_param_idx = None
            mod_node = None

            if node.type == "assignment_expression":
                left = node.child_by_field_name("left")
                if left:
                    if left.type == "pointer_expression":
                        arg = left.child_by_field_name("argument")
                        if arg and arg.type == "identifier":
                            var_name = st(arg)
                            if var_name in param_name_to_idx:
                                modification_param_idx = param_name_to_idx[var_name]
                                mod_node = node

                    elif left.type == "subscript_expression":
                        array_arg = left.child_by_field_name("argument")
                        if array_arg and array_arg.type == "identifier":
                            var_name = st(array_arg)
                            if var_name in param_name_to_idx:
                                modification_param_idx = param_name_to_idx[var_name]
                                mod_node = node

            elif node.type == "update_expression":
                arg = node.child_by_field_name("argument")
                if arg:
                    if arg.type == "parenthesized_expression":
                        inner_children = [c for c in arg.named_children if c.is_named]
                        if inner_children:
                            arg = inner_children[0]

                    if arg.type == "pointer_expression":
                        inner_arg = arg.child_by_field_name("argument")
                        if inner_arg and inner_arg.type == "identifier":
                            var_name = st(inner_arg)
                            if var_name in param_name_to_idx:
                                modification_param_idx = param_name_to_idx[var_name]
                                mod_node = node
                    elif arg.type == "subscript_expression":
                        array_arg = arg.child_by_field_name("argument")
                        if array_arg and array_arg.type == "identifier":
                            var_name = st(array_arg)
                            if var_name in param_name_to_idx:
                                modification_param_idx = param_name_to_idx[var_name]
                                mod_node = node

            if modification_param_idx is not None and mod_node is not None:
                parent_statement = return_first_parent_of_types(
                    mod_node, statement_types["node_list_type"]
                )
                if parent_statement:
                    statement_id = get_index(parent_statement, index)
                    if statement_id is not None:
                        modifications.append(
                            (modification_param_idx, mod_node, statement_id)
                        )

        modification_sites[func_name] = modifications

    return modification_sites


def add_interprocedural_edges(
    final_graph,
    parser,
    call_sites,
    modification_sites,
    function_metadata,
    cfg_graph,
    rda_table,
):
    """
    Add interprocedural DFG edges for pass-by-reference.

    For each call site where &var is passed to a pointer parameter:
    1. Add edge from call site to function definition (argument-parameter binding)
    2. Add edges from modification sites inside function to uses after the call

    Args:
        final_graph: The DFG graph to add edges to
        parser: C parser
        call_sites: List of call site information from collect_call_site_information()
        modification_sites: Dict from find_modification_sites()
        function_metadata: Dict from collect_function_metadata()
        cfg_graph: Control flow graph
        rda_table: RDA table with def/use information
    """
    index = parser.index

    for call_site_info in call_sites:
        call_site_id = call_site_info["call_site_id"]
        function_name = call_site_info["function_name"]
        pass_by_ref_args = call_site_info["pass_by_ref_args"]

        if (
            function_name not in function_metadata
            or function_name not in modification_sites
        ):
            continue

        func_meta = function_metadata[function_name]
        func_node = func_meta["node"]
        func_def_id = get_index(func_node, index)

        if func_def_id is None:
            continue

        for arg_idx, var_name, var_node in pass_by_ref_args:
            add_edge(
                final_graph,
                call_site_id,
                func_def_id,
                {
                    "dataflow_type": "comesFrom",
                    "edge_type": "DFG_edge",
                    "color": "#00A3FF",
                    "used_def": var_name,
                    "interprocedural": "call_to_function",
                },
            )

            mods = modification_sites.get(function_name, [])
            for mod_param_idx, mod_node, mod_statement_id in mods:
                if mod_param_idx == arg_idx:
                    successors = []
                    visited = set()
                    queue = [call_site_id]

                    while queue:
                        current = queue.pop(0)
                        if current in visited:
                            continue
                        visited.add(current)

                        uses_var = False
                        defines_var = False
                        if current != call_site_id and current in rda_table:
                            for used in rda_table[current]["use"]:
                                if used.name == var_name:
                                    uses_var = True
                                    successors.append(current)
                                    break

                            for defined in rda_table[current]["def"]:
                                if defined.name == var_name:
                                    defines_var = True
                                    break

                        if (
                            current == call_site_id
                            or not uses_var
                            or (uses_var and defines_var)
                        ):
                            for edge in cfg_graph.out_edges(current):
                                if edge[1] not in visited:
                                    queue.append(edge[1])

                    for use_site in successors:
                        add_edge(
                            final_graph,
                            mod_statement_id,
                            use_site,
                            {
                                "dataflow_type": "comesFrom",
                                "edge_type": "DFG_edge",
                                "color": "#00A3FF",
                                "used_def": var_name,
                                "interprocedural": "modification_to_use",
                            },
                        )


def dfg_c(properties, CFG_results):
    """
    Main driver for generating DFG for C programs.

    Args:
        properties: Configuration dict with DFG options
        CFG_results: CFG driver results with graph, parser, etc.

    Returns:
        (final_graph, debug_graph, rda_table, rda_solution)
    """
    parser = CFG_results.parser
    index = parser.index
    tree = parser.tree

    cfg_graph = copy.deepcopy(CFG_results.graph)
    # Mark DFG nodes with distinct source / colour (overwrites the CFG defaults)
    for nid in cfg_graph.nodes():
        cfg_graph.nodes[nid]["node_type"] = "DFG"
        cfg_graph.nodes[nid]["fillcolor"] = "#F5E0C6"
        cfg_graph.nodes[nid]["color"] = "#C98A5A"
    node_list = CFG_results.node_list

    processed_edges = []
    for edge in list(cfg_graph.edges()):
        edge_data = cfg_graph.get_edge_data(*edge)
        if edge_data and len(edge_data) > 0:
            edge_data = edge_data[0]
            if edge_data.get("label") == "function_return":
                return_statement = node_list.get(read_index(index, edge[0]))
                call_site_node = node_list.get(read_index(index, edge[1]))

                if return_statement and return_statement.type == "return_statement":
                    if return_statement.named_children:
                        if call_site_node and is_return_value_used(call_site_node):
                            processed_edges.append(edge)

    function_metadata = collect_function_metadata(parser)
    pointer_modifications = analyze_pointer_modifications(parser, function_metadata)

    start_rda_init_time = time.time()
    rda_table = build_rda_table(
        parser, CFG_results, function_metadata, pointer_modifications
    )
    end_rda_init_time = time.time()

    start_rda_time = time.time()
    rda_solution = start_rda(index, rda_table, cfg_graph, pre_solve=True)
    end_rda_time = time.time()

    final_graph = get_required_edges_from_def_to_use(
        index,
        cfg_graph,
        rda_solution,
        rda_table,
        cfg_graph.nodes,
        processed_edges,
        properties,
    )

    call_sites = collect_call_site_information(parser, function_metadata, cfg_graph)
    modification_sites = find_modification_sites(
        parser, function_metadata, pointer_modifications
    )
    add_interprocedural_edges(
        final_graph,
        parser,
        call_sites,
        modification_sites,
        function_metadata,
        cfg_graph,
        rda_table,
    )

    if debug:
        logger.info(
            "RDA init: {:.3f}s, RDA: {:.3f}s",
            end_rda_init_time - start_rda_init_time,
            end_rda_time - start_rda_time,
        )

    debug_graph = rda_cfg_map(rda_solution, CFG_results)

    return final_graph, debug_graph, rda_table, rda_solution
