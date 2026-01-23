from ..tree_parser.custom_parser import CustomParser


class CParser(CustomParser):
    def __init__(self, src_language, src_code):
        super().__init__(src_language, src_code)
        self.struct_definitions = {}
        self.typedef_map = {}
        self._parse_struct_definitions()
        self._parse_typedefs()

    def check_declaration(self, current_node):
        """
        Check if the current node is a variable declaration in C.
        C declarations can be:
        - init_declarator (e.g., int x = 5;)
        - Direct child of declaration (e.g., int x;)
        - parameter_declaration (function parameters)
        - pointer_declarator (pointer variables)
        """
        parent_types = ["init_declarator", "parameter_declaration", "pointer_declarator", "array_declarator"]
        current_types = ["identifier"]

        if (
            current_node.parent is not None
            and current_node.parent.type in parent_types
            and current_node.type in current_types
        ):
            if current_node.parent.type == "init_declarator":
                if current_node.parent.children and current_node.parent.children[0] == current_node:
                    return True
                if current_node.parent.children[0].type == "pointer_declarator":
                    pointer_node = current_node.parent.children[0]
                    if self.find_identifier_in_declarator(pointer_node) == current_node:
                        return True
            elif current_node.parent.type == "pointer_declarator":
                if current_node.type == "identifier":
                    return True
            elif current_node.parent.type == "array_declarator":
                if current_node.parent.children and current_node.parent.children[0] == current_node:
                    return True
            elif current_node.parent.type == "parameter_declaration":
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
                                             'struct_specifier', 'union_specifier', 'enum_specifier',
                                             'storage_class_specifier', 'type_qualifier']:
                        return True
            return False

        if current_node.parent is not None and current_node.parent.type == "declarator":
            if current_node.parent.parent is not None and current_node.parent.parent.type in ["declaration", "parameter_declaration"]:
                return True

        if current_node.parent is not None and current_node.parent.type == "function_declarator":
            if current_node.parent.children and current_node.parent.children[0] == current_node:
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
        Given a declarator node, return the variable type of the identifier INCLUDING pointer indicators.
        C type specifiers include: primitive_type, type_identifier, sized_type_specifier, etc.

        This function traverses up the tree to find the declaration or parameter_declaration node,
        then searches for the type specifier among its children. This handles complex nested
        declarators like int **pp, int ***ppp, int (*ptr_arr)[10], etc.

        Returns the full type including pointers, e.g., "char*", "int**", "uint32_t*"
        """
        datatypes = ['primitive_type', 'type_identifier', 'sized_type_specifier',
                     'struct_specifier', 'union_specifier', 'enum_specifier']

        current = node
        pointer_count = 0
        is_array = False

        while current is not None:
            if current.type == "pointer_declarator":
                for child in current.children:
                    if child.type == "*":
                        pointer_count += 1

            if current.type == "array_declarator":
                is_array = True

            if current.type in ["declaration", "parameter_declaration"]:
                base_type = None
                for child in current.children:
                    if child.type in datatypes:
                        base_type = child.text.decode('utf-8')
                        break

                if base_type:
                    if pointer_count > 0:
                        base_type += "*" * pointer_count
                    elif is_array:
                        base_type += "*"

                    return self.expand_typedef(base_type)

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
        Create tokens for C language.
        Handles C-specific constructs like pointers, arrays, function calls, etc.
        """
        remove_list = ["function_definition", "call_expression"]

        block_types = [
            "compound_statement",
            "if_statement",
            "while_statement",
            "for_statement",
            "do_statement",
            "switch_statement",
            "case_statement",
            "function_definition",
        ]

        if root_node.is_named and root_node.type in block_types:
            symbol_table["scope_id"] = symbol_table["scope_id"] + 1
            symbol_table["scope_stack"].append(symbol_table["scope_id"])

        if (
            root_node.is_named
            and (len(root_node.children) == 0 or root_node.type in ["string_literal", "variadic_parameter"])
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
                if current_node.parent.children and current_node.parent.children[0] == current_node:
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

    def _parse_struct_definitions(self):
        """
        Parse all struct definitions in the code and build a mapping of
        struct_name -> {field_name: field_type}

        This allows us to resolve struct field types when we encounter
        field_expression nodes like p.x or ptr->field.
        """
        def traverse_for_structs(node):
            if node.type == "struct_specifier":
                struct_name = None
                field_list = None

                for child in node.children:
                    if child.type == "type_identifier":
                        struct_name = child.text.decode('utf-8')
                    elif child.type == "field_declaration_list":
                        field_list = child

                if struct_name and field_list:
                    fields = {}
                    for field_decl in field_list.children:
                        if field_decl.type == "field_declaration":
                            field_type = None
                            field_names = []

                            for fc in field_decl.children:
                                if fc.type in ['primitive_type', 'type_identifier', 'sized_type_specifier', 'struct_specifier']:
                                    if fc.type == 'struct_specifier':
                                        for sc in fc.children:
                                            if sc.type == "type_identifier":
                                                field_type = "struct " + sc.text.decode('utf-8')
                                                break
                                    else:
                                        field_type = fc.text.decode('utf-8')

                                elif fc.type == "field_identifier":
                                    field_names.append(fc.text.decode('utf-8'))
                                elif fc.type == "pointer_declarator":
                                    pointer_count = fc.text.decode('utf-8').count('*')
                                    for pchild in fc.named_children:
                                        if pchild.type == "field_identifier":
                                            field_names.append(pchild.text.decode('utf-8'))
                                            break
                                    if field_type:
                                        field_type += "*" * pointer_count
                                elif fc.type == "array_declarator":
                                    for achild in fc.children:
                                        if achild.type == "field_identifier":
                                            field_names.append(achild.text.decode('utf-8'))
                                            break
                                    if field_type:
                                        field_type += "*"

                            for fname in field_names:
                                fields[fname] = field_type if field_type else "unknown"

                    self.struct_definitions[struct_name] = fields

            for child in node.children:
                traverse_for_structs(child)

        traverse_for_structs(self.root_node)

    def get_struct_field_type(self, struct_name, field_name):
        """
        Get the type of a field in a struct.

        Args:
            struct_name: Name of the struct (without 'struct' keyword)
            field_name: Name of the field

        Returns:
            Type string or "unknown" if not found
        """
        if struct_name.startswith('struct '):
            struct_name = struct_name[7:]

        if struct_name in self.struct_definitions:
            return self.struct_definitions[struct_name].get(field_name, "unknown")
        return "unknown"

    def _parse_typedefs(self):
        """
        Parse all typedef declarations and build a mapping of
        typedef_name -> actual_type

        This allows us to expand typedef aliases when resolving types.
        """
        def traverse_for_typedefs(node):
            if node.type == "type_definition":
                children = [c for c in node.children if c.type != ';' and c.type != 'typedef']

                if len(children) < 2:
                    return

                typedef_name = None
                actual_type = None
                pointer_count = 0

                if any(c.type == 'pointer_declarator' for c in children):
                    if children[0].type in ['primitive_type', 'sized_type_specifier', 'type_identifier']:
                        actual_type = children[0].text.decode('utf-8')

                    for child in children:
                        if child.type == 'pointer_declarator':
                            pointer_count = child.text.decode('utf-8').count('*')

                            def find_typedef_name(node):
                                if node.type in ['type_identifier', 'identifier']:
                                    return node.text.decode('utf-8')
                                for c in node.named_children:
                                    result = find_typedef_name(c)
                                    if result:
                                        return result
                                return None

                            typedef_name = find_typedef_name(child)

                elif any(c.type == 'function_declarator' for c in children):
                    if children[0].type in ['primitive_type', 'type_identifier']:
                        actual_type = "function_pointer"

                    for child in children:
                        if child.type == 'function_declarator':
                            for fc in child.children:
                                if fc.type == 'pointer_declarator':
                                    for pdc in fc.named_children:
                                        if pdc.type in ['identifier', 'type_identifier']:
                                            typedef_name = pdc.text.decode('utf-8')
                                            break

                elif any(c.type == 'struct_specifier' for c in children):
                    for i, child in enumerate(children):
                        if child.type == 'struct_specifier':
                            for sc in child.children:
                                if sc.type == "type_identifier":
                                    actual_type = "struct " + sc.text.decode('utf-8')
                                    break
                            if not actual_type:
                                actual_type = child.text.decode('utf-8')

                        elif child.type in ['type_identifier', 'primitive_type'] and i > 0:
                            typedef_name = child.text.decode('utf-8')

                else:
                    if len(children) >= 2:
                        if children[0].type in ['primitive_type', 'sized_type_specifier', 'type_identifier']:
                            actual_type = children[0].text.decode('utf-8')

                        if children[-1].type in ['type_identifier', 'primitive_type']:
                            typedef_name = children[-1].text.decode('utf-8')

                if actual_type and pointer_count > 0:
                    actual_type += "*" * pointer_count

                if typedef_name and actual_type:
                    self.typedef_map[typedef_name] = actual_type

            for child in node.children:
                traverse_for_typedefs(child)

        traverse_for_typedefs(self.root_node)

    def expand_typedef(self, type_name):
        """
        Recursively expand a typedef to its actual type.

        Args:
            type_name: Type name (possibly a typedef)

        Returns:
            Expanded type string, or original if not a typedef
        """
        if type_name.endswith('*'):
            base = type_name.rstrip('*')
            stars = '*' * type_name.count('*')
            expanded = self.expand_typedef(base.strip())
            return expanded + stars

        if type_name in self.typedef_map:
            return self.expand_typedef(self.typedef_map[type_name])

        return type_name
