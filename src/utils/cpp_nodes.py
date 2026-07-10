statement_types = {
    "node_list_type": [
        "declaration",
        "expression_statement",
        "labeled_statement",
        "if_statement",
        "while_statement",
        "for_statement",
        "for_range_loop",
        "do_statement",
        "break_statement",
        "continue_statement",
        "return_statement",
        "goto_statement",
        "switch_statement",
        "case_statement",
        "throw_statement",
        "try_statement",
        "function_definition",
        "class_specifier",
        "struct_specifier",
        "using_declaration",
        "alias_declaration",
        "template_declaration",
        "field_declaration",
        "access_specifier",
        "constructor_or_destructor_definition",
        "operator_cast",
        "lambda_expression",
        "enum_specifier",
        "union_specifier",
        "type_definition",
        "friend_declaration",
        "catch_clause",
        "attributed_statement",
        "static_assert_declaration",
        "namespace_alias_definition",
        "preproc_include",
        "preproc_def",
        "preproc_ifdef",
        "preproc_if",
        "preproc_elif",
        "preproc_else",
    ],
    "non_control_statement": [
        "declaration",
        "expression_statement",
        "field_declaration",
        "using_declaration",
        "alias_declaration",
        "access_specifier",
        "enum_specifier",
        "union_specifier",
        "type_definition",
        "friend_declaration",
        "static_assert_declaration",
        "namespace_alias_definition",
        "attributed_statement",
    ],
    "control_statement": [
        "if_statement",
        "while_statement",
        "for_statement",
        "for_range_loop",
        "do_statement",
        "break_statement",
        "continue_statement",
        "return_statement",
        "goto_statement",
        "switch_statement",
        "try_statement",
        "throw_statement",
    ],
    "loop_control_statement": [
        "while_statement",
        "for_statement",
        "for_range_loop",
    ],
    "not_implemented": [],
    "inner_node_type": [
        "declaration",
        "expression_statement",
    ],
    "outer_node_type": ["for_statement", "for_range_loop"],
    "statement_holders": [
        "compound_statement",
        "case_statement",
        "function_definition",
        "class_specifier",
        "struct_specifier",
        "namespace_definition",
        "translation_unit",
    ],
    "definition_types": [
        "function_definition",
        "class_specifier",
        "struct_specifier",
        "field_declaration",
        "namespace_definition",
        "template_declaration",
        "enum_specifier",
        "union_specifier",
        "type_definition",
    ],
}

method_return_types = [
    "primitive_type",
    "type_identifier",
    "template_type",
    "qualified_identifier",
    "sized_type_specifier",
    "auto",
    "decltype",
]


def get_child_of_type(node, type_list):
    """Get first child of node matching any type in type_list"""
    out = list(filter(lambda x: x.type in type_list, node.children))
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
        if top.type in statement_types["node_list_type"]:
            return None
        for child in top.children:
            bfs_queue.append(child)
    return None


def return_switch_parent(node, non_control_statement):
    while node.parent is not None and (
        node.parent.type != "class_specifier"
        and node.parent.type != "compound_statement"
    ):
        if node.parent.type == "compound_statement" and node.type == "switch_statement":
            return node
        if node.parent.type in non_control_statement:
            return node.parent
        node = node.parent
    return None


def return_switch_parent_statement(node, non_control_statement):
    while node.parent is not None and (
        node.parent.type != "class_specifier"
        and node.parent.type != "compound_statement"
    ):
        if node.parent.type in non_control_statement:
            return node.parent
        node = node.parent
    return None


def has_inner_definition(node):
    if node.type in ["struct_specifier", "class_specifier", "union_specifier"]:
        has_body = any(
            child.type == "field_declaration_list" for child in node.named_children
        )
        if has_body:
            return True
        for child in node.children:
            if has_inner_definition(child):
                return True
        return False

    if node.type in statement_types["definition_types"]:
        return True

    for child in node.children:
        if has_inner_definition(child):
            return True
    return False


def is_function_declaration(node):
    if node.type != "declaration":
        return False

    has_function_declarator = False
    has_body = False

    for child in node.children:
        if child.type == "function_declarator":
            has_function_declarator = True
        if child.type == "compound_statement":
            has_body = True

    return has_function_declarator and not has_body


def find_function_definition(node):
    while node.parent is not None:
        if node.parent.type == "function_definition":
            return node.parent
        node = node.parent
    return None


def is_virtual_function(node):
    if node.type not in ["function_definition", "field_declaration"]:
        return False

    for child in node.children:
        if child.type == "virtual":
            return True
    return False


def is_pure_virtual_function(node):
    if not is_virtual_function(node):
        return False

    has_equals = False
    for child in node.children:
        if child.type == "=" or child.text == b"=":
            has_equals = True
        if has_equals and child.type == "number_literal" and child.text == b"0":
            return True
    return False


def has_field_initializer_list(node):
    if node.type != "function_definition":
        return False

    for child in node.children:
        if child.type == "field_initializer_list":
            return True
    return False


def is_deleted_or_defaulted(node):
    if node.type not in ["function_definition", "field_declaration"]:
        return None

    for child in node.children:
        if child.type == "default_method_clause":
            return "default"
        if child.type == "delete_method_clause":
            return "delete"
    return None


def is_operator_overload(node):
    if node.type != "function_definition":
        return False

    declarator = node.child_by_field_name("declarator")
    if declarator:
        for child in declarator.children:
            if child.type == "operator_name":
                return True
    return False


def is_constexpr_function(node):
    if node.type not in ["function_definition", "field_declaration"]:
        return False

    for child in node.children:
        if child.type == "constexpr":
            return True
    return False


def is_inline_function(node):
    if node.type not in ["function_definition", "field_declaration"]:
        return False

    for child in node.children:
        if child.type == "inline":
            return True
    return False


def has_noexcept_specifier(node):
    if node.type not in ["function_definition", "field_declaration"]:
        return False

    for child in node.children:
        if child.type == "noexcept":
            return True
    return False


def get_attributes(node):
    attributes = []
    for child in node.children:
        if child.type == "attribute_specifier":
            for attr_child in child.children:
                if attr_child.type == "attribute":
                    for identifier in attr_child.children:
                        if identifier.type == "identifier":
                            attributes.append(identifier.text.decode("utf-8"))
    return attributes


def has_auto_type(node):
    if node.type not in ["declaration", "parameter_declaration"]:
        return False

    for child in node.children:
        if child.type == "auto":
            return True
        if child.type in ["init_declarator", "parameter_declarator"]:
            for subchild in child.children:
                if subchild.type == "auto":
                    return True
    return False


def is_rvalue_reference(node):
    if node.type not in ["declaration", "parameter_declaration", "field_declaration"]:
        return False

    for child in node.children:
        if child.type == "rvalue_reference_declarator":
            return True
        if hasattr(child, "children"):
            for subchild in child.children:
                if subchild.type == "rvalue_reference_declarator":
                    return True
    return False


def is_template_specialization(node):
    if node.type != "template_declaration":
        return False

    for child in node.children:
        if child.type == "template_parameter_list":
            named_children = [c for c in child.children if c.is_named]
            if len(named_children) == 0:
                return True
    return False


def get_signature(node):
    signature = []
    parameter_list = node.child_by_field_name("parameters")
    if parameter_list is None:
        return tuple(signature)

    def count_array_dimensions(array_node):
        count = 0
        if array_node.type == "array_declarator":
            count = 1
            for subchild in array_node.children:
                if subchild.type == "array_declarator":
                    count += count_array_dimensions(subchild)
        return count

    for param in parameter_list.children:
        if param.type in ["parameter_declaration", "optional_parameter_declaration"]:
            base_type = None
            for child in param.children:
                if child.type in [
                    "primitive_type",
                    "type_identifier",
                    "template_type",
                    "qualified_identifier",
                    "sized_type_specifier",
                ]:
                    base_type = child.text.decode("utf-8")
                    break

            if base_type:
                declarator = param.child_by_field_name("declarator")
                if declarator:
                    if declarator.type == "reference_declarator":
                        declarator_text = declarator.text.decode("utf-8")
                        if declarator_text.startswith("&&"):
                            signature.append(base_type + "&&")
                        else:
                            signature.append(base_type + "&")
                    elif declarator.type == "pointer_declarator":
                        signature.append(base_type + "*")
                    elif declarator.type == "array_declarator":
                        pointer_count = count_array_dimensions(declarator)
                        signature.append(base_type + "*" * pointer_count)
                    else:
                        signature.append(base_type)
                else:
                    signature.append(base_type)
        elif param.type == "...":
            signature.append("...")

    return tuple(signature)


def get_lambda_body(node):
    bfs_queue = []
    bfs_queue.append(node)
    while bfs_queue != []:
        top = bfs_queue.pop(0)
        if top.type == "lambda_expression":
            return top
        for child in top.children:
            bfs_queue.append(child)
    return None


def get_all_lambda_body(node):
    bfs_queue = []
    output = []
    bfs_queue.append(node)
    while bfs_queue != []:
        top = bfs_queue.pop(0)
        if top.type == "lambda_expression":
            output.append(top)
        for child in top.children:
            if (
                child.type == "lambda_expression"
                or child.type not in statement_types["node_list_type"]
            ):
                bfs_queue.append(child)
    return output


def check_lambda(node):
    if get_lambda_body(node) is None:
        return False
    else:
        initial_node = node
        lambda_node = get_lambda_body(node)
        parent_node = lambda_node.parent
        while parent_node is not None:
            if parent_node.type in statement_types["node_list_type"]:
                if parent_node == initial_node:
                    return True
                else:
                    return False
            parent_node = parent_node.parent


def get_class_name(node, index):
    """Returns the class name or namespace when a function definition or method is passed to it.

    For namespaces, builds the fully qualified name (e.g., "Outer::Inner").
    Returns tuple: (index, [name]) where name can be class, struct, or namespace.
    """
    type_identifiers = ["type_identifier", "template_type", "qualified_identifier"]

    namespace_parts = []
    temp_node = node
    while temp_node is not None:
        if temp_node.type == "namespace_definition":
            namespace_name_node = temp_node.child_by_field_name("name")
            if namespace_name_node:
                namespace_name = namespace_name_node.text.decode("UTF-8")
                namespace_parts.insert(0, namespace_name)
            else:
                pass
        temp_node = temp_node.parent

    if namespace_parts:
        qualified_namespace = "::".join(namespace_parts)
        temp_node = node
        while temp_node is not None:
            if temp_node.type == "namespace_definition":
                namespace_index = index.get(
                    (temp_node.start_point, temp_node.end_point, temp_node.type)
                )
                if namespace_index is not None:
                    return namespace_index, [qualified_namespace]
            temp_node = temp_node.parent

    while node is not None:
        if (
            node.type == "field_declaration_list"
            and node.parent.type == "class_specifier"
        ):
            node = node.parent
            class_index = index[(node.start_point, node.end_point, node.type)]
            class_name_node = get_child_of_type(node, ["type_identifier"])
            if class_name_node:
                class_name = [class_name_node.text.decode("UTF-8")]
            else:
                class_name = ["anonymous_class"]

            base_list = node.child_by_field_name("base_class_clause")
            if base_list is not None:
                for child in base_list.children:
                    if child.type in type_identifiers:
                        class_name.append(child.text.decode("UTF-8"))

            return class_index, class_name

        elif (
            node.type == "field_declaration_list"
            and node.parent.type == "struct_specifier"
        ):
            node = node.parent
            class_index = index[(node.start_point, node.end_point, node.type)]
            class_name_node = get_child_of_type(node, ["type_identifier"])
            if class_name_node:
                class_name = [class_name_node.text.decode("UTF-8")]
            else:
                class_name = ["anonymous_struct"]

            return class_index, class_name

        node = node.parent
    return None


def evaluate_preprocessor_condition(condition_text, macro_definitions):
    """
    Evaluate a preprocessor condition based on defined macros.
    Returns True if the condition is satisfied, False otherwise, None if cannot evaluate.

    Supports:
    - #ifdef MACRO
    - #ifndef MACRO
    - #if MACRO == VALUE
    - #if defined(MACRO)
    - Simple comparisons and logic
    """
    import re

    if not any(
        op in condition_text for op in ["==", "!=", ">", "<", "&&", "||", "defined"]
    ):
        identifier = condition_text.strip()
        return identifier in macro_definitions

    defined_pattern = r"defined\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)"
    condition_text = re.sub(
        defined_pattern,
        lambda m: "1" if m.group(1) in macro_definitions else "0",
        condition_text,
    )

    for macro, value in macro_definitions.items():
        condition_text = re.sub(r"\b" + macro + r"\b", str(value), condition_text)

    try:
        if re.match(r"^[\d\s+\-*/<>=!&|()]+$", condition_text):
            result = eval(condition_text)
            return bool(result)
    except:
        pass

    return None


def get_nodes(
    root_node=None,
    node_list={},
    graph_node_list=[],
    index={},
    records={},
    macro_definitions=None,
):
    """
    Returns statement level nodes recursively from the concrete syntax tree passed to it.
    Uses records to maintain required supplementary information.
    node_list maintains an intermediate representation and graph_node_list returns the final list.

    Args:
        macro_definitions: Dictionary of defined macros {name: value} for preprocessor evaluation
    """
    import os

    if macro_definitions is None:
        macro_definitions = {}

    if root_node.type == "catch_clause":
        node_list[(root_node.start_point, root_node.end_point, root_node.type)] = (
            root_node
        )
        catch_parameter = list(
            filter(lambda child: child.type == "parameter_list", root_node.children)
        )
        if catch_parameter:
            param_text = catch_parameter[0].text.decode("UTF-8")
            if param_text.startswith("(") and param_text.endswith(")"):
                param_text = param_text[1:-1]

            if param_text.strip() == "...":
                label = "catch (...)"
            else:
                label = "catch (" + param_text + ")"
        else:
            label = "catch (...)"
        type_label = "catch"
        graph_node_list.append(
            (
                index[(root_node.start_point, root_node.end_point, root_node.type)],
                root_node.start_point[0],
                label,
                type_label,
            )
        )

    elif (
        root_node.type == "parenthesized_expression"
        and root_node.parent is not None
        and root_node.parent.type == "do_statement"
    ):
        label = "while" + root_node.text.decode("UTF-8")
        type_label = "while"
        node_list[(root_node.start_point, root_node.end_point, root_node.type)] = (
            root_node
        )
        graph_node_list.append(
            (
                index[(root_node.start_point, root_node.end_point, root_node.type)],
                root_node.start_point[0],
                label,
                type_label,
            )
        )

    elif root_node.type in [
        "preproc_include",
        "preproc_def",
        "preproc_function_def",
        "preproc_call",
        "preproc_if",
        "preproc_ifdef",
        "preproc_elif",
        "preproc_else",
    ]:

        if root_node.type == "preproc_def":
            text = root_node.text.decode("UTF-8")
            parts = text.split(None, 2)
            if len(parts) >= 2:
                macro_name = parts[1]
                macro_value = parts[2].strip() if len(parts) > 2 else "1"
                macro_definitions[macro_name] = macro_value
                if os.environ.get("DEBUG_PREPROC"):
                    print(f"[DEFINE] {macro_name} = {macro_value}")

    elif root_node.type in statement_types["node_list_type"]:
        if root_node.type == "field_declaration":
            pass

        elif root_node.type in ["struct_specifier", "class_specifier"]:
            parent = root_node.parent
            should_skip = False

            if parent and parent.type in ["translation_unit", "declaration_list"]:
                if parent.type == "declaration_list":
                    grandparent = parent.parent if parent else None
                    if grandparent and grandparent.type in [
                        "namespace_definition",
                        "translation_unit",
                    ]:
                        should_skip = True
                else:
                    should_skip = True

            elif parent and parent.type == "field_declaration_list":
                should_skip = True

            if should_skip:
                pass
        elif is_function_declaration(root_node):
            pass
        elif root_node.type == "template_declaration":
            pass
        elif root_node.type == "access_specifier":
            pass
        elif root_node.parent and root_node.parent.type == "attributed_statement":
            pass
        elif root_node.type == "lambda_expression":
            parent = root_node.parent
            while parent and parent.type not in statement_types["node_list_type"]:
                parent = parent.parent

            if parent and parent.type != "lambda_expression":
                node_list[
                    (root_node.start_point, root_node.end_point, root_node.type)
                ] = root_node
            else:
                node_list[
                    (root_node.start_point, root_node.end_point, root_node.type)
                ] = root_node
                label = root_node.text.decode("UTF-8")
                type_label = "expression_statement"
                try:
                    if "{" in label:
                        label = label.split("{")[0] + label.split("}")[-1]
                    else:
                        label = root_node.text.decode("utf-8")
                except:
                    pass
                graph_node_list.append(
                    (
                        index[
                            (root_node.start_point, root_node.end_point, root_node.type)
                        ],
                        root_node.start_point[0],
                        label,
                        type_label,
                    )
                )
        elif (
            root_node.type in statement_types["inner_node_type"]
            and root_node.parent is not None
            and root_node.parent.type in statement_types["outer_node_type"]
            and root_node.parent.child_by_field_name("body") != root_node
        ):
            pass
        elif (
            root_node.type in statement_types["inner_node_type"]
            and return_switch_child(root_node) is not None
        ):
            switch_child = return_switch_child(root_node)
            child_index = index[
                (switch_child.start_point, switch_child.end_point, switch_child.type)
            ]
            current_index = index[
                (root_node.start_point, root_node.end_point, root_node.type)
            ]
            records["switch_child_map"][current_index] = child_index
        else:
            node_list[(root_node.start_point, root_node.end_point, root_node.type)] = (
                root_node
            )
            label = root_node.text.decode("UTF-8")
            type_label = "expression_statement"

            if (
                check_lambda(root_node)
                and root_node.type not in statement_types["definition_types"]
            ):
                raw_label = root_node.text.decode("utf-8")
                label = ""
                for lambda_expression in get_all_lambda_body(root_node):
                    split_label = raw_label.split(
                        lambda_expression.text.decode("utf-8"), 2
                    )
                    raw_label = split_label[0]
                    if len(split_label) > 1:
                        label = split_label[1] + label
                    lambda_node = (
                        lambda_expression.start_point,
                        lambda_expression.end_point,
                        lambda_expression.type,
                    )
                    records["lambda_map"][lambda_node] = root_node
                label = raw_label + label

            if root_node.type == "function_definition":
                label = ""
                declarator = root_node.child_by_field_name("declarator")

                is_virtual = is_virtual_function(root_node)
                is_pure_virtual = is_pure_virtual_function(root_node)
                is_operator = is_operator_overload(root_node)
                deleted_or_defaulted = is_deleted_or_defaulted(root_node)
                has_initializers = has_field_initializer_list(root_node)

                is_constexpr = is_constexpr_function(root_node)
                is_inline = is_inline_function(root_node)
                has_noexcept = has_noexcept_specifier(root_node)
                attributes = get_attributes(root_node)

                if declarator:
                    for child in root_node.children:
                        if child.type not in [
                            "compound_statement",
                            "function_body",
                            "field_initializer_list",
                        ]:
                            label = label + " " + child.text.decode("utf-8")

                function_name_node = None
                if declarator:
                    if declarator.type == "function_declarator":
                        operator_name_node = None
                        for child in declarator.children:
                            if child.type == "operator_name":
                                operator_name_node = child
                                break

                        if operator_name_node:
                            function_name_node = operator_name_node
                        else:
                            function_name_node = declarator.child_by_field_name(
                                "declarator"
                            )
                    elif (
                        declarator.type == "pointer_declarator"
                        or declarator.type == "reference_declarator"
                    ):
                        nested = declarator
                        while nested and nested.type in [
                            "pointer_declarator",
                            "reference_declarator",
                        ]:
                            found_nested = None
                            for child in nested.children:
                                if child.type in [
                                    "function_declarator",
                                    "pointer_declarator",
                                    "reference_declarator",
                                ]:
                                    found_nested = child
                                    break
                            nested = found_nested

                        if nested and nested.type == "function_declarator":
                            operator_name_node = None
                            for child in nested.children:
                                if child.type == "operator_name":
                                    operator_name_node = child
                                    break

                            if operator_name_node:
                                function_name_node = operator_name_node
                            else:
                                function_name_node = nested.child_by_field_name(
                                    "declarator"
                                )

                if function_name_node:
                    function_name = function_name_node.text.decode("UTF-8")
                else:
                    function_name = "unknown"

                function_index = index[
                    (root_node.start_point, root_node.end_point, root_node.type)
                ]
                type_label = root_node.type

                try:
                    sig_node = declarator
                    if declarator and declarator.type in [
                        "pointer_declarator",
                        "reference_declarator",
                    ]:
                        nested = declarator
                        while nested and nested.type in [
                            "pointer_declarator",
                            "reference_declarator",
                        ]:
                            found_nested = None
                            for child in nested.children:
                                if child.type == "function_declarator":
                                    sig_node = child
                                    break
                                elif child.type in [
                                    "pointer_declarator",
                                    "reference_declarator",
                                ]:
                                    found_nested = child
                                    break
                            if sig_node and sig_node.type == "function_declarator":
                                break
                            nested = found_nested

                    signature = get_signature(
                        sig_node
                        if sig_node and sig_node.type == "function_declarator"
                        else root_node
                    )
                    class_info = get_class_name(root_node, index)

                    if class_info:
                        class_index, class_name_list = class_info
                        if function_name == "main":
                            records["main_function"] = function_index
                            records["main_class"] = class_index

                        for class_name in class_name_list:
                            key = ((class_name, function_name), signature)
                            records["function_list"][key] = function_index

                            if len(signature) > 0 and signature[-1] == "...":
                                records["variadic_functions"][key] = True

                            return_type_node = root_node.child_by_field_name("type")
                            if return_type_node:
                                return_type = return_type_node.text.decode("UTF-8")
                            else:
                                return_type = "void"
                            records["return_type"][key] = return_type

                            if is_virtual or is_pure_virtual:
                                records["virtual_functions"][function_index] = {
                                    "is_virtual": is_virtual,
                                    "is_pure_virtual": is_pure_virtual,
                                }
                            if is_operator:
                                records["operator_overloads"][
                                    function_index
                                ] = function_name
                            if deleted_or_defaulted:
                                records["special_functions"][
                                    function_index
                                ] = deleted_or_defaulted
                            if has_initializers:
                                records["functions_with_initializers"][
                                    function_index
                                ] = True

                            if is_constexpr:
                                records["constexpr_functions"][function_index] = True
                            if is_inline:
                                records["inline_functions"][function_index] = True
                            if has_noexcept:
                                records["noexcept_functions"][function_index] = True
                            if attributes:
                                records["attributed_functions"][
                                    function_index
                                ] = attributes
                    else:
                        if function_name == "main":
                            records["main_function"] = function_index

                        records["function_list"][
                            ((None, function_name), signature)
                        ] = function_index
                        return_type_node = root_node.child_by_field_name("type")
                        if return_type_node:
                            return_type = return_type_node.text.decode("UTF-8")
                        else:
                            return_type = "void"
                        records["return_type"][
                            ((None, function_name), signature)
                        ] = return_type
                except:
                    pass

                graph_node_list.append(
                    (function_index, root_node.start_point[0], label, type_label)
                )

            elif (
                root_node.type == "class_specifier"
                or root_node.type == "struct_specifier"
            ):
                class_name_node = get_child_of_type(root_node, ["type_identifier"])
                if class_name_node:
                    class_name = class_name_node.text.decode("UTF-8")
                    label = f"{root_node.type.replace('_specifier', '')} {class_name}"
                else:
                    label = f"anonymous_{root_node.type.replace('_specifier', '')}"
                    class_name = label

                type_label = root_node.type
                class_index = index[
                    (root_node.start_point, root_node.end_point, root_node.type)
                ]
                records["class_list"][class_name] = class_index

                base_list = root_node.child_by_field_name("base_class_clause")
                if base_list is not None:
                    for child in base_list.children:
                        if child.type in [
                            "type_identifier",
                            "template_type",
                            "qualified_identifier",
                        ]:
                            parent_name = child.text.decode("UTF-8")
                            try:
                                records["extends"][class_name].append(parent_name)
                            except:
                                records["extends"][class_name] = [parent_name]

            elif root_node.type == "namespace_definition":
                namespace_name_node = root_node.child_by_field_name("name")
                if namespace_name_node:
                    namespace_name = namespace_name_node.text.decode("UTF-8")
                    label = f"namespace {namespace_name}"
                else:
                    label = "anonymous namespace"
                type_label = "namespace_definition"

            elif root_node.type == "if_statement":
                condition = root_node.child_by_field_name("condition")
                if condition:
                    label = "if(" + condition.text.decode("UTF-8") + ")"
                else:
                    label = "if"
                type_label = "if"

            elif root_node.type == "for_statement":
                try:
                    init = root_node.child_by_field_name("initializer")
                    init_text = init.text.decode("UTF-8") if init else ""
                    if init_text and not init_text.endswith(";"):
                        init_text = init_text + ";"
                except:
                    init_text = ""
                try:
                    condition = root_node.child_by_field_name("condition")
                    condition_text = condition.text.decode("UTF-8") if condition else ""
                except:
                    condition_text = ""
                try:
                    update = root_node.child_by_field_name("update")
                    update_text = update.text.decode("UTF-8") if update else ""
                except:
                    update_text = ""
                label = "for(" + init_text + condition_text + ";" + update_text + ")"
                type_label = "for"

            elif root_node.type == "for_range_loop":
                try:
                    declarator = root_node.child_by_field_name("declarator")
                    declarator_text = (
                        declarator.text.decode("UTF-8") if declarator else ""
                    )
                    range_expr = root_node.child_by_field_name("right")
                    range_text = range_expr.text.decode("UTF-8") if range_expr else ""
                    label = f"for({declarator_text} : {range_text})"
                except:
                    label = "for(range)"
                type_label = "for"

            elif root_node.type == "while_statement":
                condition = root_node.child_by_field_name("condition")
                if condition:
                    label = "while(" + condition.text.decode("UTF-8") + ")"
                else:
                    label = "while"
                type_label = "while"

            elif root_node.type == "do_statement":
                label = "do"
                type_label = "do"

            elif root_node.type == "switch_statement":
                condition = root_node.child_by_field_name("condition")
                if condition:
                    label = "switch(" + condition.text.decode("UTF-8") + ")"
                else:
                    label = "switch"
                type_label = "switch"

            elif root_node.type == "case_statement":
                value = root_node.child_by_field_name("value")
                if value:
                    label = "case " + value.text.decode("UTF-8") + ":"
                else:
                    label = "default:"
                type_label = "case"

            elif root_node.type == "try_statement":
                label = "try"
                type_label = "try"

            elif root_node.type == "labeled_statement":
                label_node = root_node.child_by_field_name("label")
                if label_node:
                    label = label_node.text.decode("UTF-8") + ":"
                    records["label_statement_map"][label] = (
                        root_node.start_point,
                        root_node.end_point,
                        root_node.type,
                    )
                else:
                    label = "label:"
                type_label = "label"

            elif root_node.type == "return_statement":
                if has_inner_definition(root_node):
                    label = "return"
                else:
                    label = root_node.text.decode("UTF-8")
                type_label = "return"

            elif root_node.type == "enum_specifier":
                enum_name_node = get_child_of_type(root_node, ["type_identifier"])
                is_scoped = "class" in [child.type for child in root_node.children]
                if enum_name_node:
                    enum_name = enum_name_node.text.decode("UTF-8")
                    if is_scoped:
                        label = f"enum class {enum_name}"
                    else:
                        label = f"enum {enum_name}"
                else:
                    label = "enum (anonymous)"
                type_label = "enum"

                enum_index = index[
                    (root_node.start_point, root_node.end_point, root_node.type)
                ]
                if enum_name_node:
                    records["enum_list"][enum_name] = enum_index

            elif root_node.type == "union_specifier":
                union_name_node = get_child_of_type(root_node, ["type_identifier"])
                if union_name_node:
                    union_name = union_name_node.text.decode("UTF-8")
                    label = f"union {union_name}"
                else:
                    label = "union (anonymous)"
                type_label = "union"

                union_index = index[
                    (root_node.start_point, root_node.end_point, root_node.type)
                ]
                if union_name_node:
                    records["union_list"][union_name] = union_index

            elif root_node.type == "type_definition":
                type_identifier_node = get_child_of_type(root_node, ["type_identifier"])
                if type_identifier_node:
                    typedef_name = type_identifier_node.text.decode("UTF-8")
                    label = f"typedef {typedef_name}"
                else:
                    label = "typedef"
                type_label = "typedef"

                typedef_index = index[
                    (root_node.start_point, root_node.end_point, root_node.type)
                ]
                if type_identifier_node:
                    records["typedef_list"][typedef_name] = typedef_index

            elif root_node.type == "friend_declaration":
                label = (
                    "friend "
                    + root_node.text.decode("UTF-8").replace("friend", "").strip()
                )
                if len(label) > 80:
                    label = label[:77] + "..."
                type_label = "friend"

            elif root_node.type == "static_assert_declaration":
                label = root_node.text.decode("UTF-8")
                if len(label) > 80:
                    label = label[:77] + "..."
                type_label = "static_assert"

            elif root_node.type == "namespace_alias_definition":
                label = root_node.text.decode("UTF-8")
                if len(label) > 80:
                    label = label[:77] + "..."
                type_label = "namespace_alias"

            elif root_node.type == "using_declaration":
                label = root_node.text.decode("UTF-8")
                if len(label) > 80:
                    label = label[:77] + "..."
                type_label = "using"

            elif root_node.type == "attributed_statement":
                attributes = []
                for child in root_node.children:
                    if child.type == "attribute_declaration":
                        for attr_child in child.named_children:
                            if attr_child.type == "attribute":
                                attr_text = attr_child.text.decode("utf-8")
                                attr_name = attr_text.split("(")[0].strip()
                                attributes.append(attr_name)

                label = root_node.text.decode("UTF-8")
                if len(label) > 80:
                    label = label[:77] + "..."
                type_label = "expression_statement"

            elif root_node.type == "new_expression":
                label = root_node.text.decode("UTF-8")
                if len(label) > 80:
                    label = label[:77] + "..."
                type_label = "new"

            excluded_from_graph = {
                "function_definition",
                "preproc_include",
                "preproc_def",
                "preproc_function_def",
                "preproc_call",
                "preproc_if",
                "preproc_ifdef",
                "preproc_elif",
                "preproc_else",
                "using_declaration",
                "alias_declaration",
                "namespace_alias_definition",
            }

            if root_node.type not in excluded_from_graph:
                graph_node_list.append(
                    (
                        index[
                            (root_node.start_point, root_node.end_point, root_node.type)
                        ],
                        root_node.start_point[0],
                        label,
                        type_label,
                    )
                )

    if root_node.type in ["preproc_ifdef", "preproc_if", "preproc_elif"]:
        condition = None
        is_ifndef = False

        if root_node.type == "preproc_ifdef":
            for child in root_node.children:
                if child.type == "#ifndef":
                    is_ifndef = True
                elif child.type == "identifier":
                    condition = child.text.decode("UTF-8")
                    break
        elif root_node.type == "preproc_if" or root_node.type == "preproc_elif":
            found_directive = False
            for child in root_node.children:
                if child.type in ["#if", "#elif"]:
                    found_directive = True
                elif (
                    found_directive
                    and child.is_named
                    and child.type
                    not in [
                        "preproc_elif",
                        "preproc_else",
                        "declaration",
                        "expression_statement",
                    ]
                ):
                    condition = child.text.decode("UTF-8")
                    break

        condition_met = False
        if condition:
            result = evaluate_preprocessor_condition(condition, macro_definitions)
            if result is not None:
                condition_met = (not result) if is_ifndef else result
                if os.environ.get("DEBUG_PREPROC"):
                    print(
                        f"[PREPROC] {root_node.type} condition='{condition}' is_ifndef={is_ifndef} macros={macro_definitions} result={result} condition_met={condition_met}"
                    )
            else:
                condition_met = True
                if os.environ.get("DEBUG_PREPROC"):
                    print(
                        f"[PREPROC] {root_node.type} condition='{condition}' macros={macro_definitions} CANNOT_EVALUATE, including by default"
                    )

        if root_node.type == "preproc_elif":
            if condition_met:
                for child in root_node.children:
                    if child.is_named and child.type not in [
                        "preproc_else",
                        "preproc_elif",
                    ]:
                        root_node, node_list, graph_node_list, records = get_nodes(
                            root_node=child,
                            node_list=node_list,
                            graph_node_list=graph_node_list,
                            index=index,
                            records=records,
                            macro_definitions=macro_definitions,
                        )
        elif root_node.type == "preproc_ifdef" or root_node.type == "preproc_if":
            found_elif_or_else = False
            for child in root_node.children:
                if not child.is_named:
                    continue

                if child.type in ["preproc_elif", "preproc_else"]:
                    if condition_met:
                        continue
                    found_elif_or_else = True

                if child.type == "preproc_elif":
                    root_node, node_list, graph_node_list, records = get_nodes(
                        root_node=child,
                        node_list=node_list,
                        graph_node_list=graph_node_list,
                        index=index,
                        records=records,
                        macro_definitions=macro_definitions,
                    )
                elif child.type == "preproc_else":
                    if not condition_met:
                        for else_child in child.children:
                            if else_child.is_named:
                                root_node, node_list, graph_node_list, records = (
                                    get_nodes(
                                        root_node=else_child,
                                        node_list=node_list,
                                        graph_node_list=graph_node_list,
                                        index=index,
                                        records=records,
                                        macro_definitions=macro_definitions,
                                    )
                                )
                elif condition_met:
                    root_node, node_list, graph_node_list, records = get_nodes(
                        root_node=child,
                        node_list=node_list,
                        graph_node_list=graph_node_list,
                        index=index,
                        records=records,
                        macro_definitions=macro_definitions,
                    )

    elif root_node.type == "preproc_else":
        pass

    elif root_node.type in [
        "preproc_include",
        "preproc_def",
        "preproc_function_def",
        "preproc_call",
    ]:
        pass

    else:
        for child in root_node.children:
            root_node, node_list, graph_node_list, records = get_nodes(
                root_node=child,
                node_list=node_list,
                graph_node_list=graph_node_list,
                index=index,
                records=records,
                macro_definitions=macro_definitions,
            )

    return root_node, node_list, graph_node_list, records
