"""JavaScript parser — extends CustomParser with JS-specific token creation."""

from .custom_parser import CustomParser


class JavaScriptParser(CustomParser):
    def __init__(self, src_language, src_code):
        super().__init__(src_language, src_code)

    def check_declaration(self, current_node):
        """Return True if *current_node* is a variable/parameter declaration."""
        parent_types = [
            "variable_declarator",  # var / let / const
            "formal_parameters",  # function params
            "catch_clause",  # catch (e)
        ]
        current_types = ["identifier"]
        if (
            current_node.parent is not None
            and current_node.parent.type in parent_types
            and current_node.type in current_types
        ):
            return True
        return False

    def get_type(self, node):
        """JS is dynamically typed — always return ``"var"``."""
        return "var"

    def scope_check(self, parent_scope, child_scope):
        for p in parent_scope:
            if p not in child_scope:
                return False
        return True

    def longest_scope_match(self, name_matches, symbol_table):
        scope_array = list(map(lambda x: symbol_table["scope_map"][x[0]], name_matches))
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
        # Identifiers inside these parent types are *definitions* (method/function names),
        # not variable references.
        remove_list = [
            "function_declaration",
            "method_definition",
            "call_expression",
            "new_expression",
            "member_expression",
        ]

        block_types = [
            "program",
            "statement_block",
            "class_body",
            "switch_body",
            "if_statement",
            "while_statement",
            "for_statement",
            "for_in_statement",
            "do_statement",
            "switch_statement",
            "try_statement",
            "catch_clause",
            "finally_clause",
            "function_declaration",
            "method_definition",
            "arrow_function",
        ]

        if root_node.is_named and root_node.type in block_types:
            symbol_table["scope_id"] = symbol_table["scope_id"] + 1
            symbol_table["scope_stack"].append(symbol_table["scope_id"])

        if (
            root_node.is_named
            and (
                len(root_node.children) == 0
                or root_node.type in ("string", "string_fragment", "regex")
            )
            and root_node.type != "comment"
        ):
            index = self.index[
                (root_node.start_point, root_node.end_point, root_node.type)
            ]
            label[index] = root_node.text.decode("UTF-8")
            start_line[index] = root_node.start_point[0]
            all_tokens.append(index)

            symbol_table["scope_map"][index] = symbol_table["scope_stack"].copy()

            current_node = root_node

            # Mark method/function definition names
            if (
                current_node.parent is not None
                and current_node.parent.type in remove_list
            ):
                method_map.append(index)
                if (
                    current_node.next_named_sibling is not None
                    and current_node.next_named_sibling.type == "arguments"
                ):
                    method_calls.append(index)

            # Handle member_expression (obj.method) — mark the property as a method
            if (
                current_node.parent is not None
                and current_node.parent.type == "member_expression"
            ):
                obj_node = current_node.parent.child_by_field_name("object")
                prop_node = current_node.parent.child_by_field_name("property")
                if obj_node is not None and prop_node is not None:
                    obj_index = self.index.get(
                        (obj_node.start_point, obj_node.end_point, obj_node.type)
                    )
                    cur_index = self.index.get(
                        (
                            current_node.start_point,
                            current_node.end_point,
                            current_node.type,
                        )
                    )
                    if (
                        cur_index is not None
                        and obj_index is not None
                        and cur_index == obj_index
                    ):
                        # This identifier is the object, not the property
                        pass
                    elif (
                        current_node.parent.parent is not None
                        and current_node.parent.parent.type == "call_expression"
                    ):
                        method_map.append(index)
                    label[index] = current_node.parent.text.decode("UTF-8")

            if self.check_declaration(current_node):
                variable_name = label[index]
                declaration[index] = variable_name
                variable_type = self.get_type(current_node)
                if variable_type is not None:
                    symbol_table["data_type"][index] = variable_type
            else:
                current_scope = symbol_table["scope_map"][index]

                name_matches = []
                for ind, var in declaration.items():
                    if var == label[index]:
                        parent_scope = symbol_table["scope_map"][ind]
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
