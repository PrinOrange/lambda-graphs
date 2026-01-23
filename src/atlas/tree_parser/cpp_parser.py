from ..tree_parser.custom_parser import CustomParser


class CppParser(CustomParser):
    def __init__(self, src_language, src_code):
        super().__init__(src_language, src_code)

    def check_declaration(self, current_node):
        """
        Check if the current node is a variable declaration in C++.
        C++ declarations can be:
        - init_declarator (e.g., int x = 5;)
        - Direct child of declaration (e.g., int x;)
        - parameter_declaration (function parameters)
        - pointer_declarator (pointer variables)
        - reference_declarator (reference variables)
        - auto declarations
        - structured bindings
        """
        parent_types = ["init_declarator", "parameter_declaration", "optional_parameter_declaration",
                        "pointer_declarator", "reference_declarator", "array_declarator"]
        current_types = ["identifier"]

        if (
            current_node.parent is not None
            and current_node.parent.type in parent_types
            and current_node.type in current_types
        ):
            if current_node.parent.type == "init_declarator":
                declarator = current_node.parent.children[0] if current_node.parent.children else None
                if declarator:
                    if declarator == current_node:
                        return True
                    if declarator.type in ["pointer_declarator", "reference_declarator", "array_declarator"]:
                        if self.find_identifier_in_declarator(declarator) == current_node:
                            return True
            elif current_node.parent.type in ["pointer_declarator", "reference_declarator"]:
                if current_node.type == "identifier":
                    return True
            elif current_node.parent.type == "array_declarator":
                if current_node.parent.children and current_node.parent.children[0] == current_node:
                    return True
            elif current_node.parent.type in ["parameter_declaration", "optional_parameter_declaration"]:
                return True

        if (
            current_node.parent is not None
            and current_node.parent.type == "declaration"
            and current_node.type == "identifier"
        ):
            for i, child in enumerate(current_node.parent.children):
                if child == current_node and i > 0:
                    prev_sibling = current_node.parent.children[i-1]
                    if prev_sibling.type in ['primitive_type', 'type_identifier', 'sized_type_specifier',
                                             'struct_specifier', 'class_specifier', 'union_specifier',
                                             'enum_specifier', 'storage_class_specifier', 'type_qualifier',
                                             'auto', 'template_type', 'qualified_identifier']:
                        return True
            return False

        if current_node.parent is not None and current_node.parent.type == "declarator":
            if current_node.parent.parent is not None and current_node.parent.parent.type in ["declaration", "parameter_declaration"]:
                return True

        if current_node.parent is not None and current_node.parent.type == "function_declarator":
            declarator = current_node.parent.child_by_field_name("declarator")
            if declarator == current_node:
                return True

        if current_node.parent is not None and current_node.parent.type == "field_declaration":
            for i, child in enumerate(current_node.parent.children):
                if child == current_node and i > 0:
                    prev_sibling = current_node.parent.children[i-1]
                    if prev_sibling.type in ['primitive_type', 'type_identifier', 'sized_type_specifier',
                                             'template_type', 'qualified_identifier', 'auto']:
                        return True

        return False

    def find_identifier_in_declarator(self, node):
        """Recursively find the identifier within a declarator node."""
        if node.type == "identifier":
            return node
        for child in node.children:
            result = self.find_identifier_in_declarator(child)
            if result is not None:
                return result
        return None

    def get_type(self, node):
        """
        Given a declarator node, return the variable type of the identifier.
        C++ type specifiers include: primitive_type, type_identifier, template_type, etc.

        This function traverses up the tree to find the declaration or parameter_declaration node,
        then searches for the type specifier among its children.
        """
        datatypes = ['primitive_type', 'type_identifier', 'sized_type_specifier',
                     'struct_specifier', 'class_specifier', 'union_specifier', 'enum_specifier',
                     'template_type', 'qualified_identifier', 'auto', 'decltype']

        current = node

        while current is not None:
            if current.type in ["declaration", "parameter_declaration", "optional_parameter_declaration", "field_declaration"]:
                for child in current.children:
                    if child.type in datatypes:
                        return child.text.decode('utf-8')
                return None

            current = current.parent

        return None

    def scope_check(self, parent_scope, child_scope):
        """Check if parent_scope is a subset of child_scope."""
        for p in parent_scope:
            if p not in child_scope:
                return False
        return True

    def longest_scope_match(self, name_matches, symbol_table):
        """Given a list of name matches, return the longest scope match."""
        scope_array = list(map(lambda x: symbol_table['scope_map'][x[0]], name_matches))
        max_val = max(scope_array, key=lambda x: len(x))
        for i in range(len(scope_array)):
            if scope_array[i] == max_val:
                return name_matches[i][0]

    def create_all_tokens(
        self,
        src_code,
        root_node,
        all_tokens,
        label,
        method_map,
        method_calls,
        start_line,
        declaration,
        declaration_map,
        symbol_table,
    ):
        """
        Create tokens for C++ language.
        Handles C++-specific constructs like classes, namespaces, templates, references, etc.
        """
        remove_list = ["function_definition", "call_expression", "class_specifier", "struct_specifier"]

        block_types = [
            "compound_statement",
            "if_statement",
            "while_statement",
            "for_statement",
            "for_range_loop",
            "do_statement",
            "switch_statement",
            "case_statement",
            "function_definition",
            "class_specifier",
            "struct_specifier",
            "namespace_definition",
            "try_statement",
            "catch_clause",
            "lambda_expression",
        ]

        if root_node.is_named and root_node.type in block_types:
            symbol_table["scope_id"] = symbol_table["scope_id"] + 1
            symbol_table["scope_stack"].append(symbol_table["scope_id"])

        if (
            root_node.is_named
            and (len(root_node.children) == 0 or root_node.type in ["string_literal", "raw_string_literal"])
            and root_node.type != "comment"
        ):
            index = self.index[(root_node.start_point, root_node.end_point, root_node.type)]

            label[index] = root_node.text.decode("UTF-8")

            start_line[index] = root_node.start_point[0]

            all_tokens.append(index)

            symbol_table["scope_map"][index] = symbol_table["scope_stack"].copy()

            current_node = root_node

            if current_node.parent is not None and current_node.parent.type in remove_list:
                method_map.append(index)
                if current_node.next_named_sibling is not None and current_node.next_named_sibling.type == "argument_list":
                    method_calls.append(index)

            if current_node.parent is not None and current_node.parent.type == "call_expression":
                function_node = current_node.parent.child_by_field_name("function")
                if function_node == current_node or (function_node and self.find_identifier_in_declarator(function_node) == current_node):
                    method_map.append(index)
                    method_calls.append(index)

            if current_node.parent is not None and current_node.parent.type == "field_expression":
                field_node = current_node.parent.child_by_field_name("field")
                if field_node is not None:
                    field_index = self.index[(field_node.start_point, field_node.end_point, field_node.type)]
                    current_index = self.index[(current_node.start_point, current_node.end_point, current_node.type)]
                    if field_index == current_index:
                        method_map.append(current_index)

                while current_node.parent is not None and current_node.parent.type == "field_expression":
                    current_node = current_node.parent

                if current_node.parent is not None and current_node.parent.type == "call_expression":
                    method_map.append(index)
                    method_calls.append(index)
                label[index] = current_node.text.decode("UTF-8")

            if current_node.parent is not None and current_node.parent.type == "qualified_identifier":
                if current_node.parent.children and current_node.parent.children[-1] == current_node:
                    label[index] = current_node.parent.text.decode("UTF-8")

            if current_node.parent is not None and current_node.parent.type == "template_function":
                method_map.append(index)
                if current_node.next_named_sibling is not None and current_node.next_named_sibling.type == "template_argument_list":
                    method_calls.append(index)

            if self.check_declaration(current_node):
                variable_name = label[index]
                declaration[index] = variable_name

                variable_type = self.get_type(current_node.parent)
                if variable_type is not None:
                    symbol_table["data_type"][index] = variable_type
            else:
                current_scope = symbol_table['scope_map'][index]

                if current_node.parent is not None and current_node.parent.type == "field_expression":
                    field_variable = current_node.parent.children[-1]
                    field_variable_name = field_variable.text.decode('utf-8')

                    for (ind, var) in declaration.items():
                        if var == field_variable_name:
                            parent_scope = symbol_table['scope_map'][ind]
                            if self.scope_check(parent_scope, current_scope):
                                declaration_map[index] = ind
                                break
                elif current_node.parent is not None and current_node.parent.type == "qualified_identifier":
                    qualified_name = current_node.parent.text.decode('utf-8')
                    name_matches = []
                    for (ind, var) in declaration.items():
                        if var == qualified_name or var == label[index]:
                            parent_scope = symbol_table['scope_map'][ind]
                            if self.scope_check(parent_scope, current_scope):
                                name_matches.append((ind, var))

                    if name_matches:
                        closest_index = self.longest_scope_match(name_matches, symbol_table)
                        declaration_map[index] = closest_index
                else:
                    name_matches = []
                    for (ind, var) in declaration.items():
                        if var == label[index]:
                            parent_scope = symbol_table['scope_map'][ind]
                            if self.scope_check(parent_scope, current_scope):
                                name_matches.append((ind, var))

                    if name_matches:
                        closest_index = self.longest_scope_match(name_matches, symbol_table)
                        declaration_map[index] = closest_index

        else:
            for child in root_node.children:
                self.create_all_tokens(
                    src_code,
                    child,
                    all_tokens,
                    label,
                    method_map,
                    method_calls,
                    start_line,
                    declaration,
                    declaration_map,
                    symbol_table,
                )

        if root_node.is_named and root_node.type in block_types:
            symbol_table["scope_stack"].pop(-1)

        return (
            all_tokens,
            label,
            method_map,
            method_calls,
            start_line,
            declaration,
            declaration_map,
            symbol_table,
        )
