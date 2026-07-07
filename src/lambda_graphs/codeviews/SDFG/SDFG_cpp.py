import copy
import time
from collections import defaultdict

import networkx as nx
from deepdiff import DeepDiff
from loguru import logger

from ...utils.cpp_nodes import statement_types
from ...utils.src_parser import traverse_tree

assignment = ["assignment_expression"]
def_statement = ["init_declarator"]
declaration_statement = ["declaration"]
increment_statement = ["update_expression"]
variable_type = ["identifier", "this", "qualified_identifier"]
function_calls = ["call_expression"]
method_calls = ["call_expression"]
literal_types = [
    "number_literal",
    "string_literal",
    "char_literal",
    "raw_string_literal",
    "true",
    "false",
    "nullptr",
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
    "cin",
    "std::cin",
]
inner_types = ["declaration", "expression_statement"]
handled_types = (
    assignment
    + def_statement
    + increment_statement
    + function_calls
    + [
        "function_definition",
        "return_statement",
        "for_statement",
        "for_range_loop",
        "switch_statement",
    ]
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


def is_node_inside_loop(ast_node):
    """
    Check if an AST node is inside a loop structure.

    Args:
        ast_node: AST node to check

    Returns:
        True if node is inside a loop (for/while/do-while), False otherwise
    """
    if ast_node is None:
        return False

    current = ast_node
    while current.parent is not None:
        if current.parent.type in [
            "for_statement",
            "while_statement",
            "do_statement",
            "for_range_loop",
        ]:
            return True
        current = current.parent
    return False


def get_loop_condition_node(ast_node, parser):
    """
    Get the loop condition CFG node for a node inside a loop body.

    Args:
        ast_node: AST node inside a loop body
        parser: Parser with index

    Returns:
        Tuple (is_in_loop_body, loop_condition_id):
        - is_in_loop_body: True if node is inside a loop body
        - loop_condition_id: CFG node ID of the loop condition, or None
    """
    if ast_node is None:
        return False, None

    current = ast_node
    while current.parent is not None:
        parent_type = current.parent.type

        if parent_type in [
            "for_statement",
            "while_statement",
            "do_statement",
            "for_range_loop",
        ]:
            loop_condition_id = get_index(current.parent, parser.index)
            return True, loop_condition_id

        current = current.parent

    return False, None


def get_variable_type(parser, node):
    """
    Get the type of a variable from parser's symbol table.

    Args:
        parser: C++ parser with symbol table
        node: AST node representing the variable

    Returns:
        String representing the type, or None if not found
    """
    var_index = get_index(node, parser.index)
    if var_index is None:
        return None

    if var_index in parser.declaration_map:
        decl_index = parser.declaration_map[var_index]
        if decl_index in parser.symbol_table.get("data_type", {}):
            return parser.symbol_table["data_type"][decl_index]

    if var_index in parser.symbol_table.get("data_type", {}):
        return parser.symbol_table["data_type"][var_index]

    return None


def is_primitive_type(type_string):
    """
    Check if a type string represents a C++ primitive type.

    Args:
        type_string: String representing the type

    Returns:
        True if primitive, False otherwise
    """
    if type_string is None:
        return False

    primitive_types = {
        "int",
        "short",
        "long",
        "char",
        "wchar_t",
        "char8_t",
        "char16_t",
        "char32_t",
        "signed",
        "unsigned",
        "int8_t",
        "int16_t",
        "int32_t",
        "int64_t",
        "uint8_t",
        "uint16_t",
        "uint32_t",
        "uint64_t",
        "int_fast8_t",
        "int_fast16_t",
        "int_fast32_t",
        "int_fast64_t",
        "uint_fast8_t",
        "uint_fast16_t",
        "uint_fast32_t",
        "uint_fast64_t",
        "int_least8_t",
        "int_least16_t",
        "int_least32_t",
        "int_least64_t",
        "uint_least8_t",
        "uint_least16_t",
        "uint_least32_t",
        "uint_least64_t",
        "intmax_t",
        "uintmax_t",
        "intptr_t",
        "uintptr_t",
        "size_t",
        "ssize_t",
        "ptrdiff_t",
        "float",
        "double",
        "bool",
        "void",
        "DWORD",
        "WORD",
        "BYTE",
    }

    type_clean = (
        type_string.strip().replace("const", "").replace("volatile", "").strip()
    )

    if type_clean in primitive_types:
        return True

    tokens = type_clean.split()
    if all(token in primitive_types for token in tokens):
        return True

    for prim in primitive_types:
        if prim in type_clean:
            if type_clean == prim or type_clean.startswith(prim + " "):
                return True

    return False


def is_class_or_struct_type(parser, type_string):
    """
    Check if a type string represents a class or struct type.

    Args:
        parser: C++ parser with symbol table
        type_string: String representing the type

    Returns:
        True if class/struct, False otherwise
    """
    if type_string is None:
        return False

    if not is_primitive_type(type_string):
        if hasattr(parser, "records") and type_string in parser.records:
            return True

        if "std::" in type_string or "::" in type_string:
            return True

        return True

    return False


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
            if (
                "qualified_identifier" in st_types
                and child.type == "qualified_identifier"
            ):
                continue
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

    def __init__(
        self,
        parser,
        node,
        line=None,
        declaration=False,
        full_ref=None,
        method_call=False,
        has_initializer=False,
        is_pointer_modification_at_call_site=False,
    ):
        self.core = st(node)
        self.unresolved_name = st(full_ref) if full_ref else st(node)
        self.base_name = self._resolve_name(node, full_ref, parser)
        self.name = self.base_name
        self.line = line
        self.declaration = declaration
        self.has_initializer = has_initializer
        self.method_call = method_call
        self.is_pointer_modification_at_call_site = is_pointer_modification_at_call_site
        if method_call and node.type == "qualified_identifier":
            self.satisfied = False
        else:
            self.satisfied = method_call

        class_node = return_first_parent_of_types(
            node, ["class_specifier", "struct_specifier"]
        )
        self.parent_class = None
        self.is_member_access = False

        if class_node is not None:
            class_name_node = None
            for child in class_node.children:
                if child.type == "type_identifier":
                    class_name_node = child
                    break
            if class_name_node:
                self.parent_class = st(class_name_node)

                parent = node.parent
                while parent and parent != class_node:
                    if parent.type == "function_definition":
                        if full_ref is None or full_ref.type not in [
                            "field_expression",
                            "pointer_expression",
                        ]:
                            self.is_member_access = True
                        break
                    parent = parent.parent

        variable_index = get_index(node, parser.index)

        if hasattr(node, "qualified_name"):
            if hasattr(node, "real_node"):
                variable_index = get_index(node.real_node, parser.index)

        if variable_index is None and node.type == "qualified_identifier":
            innermost = extract_identifier_from_declarator(node)
            if innermost:
                variable_index = get_index(innermost, parser.index)

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
            if line and line in parser.symbol_table.get("scope_map", {}):
                self.variable_scope = parser.symbol_table["scope_map"][line]
                self.scope = self.variable_scope
            elif line:
                self.variable_scope = [0, 11, 12]
                self.scope = [0]
            else:
                self.variable_scope = [0]
                self.scope = [0]

        if line is not None:
            self.real_line_no = read_index(parser.index, line)[0][0]

        if self.is_member_access and self.parent_class:
            self.name = f"{self.parent_class}::{self.base_name}"

    def _resolve_name(self, node, full_ref, parser):
        """Resolve identifier name for C++"""
        if full_ref is None:
            return st(node)

        if full_ref.type == "field_expression":
            argument = full_ref.child_by_field_name("argument")
            field = full_ref.child_by_field_name("field")

            if argument:
                arg_text = st(argument)
                field_text = st(field) if field else ""
                return arg_text + "." + field_text
            return st(full_ref)

        if full_ref.type == "pointer_expression":
            arg = full_ref.child_by_field_name("argument")
            return "*" + st(arg) if arg else st(full_ref)

        if full_ref.type == "subscript_expression":
            arg = full_ref.child_by_field_name("argument")
            return st(arg) if arg else st(full_ref)

        if full_ref.type == "unary_expression":
            for child in full_ref.children:
                if child.type == "&":
                    arg = full_ref.child_by_field_name("argument")
                    return st(arg) if arg else st(full_ref)

        if full_ref.type == "qualified_identifier":
            qualified_text = st(full_ref)
            if "::" in qualified_text:
                return qualified_text.split("::")[-1]
            return qualified_text

        if st(node) == "this":
            return "this"

        return st(node)

    def __eq__(self, other):
        return (
            self.name == other.name
            and self.line == other.line
            and sorted(self.scope) == sorted(other.scope)
            and self.method_call == other.method_call
        )

    def __hash__(self):
        return hash((self.name, self.line, str(self.scope), self.method_call))

    def __str__(self):
        result = [self.name]
        if self.line:
            result += [str(self.real_line_no)]
            result += ["|".join(map(str, self.scope))]
        else:
            result += ["?"]
        if self.method_call:
            result += ["()"]
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
        self.method_call = False

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


def get_namespace_for_node(node, parser):
    """
    Get the namespace that contains this node, if any.

    Returns the namespace name or None if not in a namespace.
    """
    parent = node.parent
    while parent:
        if parent.type == "namespace_definition":
            for child in parent.children:
                if child.type == "namespace_identifier":
                    return st(child)
        parent = parent.parent
    return None


def extract_identifier_from_declarator(declarator_node):
    """Extract identifier from declarator (may be wrapped in pointer/array/reference/qualified)"""
    if declarator_node.type == "identifier":
        return declarator_node
    elif declarator_node.type == "qualified_identifier":
        for child in declarator_node.children:
            if child.type in ["identifier", "qualified_identifier"]:
                result = extract_identifier_from_declarator(child)
                if result:
                    return result
        return None
    elif declarator_node.type == "pointer_declarator":
        for child in declarator_node.children:
            if child.type in [
                "identifier",
                "pointer_declarator",
                "array_declarator",
                "reference_declarator",
                "qualified_identifier",
            ]:
                return extract_identifier_from_declarator(child)
    elif declarator_node.type == "reference_declarator":
        for child in declarator_node.children:
            if child.type in [
                "identifier",
                "pointer_declarator",
                "array_declarator",
                "reference_declarator",
                "qualified_identifier",
            ]:
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
                "qualified_identifier",
            ]:
                return extract_identifier_from_declarator(child)
    elif declarator_node.type == "parenthesized_declarator":
        for child in declarator_node.children:
            if child.type in [
                "identifier",
                "pointer_declarator",
                "array_declarator",
                "reference_declarator",
                "qualified_identifier",
            ]:
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
            "reference_declarator",
        ]:
            return extract_identifier_from_declarator(child)
    return None


def is_reference_variable(parser, node):
    if node is None or node.type not in ["identifier"]:
        return False

    var_index = get_index(node, parser.index)
    if var_index is None:
        return False

    if var_index not in parser.declaration_map:
        return False

    decl_index = parser.declaration_map[var_index]

    def find_node_by_index(root, target_index):
        stack = [root]
        while stack:
            current = stack.pop()
            node_idx = get_index(current, parser.index)
            if node_idx == target_index:
                return current
            for child in current.children:
                stack.append(child)
        return None

    decl_node = find_node_by_index(parser.tree.root_node, decl_index)

    if decl_node:
        parent = decl_node.parent
        depth = 0
        while parent and depth < 5:
            if parent.type == "reference_declarator":
                return True
            if parent.type in [
                "parameter_declaration",
                "declaration",
                "function_definition",
                "translation_unit",
            ]:
                break
            depth += 1
            parent = parent.parent

    return False


def extract_operator_text(assign_node, left_node, right_node):
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
    method_call=False,
    has_initializer=False,
    is_pointer_modification_at_call_site=False,
):
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

    if hasattr(current_node, "qualified_name"):
        if defined is not None:
            identifier = Identifier(
                parser,
                current_node,
                statement_id,
                full_ref=current_node,
                declaration=declaration,
                method_call=method_call,
                has_initializer=has_initializer,
            )
            identifier.name = current_node.qualified_name
            set_add(rda_table[statement_id]["def"], identifier)
        return

    if current_node.type == "field_expression":
        argument = current_node.child_by_field_name("argument")

        is_method_call = (
            current_node.parent and current_node.parent.type == "call_expression"
        )

        if is_method_call:
            if defined is not None:
                set_add(
                    rda_table[statement_id]["def"],
                    Identifier(
                        parser,
                        argument,
                        statement_id,
                        full_ref=current_node,
                        declaration=declaration,
                        method_call=True,
                        has_initializer=has_initializer,
                    ),
                )
            else:
                set_add(
                    rda_table[statement_id]["use"],
                    Identifier(
                        parser, argument, full_ref=current_node, method_call=True
                    ),
                )
            return

        if defined is not None:
            if argument:
                set_add(
                    rda_table[statement_id]["def"],
                    Identifier(
                        parser,
                        argument,
                        statement_id,
                        full_ref=None,
                        declaration=declaration,
                        method_call=method_call,
                        has_initializer=has_initializer,
                    ),
                )
        else:
            if argument:
                set_add(
                    rda_table[statement_id]["use"],
                    Identifier(
                        parser, argument, full_ref=None, method_call=method_call
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
        is_address_of = False
        is_dereference = False

        if current_node.children:
            operator = current_node.children[0]
            if operator.type == "&":
                is_address_of = True
            elif operator.type == "*":
                is_dereference = True

        pointer = current_node.child_by_field_name("argument")

        if is_address_of:
            if pointer and pointer.type in variable_type:
                pointer_index = get_index(pointer, parser.index)
                if pointer_index and pointer_index in parser.symbol_table["scope_map"]:
                    set_add(
                        rda_table[statement_id]["use"],
                        Identifier(parser, pointer, full_ref=pointer),
                    )
            return

        elif is_dereference:
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
                        has_initializer=has_initializer,
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

        if index_expr is None:
            for child in current_node.children:
                if child.type == "subscript_argument_list":
                    if child.named_children:
                        index_expr = child.named_children[0]
                    break

        if defined is not None:
            set_add(
                rda_table[statement_id]["def"],
                Identifier(
                    parser,
                    array,
                    statement_id,
                    full_ref=core,
                    declaration=declaration,
                    has_initializer=has_initializer,
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

    if current_node.type == "qualified_identifier":
        innermost_id = extract_identifier_from_declarator(current_node)

        if method_call:
            if defined is not None:
                set_add(
                    rda_table[statement_id]["def"],
                    Identifier(
                        parser,
                        current_node,
                        statement_id,
                        full_ref=current_node,
                        declaration=declaration,
                        method_call=method_call,
                        has_initializer=has_initializer,
                    ),
                )
            else:
                set_add(
                    rda_table[statement_id]["use"],
                    Identifier(
                        parser,
                        current_node,
                        statement_id,
                        full_ref=current_node,
                        method_call=method_call,
                    ),
                )
            return

        if innermost_id is None:
            return

        node_index = get_index(innermost_id, parser.index)
        if node_index is None or node_index not in parser.symbol_table["scope_map"]:
            if defined is not None:
                set_add(
                    rda_table[statement_id]["def"],
                    Identifier(
                        parser,
                        current_node,
                        statement_id,
                        full_ref=current_node,
                        declaration=declaration,
                        method_call=method_call,
                        has_initializer=has_initializer,
                    ),
                )
            else:
                set_add(
                    rda_table[statement_id]["use"],
                    Identifier(
                        parser,
                        current_node,
                        statement_id,
                        full_ref=current_node,
                        method_call=method_call,
                    ),
                )
            return

        if defined is not None:
            set_add(
                rda_table[statement_id]["def"],
                Identifier(
                    parser,
                    innermost_id,
                    statement_id,
                    full_ref=current_node,
                    declaration=declaration,
                    method_call=method_call,
                    has_initializer=has_initializer,
                ),
            )
        else:
            set_add(
                rda_table[statement_id]["use"],
                Identifier(
                    parser, innermost_id, full_ref=current_node, method_call=method_call
                ),
            )
        return

    if current_node.type == "this":
        if used:
            set_add(
                rda_table[statement_id]["use"],
                Identifier(parser, current_node, full_ref=current_node),
            )
        return

    node_index = get_index(current_node, parser.index)
    if node_index is None or node_index not in parser.symbol_table["scope_map"]:
        if defined is not None:
            set_add(
                rda_table[statement_id]["def"],
                Identifier(
                    parser,
                    defined,
                    statement_id,
                    full_ref=core,
                    declaration=declaration,
                    method_call=method_call,
                    has_initializer=has_initializer,
                ),
            )
        else:
            set_add(
                rda_table[statement_id]["use"],
                Identifier(
                    parser, used, statement_id, full_ref=core, method_call=method_call
                ),
            )
        return

    if defined is not None:
        set_add(
            rda_table[statement_id]["def"],
            Identifier(
                parser,
                defined,
                statement_id,
                full_ref=core,
                declaration=declaration,
                method_call=method_call,
                has_initializer=has_initializer,
                is_pointer_modification_at_call_site=is_pointer_modification_at_call_site,
            ),
        )
    else:
        set_add(
            rda_table[statement_id]["use"],
            Identifier(
                parser, used, statement_id, full_ref=core, method_call=method_call
            ),
        )


def discover_lambdas(parser, CFG_results):
    lambda_map = {}
    index = parser.index
    tree = parser.tree
    cfg_nodes = CFG_results.graph.nodes

    for node in traverse_tree(tree, ["lambda_expression"]):
        if node.type != "lambda_expression":
            continue

        parent = node.parent
        variable_name = None
        definition_node_id = None

        if parent and parent.type == "init_declarator":
            declarator = parent.child_by_field_name("declarator")
            if declarator and declarator.type == "identifier":
                variable_name = st(declarator)

                statement = parent.parent
                if statement:
                    definition_node_id = get_index(statement, index)

        if not variable_name or not definition_node_id:
            continue

        body_nodes = []
        for child in node.children:
            if child.type == "compound_statement":
                for stmt in child.named_children:
                    stmt_id = get_index(stmt, index)
                    if stmt_id and stmt_id in cfg_nodes:
                        body_nodes.append(stmt_id)
                break

        captures = []
        for child in node.children:
            if child.type == "lambda_capture_specifier":
                for capture in child.named_children:
                    if capture.type in variable_type:
                        captures.append(st(capture))
                break

        lambda_node_id = get_index(node, index)

        lambda_map[variable_name] = {
            "definition_node": definition_node_id,
            "lambda_node": lambda_node_id,
            "body_nodes": body_nodes,
            "captures": captures,
        }

        if debug:
            logger.info(
                f"Discovered lambda: {variable_name} at node {definition_node_id}, "
                f"body nodes: {body_nodes}, captures: {captures}"
            )

    return lambda_map


def is_return_value_used(call_expr_statement):
    if call_expr_statement.type == "declaration":
        for child in call_expr_statement.children:
            if child.type == "init_declarator":
                return True
        return False

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
            "do_statement",
            "switch_statement",
        ]:
            return True

        if parent_type == "expression_statement":
            return False

        parent = parent.parent

    return False


def collect_function_metadata(parser):
    """
    Collect metadata about function definitions.

    Returns two dicts:
    - metadata_by_name: simple_name -> metadata (may overwrite for same-named functions)
    - metadata_by_id: func_def_id -> metadata (unique per function)

    Each metadata entry contains:
    - "params": list of (param_name, is_pointer, is_reference, param_idx)
    - "node": the function_definition AST node
    - "func_name": the simple function name

    Note: metadata_by_name is kept for backward compatibility but may lose information
    when multiple functions have the same name. Use metadata_by_id for precise lookup.
    """
    metadata_by_name = {}
    metadata_by_id = {}
    index = parser.index

    for node in traverse_tree(parser.tree.root_node):
        if node.type == "function_definition":
            func_name = None
            params = []

            for child in node.named_children:
                if child.type == "function_declarator":
                    declarator = child.child_by_field_name("declarator")
                    if declarator:
                        if declarator.type in ["identifier", "field_identifier"]:
                            func_name = st(declarator)
                        elif declarator.type in [
                            "pointer_declarator",
                            "reference_declarator",
                        ]:
                            inner = declarator
                            while inner and inner.type in [
                                "pointer_declarator",
                                "reference_declarator",
                            ]:
                                inner_declarator = inner.child_by_field_name(
                                    "declarator"
                                )
                                if inner_declarator:
                                    inner = inner_declarator
                                else:
                                    break
                            if inner and inner.type == "identifier":
                                func_name = st(inner)
                        elif declarator.type == "qualified_identifier":
                            name_node = declarator.child_by_field_name("name")
                            if name_node:
                                func_name = st(name_node)

                    param_list = child.child_by_field_name("parameters")
                    if param_list:
                        param_idx = 0
                        for param in param_list.named_children:
                            if param.type == "parameter_declaration":
                                param_name = None
                                is_pointer = False
                                is_reference = False

                                for p_child in param.named_children:
                                    if p_child.type in [
                                        "pointer_declarator",
                                        "reference_declarator",
                                    ]:
                                        if p_child.type == "pointer_declarator":
                                            is_pointer = True
                                        else:
                                            is_reference = True
                                        inner = p_child
                                        while inner:
                                            if inner.type == "identifier":
                                                param_name = st(inner)
                                                break
                                            elif inner.type in [
                                                "pointer_declarator",
                                                "reference_declarator",
                                            ]:
                                                inner_decl = inner.child_by_field_name(
                                                    "declarator"
                                                )
                                                if inner_decl:
                                                    inner = inner_decl
                                                else:
                                                    if inner.named_children:
                                                        for (
                                                            child
                                                        ) in inner.named_children:
                                                            if (
                                                                child.type
                                                                == "identifier"
                                                            ):
                                                                param_name = st(child)
                                                                break
                                                    break
                                            else:
                                                break
                                    elif p_child.type == "identifier":
                                        if param_name is None:
                                            param_name = st(p_child)

                                if param_name:
                                    params.append(
                                        (
                                            param_name,
                                            is_pointer,
                                            is_reference,
                                            param_idx,
                                        )
                                    )
                                    param_idx += 1
                    break

            if func_name:
                func_def_id = get_index(node, index)
                meta = {"params": params, "node": node, "func_name": func_name}
                metadata_by_name[func_name] = meta
                if func_def_id is not None:
                    metadata_by_id[func_def_id] = meta

    return metadata_by_name, metadata_by_id


def analyze_pointer_modifications(parser, function_metadata):
    modifications = {}

    for func_name, meta in function_metadata.items():
        modified_params = set()
        func_node = meta["node"]

        param_name_to_idx = {}
        for param_name, is_pointer, is_reference, param_idx in meta["params"]:
            if is_pointer or is_reference:
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

                    elif left.type == "identifier":
                        var_name = st(left)
                        if var_name in param_name_to_idx:
                            modified_params.add(param_name_to_idx[var_name])

            elif node.type == "update_expression":
                arg = node.child_by_field_name("argument")
                if arg:
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
                    elif arg.type == "identifier":
                        var_name = st(arg)
                        if var_name in param_name_to_idx:
                            modified_params.add(param_name_to_idx[var_name])

        modifications[func_name] = modified_params

    return modifications


def build_rda_table(
    parser,
    CFG_results,
    lambda_map=None,
    function_metadata=None,
    pointer_modifications=None,
):
    if lambda_map is None:
        lambda_map = {}

    rda_table = {}
    index = parser.index
    tree = parser.tree

    inner_types_local = [
        "parenthesized_expression",
        "binary_expression",
        "unary_expression",
    ]
    handled_cases = [
        "compound_statement",
        "translation_unit",
        "class_specifier",
        "struct_specifier",
        "namespace_definition",
    ]

    for root_node in traverse_tree(tree, []):
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
                if parent_statement and parent_statement.type in inner_types_local:
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

            initializer = root_node.child_by_field_name("value")
            has_initializer = initializer is not None

            if var_identifier:
                add_entry(
                    parser,
                    rda_table,
                    parent_id,
                    defined=var_identifier,
                    declaration=True,
                    has_initializer=has_initializer,
                )

            if initializer:
                if initializer.type == "lambda_expression":
                    for child in initializer.children:
                        if child.type == "lambda_capture_specifier":
                            for capture in child.named_children:
                                if capture.type in variable_type:
                                    add_entry(
                                        parser, rda_table, parent_id, used=capture
                                    )
                elif (
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
                    if child_id and child_id in parser.symbol_table["scope_map"]:
                        add_entry(
                            parser,
                            rda_table,
                            parent_id,
                            defined=child,
                            declaration=True,
                        )
                elif child.type in [
                    "pointer_declarator",
                    "array_declarator",
                    "reference_declarator",
                ]:
                    var_identifier = extract_identifier_from_declarator(child)
                    if var_identifier:
                        var_id = get_index(var_identifier, index)
                        if var_id and var_id in parser.symbol_table["scope_map"]:
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
                if parent_statement and parent_statement.type in inner_types_local:
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
                    var_type = get_variable_type(parser, left_node)

                    if is_class_or_struct_type(
                        parser, var_type
                    ) or is_reference_variable(parser, left_node):
                        add_entry(parser, rda_table, parent_id, used=left_node)
                    else:
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
                if parent_statement and parent_statement.type in inner_types_local:
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
                if parent_statement and parent_statement.type in inner_types_local:
                    parent_statement = return_first_parent_of_types(
                        parent_statement, statement_types["node_list_type"]
                    )
                    parent_id = get_index(parent_statement, index)
                elif parent_statement.type in handled_cases:
                    continue
                else:
                    continue

            function_node = root_node.child_by_field_name("function")
            function_name = None
            method_name_for_lookup = None

            if function_node:
                function_name = st(function_node)

                if function_node.type == "field_expression":
                    argument = function_node.child_by_field_name("argument")
                    if argument:
                        add_entry(parser, rda_table, parent_id, used=argument)
                    field = function_node.child_by_field_name("field")
                    if field:
                        method_name_for_lookup = st(field)
                elif function_node.type in variable_type:
                    add_entry(
                        parser,
                        rda_table,
                        parent_id,
                        used=function_node,
                        method_call=True,
                    )
                elif function_node.type == "qualified_identifier":
                    add_entry(
                        parser,
                        rda_table,
                        parent_id,
                        used=function_node,
                        method_call=True,
                    )

            is_input_function = function_name in input_functions or (
                function_name and any(inp in function_name for inp in ["cin", "scanf"])
            )

            is_variadic_macro = function_name in ["va_start", "va_arg", "va_end"]

            args_node = root_node.child_by_field_name("arguments")
            if args_node:
                arg_list = list(args_node.named_children)
                for idx, arg in enumerate(arg_list):
                    if is_variadic_macro:
                        if function_name == "va_start" and idx == 0:
                            if arg.type in variable_type:
                                add_entry(
                                    parser,
                                    rda_table,
                                    parent_id,
                                    defined=arg,
                                    declaration=False,
                                    has_initializer=True,
                                )
                            else:
                                identifiers_defined = recursively_get_children_of_types(
                                    arg,
                                    variable_type,
                                    index=parser.index,
                                    check_list=parser.symbol_table["scope_map"],
                                )
                                for identifier in identifiers_defined:
                                    add_entry(
                                        parser,
                                        rda_table,
                                        parent_id,
                                        defined=identifier,
                                        declaration=False,
                                        has_initializer=True,
                                    )
                            continue

                        elif function_name == "va_arg" and idx == 0:
                            if arg.type in variable_type:
                                add_entry(parser, rda_table, parent_id, used=arg)
                                add_entry(
                                    parser,
                                    rda_table,
                                    parent_id,
                                    defined=arg,
                                    declaration=False,
                                )
                            else:
                                identifiers_used = recursively_get_children_of_types(
                                    arg,
                                    variable_type,
                                    index=parser.index,
                                    check_list=parser.symbol_table["scope_map"],
                                )
                                for identifier in identifiers_used:
                                    add_entry(
                                        parser, rda_table, parent_id, used=identifier
                                    )
                                    add_entry(
                                        parser,
                                        rda_table,
                                        parent_id,
                                        defined=identifier,
                                        declaration=False,
                                    )
                            continue

                    if is_input_function:
                        if arg.type == "unary_expression":
                            has_address_of = any(
                                child.type == "&" for child in arg.children
                            )
                            if has_address_of:
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
                                continue
                        if arg.type in variable_type + ["field_expression"]:
                            add_entry(
                                parser,
                                rda_table,
                                parent_id,
                                defined=arg,
                                declaration=False,
                            )
                            continue

                    if not is_input_function and not is_variadic_macro:
                        modifies_params = set()
                        lookup_name = (
                            method_name_for_lookup
                            if method_name_for_lookup
                            else function_name
                        )
                        if (
                            lookup_name
                            and function_metadata
                            and lookup_name in function_metadata
                        ):
                            if (
                                pointer_modifications
                                and lookup_name in pointer_modifications
                            ):
                                modifies_params = pointer_modifications[lookup_name]

                        is_modified_param = idx in modifies_params

                        if is_modified_param:
                            if arg.type == "pointer_expression":
                                inner_arg = arg.child_by_field_name("argument")
                                if not inner_arg:
                                    inner_arg = (
                                        arg.named_children[0]
                                        if arg.named_children
                                        else None
                                    )

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
                                            is_pointer_modification_at_call_site=True,
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
                                            is_pointer_modification_at_call_site=True,
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
                                continue
                            elif arg.type == "unary_expression":
                                has_address_of = any(
                                    child.type == "&" for child in arg.children
                                )
                                if has_address_of:
                                    inner_arg = arg.child_by_field_name("argument")
                                    if inner_arg:
                                        if inner_arg.type in variable_type:
                                            add_entry(
                                                parser,
                                                rda_table,
                                                parent_id,
                                                used=inner_arg,
                                            )
                                            add_entry(
                                                parser,
                                                rda_table,
                                                parent_id,
                                                defined=inner_arg,
                                                declaration=False,
                                                is_pointer_modification_at_call_site=True,
                                            )
                                        elif inner_arg.type in [
                                            "field_expression",
                                            "subscript_expression",
                                        ]:
                                            add_entry(
                                                parser,
                                                rda_table,
                                                parent_id,
                                                used=inner_arg,
                                            )
                                            add_entry(
                                                parser,
                                                rda_table,
                                                parent_id,
                                                defined=inner_arg,
                                                declaration=False,
                                                is_pointer_modification_at_call_site=True,
                                            )
                                    continue

                            elif arg.type in variable_type + ["field_expression"]:
                                add_entry(parser, rda_table, parent_id, used=arg)
                                add_entry(
                                    parser,
                                    rda_table,
                                    parent_id,
                                    defined=arg,
                                    declaration=False,
                                    is_pointer_modification_at_call_site=True,
                                )
                                continue

                    if arg.type in variable_type + ["field_expression"]:
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

        elif root_node.type == "function_definition":
            parent_id = get_index(root_node, index)
            if parent_id is None:
                continue

            declarator = root_node.child_by_field_name("declarator")
            if declarator:
                func_declarator = declarator
                while func_declarator and func_declarator.type in [
                    "pointer_declarator",
                    "reference_declarator",
                ]:
                    for child in func_declarator.children:
                        if child.type == "function_declarator":
                            func_declarator = child
                            break
                    else:
                        break

                if func_declarator and func_declarator.type == "function_declarator":
                    func_name_node = func_declarator.child_by_field_name("declarator")
                    if func_name_node and func_name_node.type in variable_type:
                        func_name_idx = get_index(func_name_node, index)
                        if (
                            func_name_idx
                            and func_name_idx in parser.symbol_table["scope_map"]
                        ):
                            namespace_name = get_namespace_for_node(root_node, parser)

                            if namespace_name:
                                qualified_name = (
                                    f"{namespace_name}::{st(func_name_node)}"
                                )

                                class PseudoNode:
                                    def __init__(self, name, real_node):
                                        self.type = "qualified_function"
                                        self.text = name.encode("utf-8")
                                        self.qualified_name = name
                                        self.parent = (
                                            real_node.parent if real_node else None
                                        )
                                        self.real_node = real_node

                                pseudo_node = PseudoNode(qualified_name, func_name_node)
                                add_entry(
                                    parser,
                                    rda_table,
                                    parent_id,
                                    defined=pseudo_node,
                                    declaration=True,
                                )
                            else:
                                add_entry(
                                    parser,
                                    rda_table,
                                    parent_id,
                                    defined=func_name_node,
                                    declaration=True,
                                )

                    param_list = func_declarator.child_by_field_name("parameters")
                    if param_list:
                        for param in param_list.named_children:
                            if param.type in [
                                "parameter_declaration",
                                "optional_parameter_declaration",
                            ]:
                                param_id = extract_param_identifier(param)
                                if param_id:
                                    add_entry(
                                        parser,
                                        rda_table,
                                        parent_id,
                                        defined=param_id,
                                        declaration=True,
                                        has_initializer=True,
                                    )

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

        elif root_node.type == "for_range_loop":
            parent_id = get_index(root_node, index)
            if parent_id is None or parent_id not in CFG_results.graph.nodes:
                continue

            declarator = root_node.child_by_field_name("declarator")
            if declarator:
                var_id = extract_identifier_from_declarator(declarator)
                if var_id:
                    add_entry(
                        parser, rda_table, parent_id, defined=var_id, declaration=True
                    )

            range_expr = root_node.child_by_field_name("right")
            if range_expr:
                if range_expr.type in variable_type + ["field_expression"]:
                    add_entry(parser, rda_table, parent_id, used=range_expr)
                else:
                    identifiers_used = recursively_get_children_of_types(
                        range_expr,
                        variable_type + ["field_expression"],
                        index=parser.index,
                        check_list=parser.symbol_table["scope_map"],
                    )
                    for identifier in identifiers_used:
                        add_entry(parser, rda_table, parent_id, used=identifier)

        elif root_node.type == "do_statement":
            pass

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

        elif root_node.type == "conditional_expression":
            parent_statement = return_first_parent_of_types(
                root_node, statement_types["node_list_type"]
            )
            if parent_statement is None:
                continue

            parent_id = get_index(parent_statement, index)
            if parent_id is None or parent_id not in CFG_results.graph.nodes:
                if parent_statement and parent_statement.type in inner_types_local:
                    parent_statement = return_first_parent_of_types(
                        parent_statement, statement_types["node_list_type"]
                    )
                    parent_id = get_index(parent_statement, index)
                elif parent_statement.type in handled_cases:
                    continue
                else:
                    continue

            condition = root_node.child_by_field_name("condition")
            if condition:
                if (
                    condition.type
                    in variable_type
                    + [
                        "field_expression",
                        "pointer_expression",
                        "subscript_expression",
                        "unary_expression",
                    ]
                    + literal_types
                ):
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
                elif consequence.type in literal_types:
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
                elif alternative.type in literal_types:
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

        elif root_node.type == "lambda_expression":
            parent_id = get_index(root_node, index)
            if parent_id is None:
                continue

            for child in root_node.children:
                if child.type == "lambda_capture_specifier":
                    for capture in child.named_children:
                        if capture.type in variable_type:
                            add_entry(parser, rda_table, parent_id, used=capture)

        elif root_node.type == "catch_clause":
            parent_id = get_index(root_node, index)
            if parent_id is None:
                continue

            for child in root_node.children:
                if child.type == "parameter_list":
                    for param in child.named_children:
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

        elif root_node.type == "throw_statement":
            parent_id = get_index(root_node, index)
            if parent_id is None:
                continue

            identifiers_used = recursively_get_children_of_types(
                root_node,
                variable_type + ["field_expression"],
                index=parser.index,
                check_list=parser.symbol_table["scope_map"],
            )
            for identifier in identifiers_used:
                add_entry(parser, rda_table, parent_id, used=identifier)

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

            handled_types_local = (
                def_statement
                + assignment
                + increment_statement
                + function_calls
                + declaration_statement
                + [
                    "return_statement",
                    "catch_clause",
                    "throw_statement",
                    "conditional_expression",
                ]
            )
            parent_statement = return_first_parent_of_types(
                root_node,
                statement_types["non_control_statement"]
                + statement_types["control_statement"],
                stop_types=statement_types.get("statement_holders", [])
                + handled_types_local,
            )

            if parent_statement is None:
                continue

            parent_id = get_index(parent_statement, index)
            if parent_id is None or parent_id not in CFG_results.graph.nodes:
                continue

            if parent_statement.type in declaration_statement:
                continue

            immediate_parent = root_node.parent
            if immediate_parent and immediate_parent.type == "pointer_expression":
                continue

            add_entry(parser, rda_table, parent_id, used=root_node)

    return rda_table


def start_rda(index, rda_table, cfg_graph, pre_solve=False):
    graph = copy.deepcopy(cfg_graph)
    if pre_solve:
        remove_edges = []
        for edge in graph.edges:
            edge_data = graph.edges[edge]
            if "label" in edge_data and edge_data["label"] in [
                "method_call",
                "method_return",
                "class_return",
                "constructor_call",
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


def name_match_with_fields(use_name, def_name):
    if use_name == def_name:
        return True

    if "." in use_name:
        base_obj = use_name.split(".")[0]
        if def_name == base_obj:
            return True

    return False


def get_required_edges_from_def_to_use(
    index,
    cfg,
    rda_solution,
    rda_table,
    graph_nodes,
    processed_edges,
    properties,
    lambda_map=None,
    node_list=None,
    parser=None,
):
    if lambda_map is None:
        lambda_map = {}
    if node_list is None:
        node_list = {}
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

            matching_defs = []
            matching_field_defs = []

            for available_def in rda_solution[node]["IN"]:
                if parser.src_language != "cpp":
                    if hasattr(available_def, "declaration") and hasattr(
                        available_def, "has_initializer"
                    ):
                        if (
                            available_def.declaration
                            and not available_def.has_initializer
                        ):
                            continue

                if available_def.name == used.name:
                    if scope_check(available_def.scope, used.variable_scope):
                        matching_defs.append(available_def)
                elif "." in used.name or "." in available_def.name:
                    if name_match_with_fields(used.name, available_def.name):
                        if scope_check(available_def.scope, used.variable_scope):
                            matching_field_defs.append(available_def)

            def_info = rda_table[node]["def"] if node in rda_table else []
            defines_same_var = any(d.name == used.name for d in def_info)

            if defines_same_var:
                if matching_defs:
                    node_key = (
                        read_index(index, node) if node in index.values() else None
                    )
                    ast_node = (
                        node_list.get(node_key) if node_list and node_key else None
                    )

                    has_loop_carried_def = any(d.line == node for d in matching_defs)

                    if (
                        has_loop_carried_def
                        and ast_node
                        and is_node_inside_loop(ast_node)
                    ):
                        add_edge(
                            final_graph,
                            node,
                            node,
                            {
                                "dataflow_type": "loop_carried",
                                "edge_type": "DFG_edge",
                                "color": "#FFA500",
                                "used_def": used.name,
                            },
                        )

                    for available_def in matching_defs:
                        if getattr(
                            available_def, "is_pointer_modification_at_call_site", False
                        ):
                            continue
                        if available_def.line != node:
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
            elif matching_defs:
                for available_def in matching_defs:
                    if getattr(
                        available_def, "is_pointer_modification_at_call_site", False
                    ):
                        continue
                    if available_def.line != node:
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
                if matching_defs:
                    used.satisfied = True
            elif matching_field_defs:
                for available_def in matching_field_defs:
                    if name_match_with_fields(used.name, available_def.name):
                        if scope_check(available_def.scope, used.variable_scope):
                            if available_def.line != node:
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
                        names_match = False

                        if definition.name == used.name:
                            names_match = True
                        else:
                            def_base = (
                                definition.name.split("::")[-1]
                                if "::" in definition.name
                                else definition.name
                            )
                            used_base = (
                                used.name.split("::")[-1]
                                if "::" in used.name
                                else used.name
                            )

                            if def_base == used_base:
                                if "::" in used.name:
                                    names_match = definition.name == used.name
                                else:
                                    names_match = False

                        if names_match:
                            node_type = (
                                read_index(index, def_node)[-1]
                                if def_node in index.values()
                                else None
                            )
                            if node_type == "function_definition":
                                func_scope = definition.scope
                                func_line = definition.line
                                namespace_scope = (
                                    func_scope[:-1]
                                    if len(func_scope) > 1
                                    else func_scope
                                )

                                return_nodes = []

                                for rnode in graph_nodes:
                                    rnode_type = (
                                        read_index(index, rnode)[-1]
                                        if rnode in index.values()
                                        else None
                                    )
                                    if rnode_type == "return_statement":
                                        has_return_value = False
                                        return_scope = None
                                        return_line = None

                                        if rnode in rda_table and rda_table[rnode].get(
                                            "use"
                                        ):
                                            for ret_use in rda_table[rnode]["use"]:
                                                return_scope = ret_use.scope
                                                return_line = ret_use.line
                                                has_return_value = True
                                                break

                                        if (
                                            has_return_value
                                            and return_scope
                                            and return_line
                                        ):
                                            namespace_matches = len(
                                                return_scope
                                            ) == len(namespace_scope) and all(
                                                return_scope[i] == namespace_scope[i]
                                                for i in range(len(namespace_scope))
                                            )

                                            if (
                                                namespace_matches
                                                and return_line > func_line
                                            ):
                                                is_in_this_function = True

                                                next_func_line = float("inf")
                                                for other_node in graph_nodes:
                                                    other_type = (
                                                        read_index(index, other_node)[
                                                            -1
                                                        ]
                                                        if other_node in index.values()
                                                        else None
                                                    )
                                                    if (
                                                        other_type
                                                        == "function_definition"
                                                        and other_node != def_node
                                                    ):
                                                        if other_node in rda_table:
                                                            for other_def in rda_table[
                                                                other_node
                                                            ].get("def", []):
                                                                other_scope = (
                                                                    other_def.scope
                                                                )
                                                                other_line = (
                                                                    other_def.line
                                                                )
                                                                other_namespace = (
                                                                    other_scope[:-1]
                                                                    if len(other_scope)
                                                                    > 1
                                                                    else other_scope
                                                                )
                                                                if (
                                                                    other_namespace
                                                                    == namespace_scope
                                                                    and other_line
                                                                    > func_line
                                                                    and other_line
                                                                    < next_func_line
                                                                ):
                                                                    next_func_line = (
                                                                        other_line
                                                                    )

                                                if return_line < next_func_line:
                                                    return_nodes.append(rnode)

                                if return_nodes:
                                    for ret_node in return_nodes:
                                        if ret_node != node:
                                            add_edge(
                                                final_graph,
                                                ret_node,
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

            if not used.satisfied:
                for def_node in graph_nodes:
                    if def_node not in rda_table:
                        continue
                    for definition in rda_table[def_node]["def"]:
                        if definition.name == used.name:
                            if definition.scope == [0] and scope_check(
                                definition.scope, used.scope
                            ):
                                if definition.line != node:
                                    add_edge(
                                        final_graph,
                                        definition.line,
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
                    if used.satisfied:
                        break

            if not used.satisfied and "::" in used.name:
                qualified_parts = used.name.split("::")
                var_name = qualified_parts[-1]

                for def_node in graph_nodes:
                    if def_node not in rda_table:
                        continue
                    for definition in rda_table[def_node]["def"]:
                        if definition.name == var_name:
                            if len(definition.scope) >= 2:
                                if definition.line != node:
                                    add_edge(
                                        final_graph,
                                        definition.line,
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
                    if used.satisfied:
                        break

            if not used.satisfied:
                for def_node in graph_nodes:
                    if def_node not in rda_table:
                        continue
                    for definition in rda_table[def_node]["def"]:
                        if definition.name == used.name:
                            if len(definition.scope) >= 2 and len(used.scope) >= 2:
                                if (
                                    definition.scope[0] == used.scope[0]
                                    and definition.scope[1] == used.scope[1]
                                ):
                                    if definition.line != node:
                                        add_edge(
                                            final_graph,
                                            definition.line,
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
                    if used.satisfied:
                        break

        if properties.get("last_def", False):
            killed_defs = rda_solution[node]["IN"] - rda_solution[node]["OUT"]
            for killed_def in killed_defs:
                node_type = read_index(index, node)[-1]
                def_node_type = read_index(index, killed_def.line)[-1]
                ignore_types = [
                    "for_statement",
                    "for_range_loop",
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
        edge_data = cfg.get_edge_data(*edge)
        if edge_data and len(edge_data) > 0:
            edge_data = edge_data[0]
            label = edge_data.get("label", "")

            if label == "constructor_call":
                source_node = node_list.get(read_index(index, edge[0]))
                obj_name = "this"
                if source_node and source_node.type == "declaration":
                    for child in source_node.named_children:
                        if child.type in [
                            "init_declarator",
                            "identifier",
                            "type_identifier",
                        ]:
                            if child.type == "init_declarator":
                                decl = child.child_by_field_name("declarator")
                                if decl and decl.type == "identifier":
                                    obj_name = st(decl)
                            elif child.type == "identifier":
                                obj_name = st(child)

                add_edge(
                    final_graph,
                    edge[0],
                    edge[1],
                    {
                        "dataflow_type": "constructor_call",
                        "edge_type": "DFG_edge",
                        "color": "#FF6B6B",
                        "object_name": obj_name,
                    },
                )

            elif label == "base_constructor_call":
                add_edge(
                    final_graph,
                    edge[0],
                    edge[1],
                    {
                        "dataflow_type": "base_constructor_call",
                        "edge_type": "DFG_edge",
                        "color": "#FF6B6B",
                        "object_name": "this",
                    },
                )

            elif label == "scope_exit_destructor":
                add_edge(
                    final_graph,
                    edge[0],
                    edge[1],
                    {
                        "dataflow_type": "destructor_call",
                        "edge_type": "DFG_edge",
                        "color": "#C44569",
                        "object_name": "this",
                    },
                )

            elif label == "base_destructor_call":
                add_edge(
                    final_graph,
                    edge[0],
                    edge[1],
                    {
                        "dataflow_type": "base_destructor_call",
                        "edge_type": "DFG_edge",
                        "color": "#C44569",
                        "object_name": "this",
                    },
                )

            elif label == "virtual_call":
                source_node = node_list.get(read_index(index, edge[0]))
                obj_name = "this"

                if source_node and source_node.type == "expression_statement":
                    call_expr = (
                        source_node.named_children[0]
                        if source_node.named_children
                        else None
                    )
                    if call_expr and call_expr.type == "call_expression":
                        func_node = call_expr.child_by_field_name("function")
                        if func_node and func_node.type == "field_expression":
                            arg_node = func_node.child_by_field_name("argument")
                            if arg_node:
                                obj_name = st(arg_node)

                add_edge(
                    final_graph,
                    edge[0],
                    edge[1],
                    {
                        "dataflow_type": "virtual_dispatch",
                        "edge_type": "DFG_edge",
                        "color": "#4834DF",
                        "object_name": obj_name,
                    },
                )

            elif label == "method_call":
                pass

            else:
                if label in ["method_return", "function_return"]:
                    add_edge(
                        final_graph,
                        edge[0],
                        edge[1],
                        {"dataflow_type": "parameter", "edge_type": "DFG_edge"},
                    )

    if lambda_map:
        param_to_lambda = {}

        for call_node, func_def_node in processed_edges:
            if call_node not in rda_table:
                continue

            uses = rda_table[call_node].get("use", [])

            if func_def_node not in rda_table:
                continue
            params = rda_table[func_def_node].get("def", [])

            node_type = (
                read_index(index, func_def_node)[-1]
                if func_def_node in index.values()
                else None
            )
            actual_params = (
                params[1:] if node_type == "function_definition" and params else params
            )

            for used_var in uses:
                if not isinstance(used_var, Identifier):
                    continue
                if used_var.method_call:
                    continue

                if used_var.name in lambda_map:
                    for param in actual_params:
                        if isinstance(param, Identifier) and not param.method_call:
                            param_to_lambda[(param.name, func_def_node)] = used_var.name
                            if debug:
                                logger.info(
                                    f"Mapped parameter {param.name} in func {func_def_node} "
                                    f"to lambda {used_var.name}"
                                )

        for node in graph_nodes:
            if node not in rda_table:
                continue

            uses = rda_table[node].get("use", [])

            for used_var in uses:
                if not isinstance(used_var, Identifier):
                    continue
                if not used_var.method_call:
                    continue

                node_type = (
                    read_index(index, node)[-1] if node in index.values() else None
                )

                reaching_defs = rda_solution[node]["IN"]
                for def_var in reaching_defs:
                    if not isinstance(def_var, Identifier):
                        continue
                    if def_var.name != used_var.name:
                        continue

                    key = (def_var.name, def_var.line)
                    if key in param_to_lambda:
                        lambda_var = param_to_lambda[key]
                        lambda_info = lambda_map[lambda_var]

                        for body_node in lambda_info["body_nodes"]:
                            add_edge(
                                final_graph,
                                node,
                                body_node,
                                {
                                    "dataflow_type": "lambda_call",
                                    "edge_type": "DFG_edge",
                                    "color": "#FF6B6B",
                                    "lambda_var": lambda_var,
                                },
                            )
                            if debug:
                                logger.info(
                                    f"Added lambda call edge: {node} -> {body_node} "
                                    f"(calling lambda {lambda_var})"
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
            func_node = node.child_by_field_name("function")
            if func_node:
                if func_node.type == "identifier":
                    function_name = st(func_node)
                elif func_node.type == "qualified_identifier":
                    function_name = st(func_node)
                elif func_node.type == "field_expression":
                    field_node = func_node.child_by_field_name("field")
                    if field_node and field_node.type == "field_identifier":
                        function_name = st(field_node)

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
            args_node = node.child_by_field_name("arguments")
            if args_node:
                func_params = function_metadata[function_name]["params"]

                for arg_idx, arg in enumerate(args_node.named_children):
                    if arg_idx < len(func_params):
                        param_name, is_pointer, is_reference, param_idx = func_params[
                            arg_idx
                        ]

                        if is_pointer or is_reference:
                            if arg.type == "pointer_expression":
                                has_ampersand = False
                                arg_node = None
                                for arg_child in arg.children:
                                    if arg_child.type == "&":
                                        has_ampersand = True
                                    elif arg_child.is_named:
                                        arg_node = arg_child

                                if has_ampersand and arg_node:
                                    if arg_node.type in ["identifier", "this"]:
                                        var_name = st(arg_node)
                                        pass_by_ref_args.append(
                                            (arg_idx, var_name, arg_node)
                                        )
                            elif is_reference and arg.type in ["identifier", "this"]:
                                var_name = st(arg)
                                pass_by_ref_args.append((arg_idx, var_name, arg))
                            elif is_pointer and arg.type in ["identifier", "this"]:
                                var_name = st(arg)
                                arg_index = get_index(arg, index)
                                if (
                                    arg_index
                                    and arg_index in parser.symbol_table["scope_map"]
                                ):
                                    pass_by_ref_args.append((arg_idx, var_name, arg))

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


def find_modification_sites(parser, function_metadata_by_id, pointer_modifications):
    """
    Find all modification sites for pointer/reference parameters inside functions.

    For each function, find all statements where a pointer/reference parameter is modified.

    Args:
        parser: C++ parser
        function_metadata_by_id: Dict mapping func_def_id -> metadata (from collect_function_metadata)
        pointer_modifications: Dict mapping func_name -> set of modified param indices

    Returns:
        Tuple of:
        - modification_sites_by_name: Dict mapping function_name -> list of (param_idx, modification_node, statement_id)
        - modification_sites_by_id: Dict mapping func_def_id -> list of (param_idx, modification_node, statement_id)
    """
    modification_sites_by_name = {}
    modification_sites_by_id = {}
    index = parser.index

    for func_def_id, meta in function_metadata_by_id.items():
        modifications = []
        func_node = meta["node"]
        func_name = meta.get("func_name", "")
        modified_params = pointer_modifications.get(func_name, set())

        param_name_to_idx = {}
        for param_name, is_pointer, is_reference, param_idx in meta["params"]:
            if (is_pointer or is_reference) and param_idx in modified_params:
                param_name_to_idx[param_name] = param_idx

        if not param_name_to_idx:
            if func_name:
                modification_sites_by_name[func_name] = modifications
            modification_sites_by_id[func_def_id] = modifications
            continue

        for node in traverse_tree(func_node):
            modification_param_idx = None
            mod_node = None

            if node.type == "assignment_expression":
                left = node.child_by_field_name("left")
                if left:
                    if left.type == "pointer_expression":
                        arg = left.child_by_field_name("argument")
                        if arg and arg.type in ["identifier", "this"]:
                            var_name = st(arg)
                            if var_name in param_name_to_idx:
                                modification_param_idx = param_name_to_idx[var_name]
                                mod_node = node

                    elif left.type == "subscript_expression":
                        array_arg = left.child_by_field_name("argument")
                        if array_arg and array_arg.type in ["identifier", "this"]:
                            var_name = st(array_arg)
                            if var_name in param_name_to_idx:
                                modification_param_idx = param_name_to_idx[var_name]
                                mod_node = node

                    elif left.type in ["identifier", "this"]:
                        var_name = st(left)
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
                        if inner_arg and inner_arg.type in ["identifier", "this"]:
                            var_name = st(inner_arg)
                            if var_name in param_name_to_idx:
                                modification_param_idx = param_name_to_idx[var_name]
                                mod_node = node
                    elif arg.type == "subscript_expression":
                        array_arg = arg.child_by_field_name("argument")
                        if array_arg and array_arg.type in ["identifier", "this"]:
                            var_name = st(array_arg)
                            if var_name in param_name_to_idx:
                                modification_param_idx = param_name_to_idx[var_name]
                                mod_node = node
                    elif arg.type in ["identifier", "this"]:
                        var_name = st(arg)
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

        if func_name:
            modification_sites_by_name[func_name] = modifications
        modification_sites_by_id[func_def_id] = modifications

    return modification_sites_by_name, modification_sites_by_id


def get_cfg_call_targets(cfg_graph, call_site_id):
    """
    Get the function definition IDs that are called from a given call site,
    based on CFG edges (method_call, virtual_call, function_call).

    This uses the CFG's resolution of virtual dispatch, which correctly handles
    pointer_targets to determine the actual concrete type being called.

    Args:
        cfg_graph: The CFG graph
        call_site_id: The call site node ID

    Returns:
        Set of function definition IDs that are actually called from this call site
    """
    target_func_ids = set()

    for edge in cfg_graph.out_edges(call_site_id):
        edge_data = cfg_graph.get_edge_data(*edge)
        if edge_data and len(edge_data) > 0:
            edge_data = edge_data[0]
            label = edge_data.get("label", "")

            if (
                label.startswith("method_call")
                or label.startswith("virtual_call")
                or label.startswith("function_call")
            ):
                target_func_ids.add(edge[1])

    return target_func_ids


def add_interprocedural_edges(
    final_graph,
    parser,
    call_sites,
    modification_sites_by_id,
    function_metadata,
    cfg_graph,
    rda_table,
):
    """
    Add interprocedural DFG edges for pass-by-reference.

    For each call site where &var or reference is passed to a pointer/reference parameter:
    1. Use CFG edges to determine which function(s) are actually called (handles virtual dispatch)
    2. Add edges from modification sites inside the ACTUALLY CALLED function to uses after the call

    This function uses CFG edge information to correctly resolve virtual dispatch,
    ensuring that only modifications from the concrete type's implementation are connected.

    Args:
        final_graph: The DFG graph to add edges to
        parser: C++ parser
        call_sites: List of call site information from collect_call_site_information()
        modification_sites_by_id: Dict mapping func_def_id -> list of modifications
        function_metadata: Dict from collect_function_metadata()
        cfg_graph: Control flow graph (contains virtual dispatch resolution)
        rda_table: RDA table with def/use information
    """
    index = parser.index

    for call_site_info in call_sites:
        call_site_id = call_site_info["call_site_id"]
        function_name = call_site_info["function_name"]
        pass_by_ref_args = call_site_info["pass_by_ref_args"]

        target_func_ids = get_cfg_call_targets(cfg_graph, call_site_id)

        if not target_func_ids:
            continue

        for arg_idx, var_name, var_node in pass_by_ref_args:
            all_param_mods = []

            for func_def_id in target_func_ids:
                mods = modification_sites_by_id.get(func_def_id, [])
                for mod_param_idx, mod_node, mod_statement_id in mods:
                    if mod_param_idx == arg_idx:
                        all_param_mods.append(
                            (mod_param_idx, mod_node, mod_statement_id, func_def_id)
                        )

            if not all_param_mods:
                continue

            reaching_mods = []

            for (
                mod_param_idx,
                mod_node,
                mod_statement_id,
                func_def_id,
            ) in all_param_mods:
                is_killed = False

                func_mods = [
                    (m_idx, m_node, m_id)
                    for m_idx, m_node, m_id, f_id in all_param_mods
                    if f_id == func_def_id and m_idx == mod_param_idx
                ]

                visited_in_func = set()
                queue_in_func = [mod_statement_id]

                while queue_in_func:
                    current = queue_in_func.pop(0)
                    if current in visited_in_func:
                        continue
                    visited_in_func.add(current)

                    for edge in cfg_graph.out_edges(current):
                        successor = edge[1]

                        if successor in visited_in_func:
                            continue

                        for other_mod_idx, other_mod_node, other_mod_id in func_mods:
                            if (
                                other_mod_id == successor
                                and other_mod_id != mod_statement_id
                            ):
                                is_killed = True
                                break

                        if is_killed:
                            break

                        edge_data = cfg_graph.get_edge_data(*edge)
                        if edge_data:
                            edge_label = edge_data.get(0, {}).get("label", "")
                            if "return" not in edge_label:
                                queue_in_func.append(successor)

                    if is_killed:
                        break

                if not is_killed:
                    reaching_mods.append((mod_param_idx, mod_node, mod_statement_id))

            for mod_param_idx, mod_node, mod_statement_id in reaching_mods:
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


def add_argument_parameter_edges(final_graph, parser, cfg_graph, rda_table):
    """
    Add interprocedural DFG edges for argument-to-parameter data flow.

    For each function call:
    1. Extract arguments from call site
    2. Extract parameters from function definition
    3. Create edges from arguments to parameters

    Args:
        final_graph: The DFG graph to add edges to
        parser: C++ parser
        cfg_graph: Control flow graph with function_call edges
        rda_table: RDA table with def/use information
    """
    index = parser.index
    node_list = {
        (node.start_point, node.end_point, node.type): node
        for node in traverse_tree(parser.tree, [])
    }

    for edge in list(cfg_graph.edges()):
        edge_data = cfg_graph.get_edge_data(*edge)
        if edge_data and len(edge_data) > 0:
            edge_data = edge_data[0]
            label = edge_data.get("label", "")
            controlflow_type = edge_data.get("controlflow_type", "")

            is_function_call = label.startswith(
                "function_call"
            ) or controlflow_type.startswith("function_call")
            is_method_call = label.startswith(
                "method_call"
            ) or controlflow_type.startswith("method_call")

            if is_function_call or is_method_call:
                call_site_id = edge[0]
                func_def_id = edge[1]

                call_site_node = node_list.get(read_index(index, call_site_id))
                func_def_node = node_list.get(read_index(index, func_def_id))

                if not (call_site_node and func_def_node):
                    continue

                if func_def_node.type != "function_definition":
                    continue

                call_expr = None
                for child in traverse_tree(call_site_node, []):
                    if child.type == "call_expression":
                        call_expr = child
                        break

                if not call_expr:
                    continue

                args_node = call_expr.child_by_field_name("arguments")
                if not args_node or not args_node.named_children:
                    continue

                arguments = args_node.named_children

                declarator = func_def_node.child_by_field_name("declarator")
                if not declarator:
                    continue

                func_declarator = declarator
                while func_declarator and func_declarator.type in [
                    "pointer_declarator",
                    "reference_declarator",
                ]:
                    for child in func_declarator.children:
                        if child.type == "function_declarator":
                            func_declarator = child
                            break
                    else:
                        break

                if not func_declarator or func_declarator.type != "function_declarator":
                    continue

                params_node = func_declarator.child_by_field_name("parameters")
                if not params_node or not params_node.named_children:
                    continue

                parameters = [
                    p
                    for p in params_node.named_children
                    if p.type == "parameter_declaration"
                ]

                for idx, (arg, param) in enumerate(zip(arguments, parameters)):
                    param_declarator = param.child_by_field_name("declarator")
                    if not param_declarator:
                        continue

                    is_pass_by_ref_or_ptr = False
                    if param_declarator.type in [
                        "pointer_declarator",
                        "reference_declarator",
                        "array_declarator",
                    ]:
                        is_pass_by_ref_or_ptr = True

                    if not is_pass_by_ref_or_ptr:
                        continue

                    param_id = param_declarator
                    while param_id and param_id.type not in ["identifier"]:
                        if param_id.type in [
                            "pointer_declarator",
                            "reference_declarator",
                            "array_declarator",
                        ]:
                            for child in param_id.named_children:
                                if child.type == "identifier":
                                    param_id = child
                                    break
                                elif child.type in [
                                    "pointer_declarator",
                                    "reference_declarator",
                                    "function_declarator",
                                    "array_declarator",
                                ]:
                                    param_id = child
                                    break
                            else:
                                break
                        else:
                            break

                    if not param_id or param_id.type != "identifier":
                        continue

                    param_name = param_id.text.decode("utf-8")

                    add_edge(
                        final_graph,
                        call_site_id,
                        func_def_id,
                        {
                            "dataflow_type": "comesFrom",
                            "edge_type": "DFG_edge",
                            "color": "#00A3FF",
                            "used_def": param_name,
                            "interprocedural": "argument_to_parameter",
                            "argument_index": idx,
                        },
                    )


def add_method_member_access_edges(final_graph, parser, cfg_graph, rda_table):
    """
    Add interprocedural DFG edges for method member access.

    When an object's method is called (obj.method()), create edges showing:
    1. The object flows to the method (as implicit 'this' parameter)
    2. Member accesses within the method (this->field) use the object's data

    Args:
        final_graph: The DFG graph to add edges to
        parser: C++ parser
        cfg_graph: Control flow graph with method_call edges
        rda_table: RDA table with def/use information
    """
    index = parser.index
    node_list = {
        (node.start_point, node.end_point, node.type): node
        for node in traverse_tree(parser.tree, [])
    }

    for edge in list(cfg_graph.edges()):
        edge_data = cfg_graph.get_edge_data(*edge)
        if edge_data and len(edge_data) > 0:
            edge_data = edge_data[0]
            label = edge_data.get("label", "")
            object_name = edge_data.get("object_name", "")

            if label in ["method_call", "virtual_call"]:
                call_site_id = edge[0]
                method_def_id = edge[1]

                call_site_node = node_list.get(read_index(index, call_site_id))
                method_def_node = node_list.get(read_index(index, method_def_id))

                if not (call_site_node and method_def_node):
                    continue

                if method_def_node.type != "function_definition":
                    continue

                method_body = method_def_node.child_by_field_name("body")
                if not method_body:
                    continue

                field_accesses = []
                for node in traverse_tree(method_body, []):
                    if node.type == "field_expression":
                        argument = node.child_by_field_name("argument")
                        field = node.child_by_field_name("field")

                        if argument and field:
                            arg_text = argument.text.decode("utf-8")
                            if arg_text == "this" or arg_text == object_name:
                                parent_stmt = node
                                while (
                                    parent_stmt
                                    and parent_stmt.type
                                    not in statement_types["node_list_type"]
                                ):
                                    parent_stmt = parent_stmt.parent

                                if parent_stmt:
                                    stmt_id = get_index(parent_stmt, index)
                                    if stmt_id and stmt_id in cfg_graph.nodes:
                                        field_name = field.text.decode("utf-8")
                                        field_accesses.append((stmt_id, field_name))

                class_members = set()
                parent = method_def_node.parent
                while parent:
                    if parent.type in ["class_specifier", "struct_specifier"]:
                        for node in traverse_tree(parent, []):
                            if node.type == "field_declaration":
                                declarator = node.child_by_field_name("declarator")
                                if declarator:
                                    if declarator.type == "identifier":
                                        class_members.add(
                                            declarator.text.decode("utf-8")
                                        )
                                    elif declarator.type == "field_identifier":
                                        class_members.add(
                                            declarator.text.decode("utf-8")
                                        )
                                    for child in declarator.children:
                                        if child.type == "identifier":
                                            class_members.add(
                                                child.text.decode("utf-8")
                                            )
                        break
                    parent = parent.parent

                for node_id in cfg_graph.nodes:
                    node_key = (
                        read_index(index, node_id)
                        if node_id in index.values()
                        else None
                    )
                    if not node_key:
                        continue
                    ast_node = node_list.get(node_key)
                    if not ast_node:
                        continue

                    is_in_method = False
                    temp = ast_node
                    while temp:
                        if temp == method_body:
                            is_in_method = True
                            break
                        temp = temp.parent

                    if not is_in_method:
                        continue

                    if node_id in rda_table:
                        for used in rda_table[node_id].get("use", []):
                            if isinstance(used, Identifier):
                                if used.core in class_members:
                                    field_accesses.append((node_id, used.core))


def add_function_return_edges(final_graph, parser, cfg_graph, rda_table):
    """
    Add interprocedural DFG edges for function return values.

    For each function call where the return value is used:
    1. Find the return statement(s) in the called function
    2. Extract the returned expression/variable
    3. Find the variable being initialized at the call site
    4. Create edge from returned expression to initialized variable

    Args:
        final_graph: The DFG graph to add edges to
        parser: C++ parser
        cfg_graph: Control flow graph with function_return/method_return edges
        rda_table: RDA table with def/use information
    """
    index = parser.index
    node_list = {
        (node.start_point, node.end_point, node.type): node
        for node in traverse_tree(parser.tree, [])
    }

    for edge in list(cfg_graph.edges()):
        edge_data = cfg_graph.get_edge_data(*edge)
        if edge_data and len(edge_data) > 0:
            edge_data = edge_data[0]
            label = edge_data.get("label", "")

            if label in ["function_return", "method_return"]:
                return_node_id = edge[0]
                call_site_id = edge[1]

                return_statement = node_list.get(read_index(index, return_node_id))
                call_site_node = node_list.get(read_index(index, call_site_id))

                if not (return_statement and call_site_node):
                    continue

                if (
                    return_statement.type != "return_statement"
                    or not return_statement.named_children
                ):
                    continue

                if not is_return_value_used(call_site_node):
                    continue

                returned_vars = []
                if return_node_id in rda_table:
                    for used in rda_table[return_node_id].get("use", []):
                        if isinstance(used, Identifier):
                            returned_vars.append(used.name)

                if not returned_vars:
                    continue

                initialized_vars = []
                if call_site_id in rda_table:
                    for defined in rda_table[call_site_id].get("def", []):
                        if isinstance(defined, Identifier):
                            initialized_vars.append(defined.name)

                for ret_var in returned_vars:
                    for init_var in initialized_vars:
                        add_edge(
                            final_graph,
                            return_node_id,
                            call_site_id,
                            {
                                "dataflow_type": "comesFrom",
                                "edge_type": "DFG_edge",
                                "color": "#00A3FF",
                                "used_def": init_var,
                                "interprocedural": "return_to_caller",
                                "returned_value": ret_var,
                            },
                        )


def dfg_cpp(properties, CFG_results):
    """
    Main driver for generating DFG for C++ programs.

    Combines C procedural features with Java OOP features.

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
        cfg_graph.nodes[nid]["node_source"] = "DFG"
        cfg_graph.nodes[nid]["fillcolor"] = "#F5E0C6"
        cfg_graph.nodes[nid]["color"] = "#C98A5A"
    node_list = CFG_results.node_list

    cfg_records = (
        CFG_results.CFG.records
        if hasattr(CFG_results, "CFG") and hasattr(CFG_results.CFG, "records")
        else {}
    )
    implicit_return_map = cfg_records.get("implicit_return_map", {})

    implicit_return_to_destructor = {
        ir_id: fn_id for fn_id, ir_id in implicit_return_map.items()
    }

    processed_edges = []

    called_destructors = set()
    destructor_chain_edges = []
    base_destructor_edges = []

    for edge in list(cfg_graph.edges()):
        edge_data = cfg_graph.get_edge_data(*edge)
        if edge_data and len(edge_data) > 0:
            edge_data = edge_data[0]
            label = edge_data.get("label", "")

            if label == "scope_exit_destructor":
                called_destructors.add(edge[1])
            elif label.startswith("destructor_chain|"):
                destructor_chain_edges.append(edge)
            elif label == "base_destructor_call":
                base_destructor_edges.append(edge)

    changed = True
    while changed:
        changed = False
        for edge in destructor_chain_edges:
            source_ir = edge[0]
            target_destructor = edge[1]
            source_destructor = implicit_return_to_destructor.get(source_ir)
            if source_destructor and source_destructor in called_destructors:
                if target_destructor not in called_destructors:
                    called_destructors.add(target_destructor)
                    changed = True

    valid_implicit_returns = set()
    for destructor_id in called_destructors:
        ir_id = implicit_return_map.get(destructor_id)
        if ir_id:
            valid_implicit_returns.add(ir_id)

    for edge in list(cfg_graph.edges()):
        edge_data = cfg_graph.get_edge_data(*edge)
        if edge_data and len(edge_data) > 0:
            edge_data = edge_data[0]
            label = edge_data.get("label", "")

            if label.startswith("function_call|"):
                call_statement = node_list.get(read_index(index, edge[0]))
                function_def = node_list.get(read_index(index, edge[1]))

                if call_statement and function_def:
                    if function_def.type == "function_definition":
                        declarator = function_def.child_by_field_name("declarator")
                        if declarator:
                            params_node = declarator.child_by_field_name("parameters")
                            if params_node and params_node.named_children:
                                processed_edges.append(edge)

            elif label in ["method_return", "function_return"]:
                return_statement = node_list.get(read_index(index, edge[0]))
                call_site_node = node_list.get(read_index(index, edge[1]))

                if return_statement and return_statement.type == "return_statement":
                    if return_statement.named_children:
                        if call_site_node and is_return_value_used(call_site_node):
                            processed_edges.append(edge)

            elif label == "constructor_call":
                processed_edges.append(edge)

            elif label == "base_constructor_call":
                processed_edges.append(edge)

            elif label == "scope_exit_destructor":
                processed_edges.append(edge)

            elif label == "base_destructor_call":
                source_ir = edge[0]
                if source_ir in valid_implicit_returns:
                    processed_edges.append(edge)

            elif label == "virtual_call":
                processed_edges.append(edge)

            elif label == "method_call":
                processed_edges.append(edge)

    start_lambda_time = time.time()
    lambda_map = discover_lambdas(parser, CFG_results)
    end_lambda_time = time.time()

    function_metadata_by_name, function_metadata_by_id = collect_function_metadata(
        parser
    )
    pointer_modifications = analyze_pointer_modifications(
        parser, function_metadata_by_name
    )

    start_rda_init_time = time.time()
    rda_table = build_rda_table(
        parser,
        CFG_results,
        lambda_map,
        function_metadata_by_name,
        pointer_modifications,
    )
    end_rda_init_time = time.time()

    start_rda_time = time.time()
    rda_solution = start_rda(index, rda_table, cfg_graph)
    end_rda_time = time.time()

    final_graph = get_required_edges_from_def_to_use(
        index,
        cfg_graph,
        rda_solution,
        rda_table,
        cfg_graph.nodes,
        processed_edges,
        properties,
        lambda_map,
        node_list,
        parser,
    )

    call_sites = collect_call_site_information(
        parser, function_metadata_by_name, cfg_graph
    )
    modification_sites_by_name, modification_sites_by_id = find_modification_sites(
        parser, function_metadata_by_id, pointer_modifications
    )
    add_interprocedural_edges(
        final_graph,
        parser,
        call_sites,
        modification_sites_by_id,
        function_metadata_by_name,
        cfg_graph,
        rda_table,
    )

    add_argument_parameter_edges(final_graph, parser, cfg_graph, rda_table)

    add_function_return_edges(final_graph, parser, cfg_graph, rda_table)

    add_method_member_access_edges(final_graph, parser, cfg_graph, rda_table)

    if debug:
        logger.info(
            "RDA init: {:.3f}s, RDA: {:.3f}s",
            end_rda_init_time - start_rda_init_time,
            end_rda_time - start_rda_time,
        )

    debug_graph = rda_cfg_map(rda_solution, CFG_results)

    return final_graph, debug_graph, rda_table, rda_solution
