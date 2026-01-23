statement_types = {
    "node_list_type": [
        "declaration",
        "expression_statement",
        "labeled_statement",
        "if_statement",
        "while_statement",
        "for_statement",
        "do_statement",
        "break_statement",
        "continue_statement",
        "return_statement",
        "switch_statement",
        "function_definition",
        "case_statement",
        "goto_statement",
        "compound_statement",
        "preproc_include",
        "preproc_def",
        "preproc_function_def",
        "preproc_call",
        "preproc_if",
        "preproc_ifdef",
        "preproc_elif",
        "preproc_else"
    ],
    "non_control_statement": [
        "declaration",
        "expression_statement",
        "preproc_include",
        "preproc_def",
        "preproc_function_def",
        "preproc_call"
    ],
    "control_statement": [
        "if_statement",
        "while_statement",
        "for_statement",
        "do_statement",
        "break_statement",
        "continue_statement",
        "return_statement",
        "switch_statement",
        "goto_statement",
        "case_statement",
        "preproc_if",
        "preproc_ifdef",
        "preproc_elif",
        "preproc_else"
    ],
    "loop_control_statement": [
        "while_statement",
        "for_statement",
        "do_statement",
    ],
    "not_implemented": [],
    "inner_node_type": [
        "declaration",
        "expression_statement",
    ],
    "outer_node_type": ["for_statement"],
    "statement_holders": [
        "compound_statement",
        "translation_unit",
        "case_statement",
        "function_definition"
    ],
    "definition_types": ["function_definition", "declaration", "struct_specifier", "union_specifier", "enum_specifier"]
}

function_return_types = ['primitive_type', 'type_identifier', 'sized_type_specifier', 'struct_specifier', 'union_specifier', 'enum_specifier', 'pointer_declarator']

def extract_parameter_type(param_node):
    """
    Extract the full type of a parameter declaration, including qualifiers and pointers.

    Examples:
    - const uint32_t *in_arr -> 'uint32_t*'
    - size_t n -> 'size_t'
    - char **argv -> 'char**'
    - const int * const ptr -> 'int*'
    - int arr[] -> 'int*' (array parameters decay to pointers)
    - int arr[][10] -> 'int*' (multi-dimensional arrays decay to pointers)

    Returns: string representing the parameter type
    """
    if param_node.type != "parameter_declaration":
        return "unknown"

    base_type = None
    pointer_count = 0

    for child in param_node.children:
        if child.type == "type_qualifier":
            continue

        if child.type in ['primitive_type', 'type_identifier', 'sized_type_specifier',
                         'struct_specifier', 'union_specifier', 'enum_specifier']:
            base_type = child.text.decode('utf-8')

        elif child.type == "pointer_declarator":
            pointer_text = child.text.decode('utf-8')
            pointer_count = pointer_text.count('*')

        elif child.type == "array_declarator":
            def count_array_dimensions(node):
                count = 0
                if node.type == "array_declarator":
                    count = 1
                    for subchild in node.children:
                        if subchild.type == "array_declarator":
                            count += count_array_dimensions(subchild)
                return count

            pointer_count = count_array_dimensions(child)

    if base_type:
        return base_type + ('*' * pointer_count)

    return "unknown"

def get_child_of_type(node, type_list):
    out = list(filter(lambda x : x.type in type_list, node.children))
    if len(out) > 0:
        return out[0]
    else:
        return None

def return_switch_child(node):
    bfs_queue = []
    for child in node.children:
        bfs_queue.append(child)
    while bfs_queue != []:
        top = bfs_queue.pop(0)
        if top.type == "switch_statement":
            return top
        for child in top.children:
            bfs_queue.append(child)
    return None

def get_function_signature(node):
    """
    Extract function signature from function definition or declaration.

    For variadic functions (e.g., int foo(int x, ...)), the signature includes
    '...' as the last element to indicate variable arguments.

    Handles complex types including pointers, const qualifiers, etc.
    Examples:
    - int foo(const uint32_t *arr, size_t n) -> ('uint32_t*', 'size_t')
    - char* bar(char **argv, int argc) -> ('char**', 'int')

    Returns: tuple of parameter types, e.g., ('int', 'char*') or ('int', '...')
    """
    signature = []
    for child in node.children:
        if child.type == "function_declarator":
            param_list = child.child_by_field_name('parameters')
            if param_list:
                for param in param_list.children:
                    if param.type == "parameter_declaration":
                        param_type = extract_parameter_type(param)
                        signature.append(param_type)
                    elif param.type == "variadic_parameter":
                        signature.append('...')
    return tuple(signature)

def get_function_name(node):
    """Extract function name from function_definition"""
    for child in node.children:
        if child.type == "function_declarator":
            for dchild in child.children:
                if dchild.type == "identifier":
                    return dchild.text.decode('utf-8')
                elif dchild.type == "pointer_declarator":
                    for pchild in dchild.children:
                        if pchild.type == "identifier":
                            return pchild.text.decode('utf-8')
    return None

def is_function_declaration(node):
    """
    Check if a declaration node is a function declaration (forward declaration/prototype).

    Function declarations have the form: int foo(int x);
    They contain a function_declarator child but no compound_statement (function body).

    Returns True if the node is a function declaration, False otherwise.
    """
    if node.type != "declaration":
        return False

    for child in node.children:
        if child.type == "function_declarator":
            return True

    return False

def get_nodes(root_node=None, node_list={}, graph_node_list=[], index={}, records={}):
    """
    Returns statement level nodes recursively from the C AST.
    Extracts nodes that will become CFG nodes and populates records dictionary.
    """

    if (
        root_node.type == "parenthesized_expression"
        and root_node.parent is not None
        and root_node.parent.type == "do_statement"
    ):
        label = "while" + root_node.text.decode("UTF-8")
        type_label = "while"
        node_list[(root_node.start_point, root_node.end_point, root_node.type)] = root_node
        graph_node_list.append((index[(root_node.start_point, root_node.end_point, root_node.type)], root_node.start_point[0], label, type_label))

    elif root_node.type in statement_types["node_list_type"]:
        if (
            root_node.type in statement_types["inner_node_type"]
            and root_node.parent is not None
            and root_node.parent.type in statement_types["outer_node_type"]
        ):
            if root_node.parent.type == "for_statement":
                body = root_node.parent.child_by_field_name("body")
                if body != root_node:
                    pass
                else:
                    node_list[(root_node.start_point, root_node.end_point, root_node.type)] = root_node
                    label = root_node.text.decode("UTF-8")
                    type_label = root_node.type
                    graph_node_list.append((index[(root_node.start_point, root_node.end_point, root_node.type)], root_node.start_point[0], label, type_label))

        elif (
            root_node.type in statement_types["inner_node_type"]
            and return_switch_child(root_node) is not None
        ):
            switch_child = return_switch_child(root_node)
            child_index = index[(switch_child.start_point, switch_child.end_point, switch_child.type)]
            current_index = index[(root_node.start_point, root_node.end_point, root_node.type)]
            records["switch_child_map"][current_index] = child_index

        else:
            node_list[(root_node.start_point, root_node.end_point, root_node.type)] = root_node
            label = root_node.text.decode("UTF-8")
            type_label = root_node.type

            if root_node.type == "function_definition":
                label = ""
                for child in root_node.children:
                    if child.type != "compound_statement":
                        label = label + " " + child.text.decode('utf-8')

                func_name = get_function_name(root_node)
                func_index = index[(root_node.start_point, root_node.end_point, root_node.type)]
                type_label = "function_definition"

                if func_name:
                    signature = get_function_signature(root_node)
                    records["function_list"][(func_name, signature)] = func_index

                    if func_name == "main":
                        records["main_function"] = func_index

                    return_type = None
                    for child in root_node.children:
                        if child.type in function_return_types:
                            return_type = child.text.decode('utf-8')
                            break
                    records["return_type"][(func_name, signature)] = return_type

                graph_node_list.append((func_index, root_node.start_point[0], label, type_label))

            elif root_node.type == "if_statement":
                condition = root_node.child_by_field_name("condition")
                if condition:
                    label = "if" + condition.text.decode("UTF-8")
                else:
                    label = "if(...)"
                type_label = "if"

            elif root_node.type == "for_statement":
                init = root_node.child_by_field_name("initializer")
                init_str = init.text.decode("UTF-8") + ";" if init else ""

                condition = root_node.child_by_field_name("condition")
                cond_str = condition.text.decode("UTF-8") if condition else ""

                update = root_node.child_by_field_name("update")
                update_str = update.text.decode("UTF-8") if update else ""

                label = "for(" + init_str + " " + cond_str + "; " + update_str + ")"
                type_label = "for"

            elif root_node.type == "while_statement":
                condition = root_node.child_by_field_name("condition")
                if condition:
                    label = "while" + condition.text.decode("UTF-8")
                else:
                    label = "while(...)"
                type_label = "while"

            elif root_node.type == "do_statement":
                label = "do"
                type_label = "do"

            elif root_node.type == "switch_statement":
                condition = root_node.child_by_field_name("condition")
                if condition:
                    label = "switch" + condition.text.decode("UTF-8")
                else:
                    label = "switch(...)"
                type_label = "switch"

            elif root_node.type == "case_statement":
                value_node = root_node.child_by_field_name("value")
                if value_node:
                    label = "case " + value_node.text.decode("UTF-8") + ":"
                else:
                    if root_node.children and root_node.children[0].type == "default":
                        label = "default:"
                    else:
                        label = "case:"
                type_label = "case"

            elif root_node.type == "labeled_statement":
                label_node = root_node.child_by_field_name("label")
                if label_node:
                    label_name = label_node.text.decode("UTF-8")
                    label = label_name + ":"
                    current_index = index[(root_node.start_point, root_node.end_point, root_node.type)]
                    records["label_statement_map"][label_name] = (root_node.start_point, root_node.end_point, root_node.type)
                type_label = "label"

            elif root_node.type == "return_statement":
                label = root_node.text.decode("UTF-8")
                type_label = "return"

            elif root_node.type == "break_statement":
                label = "break;"
                type_label = "break"

            elif root_node.type == "continue_statement":
                label = "continue;"
                type_label = "continue"

            elif root_node.type == "goto_statement":
                label_node = root_node.child_by_field_name("label")
                if label_node:
                    label = "goto " + label_node.text.decode("UTF-8") + ";"
                else:
                    label = "goto;"
                type_label = "goto"

            if root_node.type not in ["function_definition"]:
                node_index = index[(root_node.start_point, root_node.end_point, root_node.type)]
                graph_node_list.append((node_index, root_node.start_point[0], label, type_label))

    for child in root_node.children:
        get_nodes(child, node_list, graph_node_list, index, records)

    return node_list, graph_node_list, records
