import traceback

import networkx as nx
from loguru import logger

from ...utils import c_nodes
from .CFG import CFGGraph


class CFGGraph_c(CFGGraph):
    def __init__(self, src_language, src_code, properties, root_node, parser):
        super().__init__(src_language, src_code, properties, root_node, parser)

        self.node_list = None
        self.statement_types = c_nodes.statement_types
        self.CFG_node_list = []
        self.CFG_edge_list = []
        self.records = {
            "basic_blocks": {},
            "function_list": {},
            "return_type": {},
            "function_calls": {},
            "switch_child_map": {},
            "label_statement_map": {},
            "return_statement_map": {},
            "function_pointer_map": {},
        }
        self.index_counter = max(self.index.values())
        self.CFG_node_indices = []

        self.symbol_table = self.parser.symbol_table
        self.declaration = self.parser.declaration
        self.declaration_map = self.parser.declaration_map
        self.CFG_node_list, self.CFG_edge_list = self.CFG_c()
        self.graph = self.to_networkx(self.CFG_node_list, self.CFG_edge_list)

    def get_index(self, node):
        """Get the unique index for a given AST node"""
        return self.index[(node.start_point, node.end_point, node.type)]

    def get_basic_blocks(self, CFG_node_list, CFG_edge_list):
        """Partition CFG into basic blocks using weakly connected components"""
        G = self.to_networkx(CFG_node_list, CFG_edge_list)
        components = nx.weakly_connected_components(G)
        block_index = 1
        for block in components:
            block_list = sorted(list(block))
            self.records["basic_blocks"][block_index] = block_list
            block_index += 1

    def get_key(self, val, dictionary):
        """Find the key in dictionary where val is in the value list"""
        for key, value in dictionary.items():
            if val in value:
                return key
        return None

    def get_containing_function(self, node):
        """Find the enclosing function definition for a given node"""
        while node is not None:
            if node.type == "function_definition":
                return node
            node = node.parent
        return None

    def get_next_index(self, current_node, node_list):
        """
        Find the next executable statement after current_node.
        Handles:
        - Sequential statements (next_named_sibling)
        - End of blocks (traverse up to parent)
        - Loop back edges
        - Function boundaries
        """
        next_node = current_node.next_named_sibling

        while next_node is None:
            parent = current_node.parent
            if parent is None:
                return (2, None)

            if parent.type in self.statement_types["loop_control_statement"]:
                if (parent.start_point, parent.end_point, parent.type) in node_list:
                    return (self.get_index(parent), parent)

            if parent.type in self.statement_types["control_statement"]:
                current_node = parent
                next_node = current_node.next_named_sibling
                continue

            if parent.type == "function_definition":
                return (2, None)

            if parent.type in self.statement_types["statement_holders"]:
                current_node = parent
                next_node = current_node.next_named_sibling
                continue

            current_node = parent
            next_node = current_node.next_named_sibling

        if next_node.type == "compound_statement" and len(list(next_node.named_children)) == 0:
            current_node = next_node
            return self.get_next_index(current_node, node_list)

        if next_node.type == "compound_statement":
            children_list = list(next_node.named_children)
            if children_list:
                first_child = children_list[0]
                if (first_child.start_point, first_child.end_point, first_child.type) in node_list:
                    return (self.get_index(first_child), first_child)

        if (next_node.start_point, next_node.end_point, next_node.type) in node_list:
            return (self.get_index(next_node), next_node)

        return self.get_next_index(next_node, node_list)

    def is_last_in_control_block(self, node):
        """
        Check if a node is the last statement in a control flow block (if/else/loop).
        These nodes should NOT have edges added in the sequential flow step,
        as they will be handled by the control flow step.

        Handles two cases:
        1. Last statement in a compound_statement that belongs to a control structure
        2. Single statement (no braces) that is the consequence/body of a control structure
        """
        if node.parent is None:
            return False

        parent = node.parent

        if parent.type == "compound_statement":
            children = list(parent.named_children)
            if children and children[-1] == node:
                grandparent = parent.parent
                if grandparent and grandparent.type in ["if_statement", "while_statement", "for_statement", "do_statement", "else_clause"]:
                    return True

        if parent.type in ["if_statement", "while_statement", "for_statement", "do_statement"]:
            consequence = parent.child_by_field_name("consequence")
            body = parent.child_by_field_name("body")

            if consequence and consequence == node:
                return True

            if body and body == node:
                return True

        if parent.type == "else_clause":
            children = list(parent.named_children)
            if children and node in children:
                return True

        return False

    def get_block_last_line(self, current_node, body_field="body"):
        """
        Find the last executable statement in a block.
        Used for connecting end of if/else/loop bodies to next statement.
        """
        block_node = current_node.child_by_field_name(body_field)

        if block_node is None:
            for child in current_node.children:
                if child.type == "compound_statement":
                    block_node = child
                    break

        if block_node is None:
            return (current_node, current_node.type)

        while block_node.type in self.statement_types["statement_holders"]:
            children = list(block_node.named_children)
            if not children:
                return (current_node, current_node.type)

            last_child = children[-1]

            if last_child.type in self.statement_types["node_list_type"]:
                return (last_child, last_child.type)

            block_node = last_child

        return (block_node, block_node.type)

    def edge_first_line(self, node, node_list):
        """
        Find the first executable line in a function/block and create edge.
        Returns the first statement node and its index.
        """
        body_node = None

        if node.type == "function_definition":
            body_node = node.child_by_field_name("body")

        if body_node is None:
            for child in node.children:
                if child.type == "compound_statement":
                    body_node = child
                    break

        if body_node is None:
            return None

        for child in body_node.named_children:
            if (child.start_point, child.end_point, child.type) in node_list:
                return (self.get_index(child), child)

        return None

    def add_edge(self, src, dest, edge_type, additional_data=None):
        """Add an edge to the CFG edge list with validation"""
        if src is None or dest is None:
            logger.error(f"Attempting to add edge with None: {src} -> {dest}")
            return

        if additional_data:
            self.CFG_edge_list.append((src, dest, edge_type, additional_data))
        else:
            self.CFG_edge_list.append((src, dest, edge_type))

    def track_function_pointers(self, root_node):
        """
        Track function pointer assignments in the program.
        Records mappings like: fptr -> add when we see fptr = &add
        """
        if root_node.type == "assignment_expression":
            left = root_node.child_by_field_name("left")
            right = root_node.child_by_field_name("right")

            if left and right:
                if right.type == "pointer_expression":
                    arg = right.child_by_field_name("argument")
                    if arg and arg.type == "identifier":
                        ptr_var = left.text.decode('utf-8')
                        target_func = arg.text.decode('utf-8')
                        self.records["function_pointer_map"][ptr_var] = target_func

        for child in root_node.children:
            self.track_function_pointers(child)

    def function_list(self, root_node, node_list):
        """
        Build a map of all function calls in the program.
        Maps function signatures to their call sites.

        Handles both direct calls (add(10, 5)) and function pointer calls (fptr(10, 5)).
        """
        if root_node.type == "call_expression":
            function_node = root_node.child_by_field_name("function")
            if function_node:
                if function_node.type == "identifier":
                    func_name = function_node.text.decode('utf-8')

                    if func_name in self.records["function_pointer_map"]:
                        actual_func_name = self.records["function_pointer_map"][func_name]
                        func_name = actual_func_name

                    parent_stmt = root_node
                    while parent_stmt and parent_stmt.type not in self.statement_types["node_list_type"]:
                        parent_stmt = parent_stmt.parent

                    if parent_stmt and (parent_stmt.start_point, parent_stmt.end_point, parent_stmt.type) in node_list:
                        parent_index = self.get_index(parent_stmt)
                        call_index = self.get_index(function_node)

                        args_node = root_node.child_by_field_name("arguments")
                        signature = self.get_call_signature(args_node)

                        key = (func_name, signature)
                        if key not in self.records["function_calls"]:
                            self.records["function_calls"][key] = []
                        self.records["function_calls"][key].append((call_index, parent_index))

        for child in root_node.children:
            self.function_list(child, node_list)

    def get_argument_type(self, arg_node):
        """
        Infer the type of an argument expression.
        Returns the type as a string, or "unknown" if type cannot be determined.

        Handles:
        - Identifiers (variables): Look up in symbol_table
        - Literals: Map to C types
        - Cast expressions: Use the cast type
        - Arithmetic/binary expressions: Infer from operands
        - Function calls: Look up return type
        - Pointer/address operations: Modify base type
        - Array subscript: Get element type
        - Field access: Look up field type
        """

        if arg_node is None:
            return "unknown"

        node_type = arg_node.type

        if node_type == "identifier":
            var_name = arg_node.text.decode('utf-8')

            arg_index_key = (arg_node.start_point, arg_node.end_point, arg_node.type)
            if arg_index_key in self.index:
                arg_index = self.index[arg_index_key]

                if arg_index in self.declaration_map:
                    decl_index = self.declaration_map[arg_index]
                    if decl_index in self.symbol_table["data_type"]:
                        return self.symbol_table["data_type"][decl_index]

            for decl_idx, decl_name in self.declaration.items():
                if decl_name == var_name:
                    if decl_idx in self.symbol_table["data_type"]:
                        var_type = self.symbol_table["data_type"][decl_idx]
                        if hasattr(self.parser, 'expand_typedef'):
                            return self.parser.expand_typedef(var_type)
                        return var_type

            return "unknown"

        elif node_type == "number_literal":
            text = arg_node.text.decode('utf-8').lower()
            if '.' in text or 'e' in text:
                if text.endswith('f'):
                    return "float"
                return "double"
            else:
                if text.endswith('ll') or text.endswith('LL'):
                    return "long long"
                elif text.endswith('l') or text.endswith('L'):
                    return "long"
                elif text.endswith('u') or text.endswith('U'):
                    return "unsigned int"
                else:
                    return "int"

        elif node_type == "string_literal":
            return "char*"

        elif node_type == "char_literal":
            return "char"

        elif node_type == "true" or node_type == "false":
            return "int"

        elif node_type == "null":
            return "void*"

        elif node_type == "cast_expression":
            type_desc = arg_node.child_by_field_name("type")
            if type_desc:
                for child in type_desc.children:
                    if child.type in ["primitive_type", "type_identifier", "sized_type_specifier"]:
                        return child.text.decode('utf-8')
            return "unknown"

        elif node_type == "pointer_expression":
            operand = arg_node.child_by_field_name("argument")
            if operand:
                operand_type = self.get_argument_type(operand)
                if operand_type.endswith('*'):
                    return operand_type[:-1].strip()
            return "unknown"

        elif node_type == "unary_expression":
            operator = arg_node.child_by_field_name("operator")
            if operator and operator.text.decode('utf-8') == '&':
                operand = arg_node.child_by_field_name("argument")
                if operand:
                    operand_type = self.get_argument_type(operand)
                    if operand_type != "unknown":
                        return operand_type + "*"
            return "unknown"

        elif node_type == "binary_expression":
            left = arg_node.child_by_field_name("left")
            right = arg_node.child_by_field_name("right")

            if left and right:
                left_type = self.get_argument_type(left)
                right_type = self.get_argument_type(right)

                if "double" in left_type or "double" in right_type:
                    return "double"
                elif "float" in left_type or "float" in right_type:
                    return "float"
                elif "long" in left_type or "long" in right_type:
                    return "long"
                elif left_type != "unknown":
                    return left_type
                elif right_type != "unknown":
                    return right_type

            return "int"

        elif node_type == "subscript_expression":
            array = arg_node.child_by_field_name("argument")
            if array:
                array_type = self.get_argument_type(array)
                if array_type.endswith('[]'):
                    return array_type[:-2]
                elif array_type.endswith('*'):
                    return array_type[:-1].strip()
            return "unknown"

        elif node_type == "field_expression":
            field = arg_node.child_by_field_name("field")
            argument = arg_node.child_by_field_name("argument")

            if field and field.type in ["field_identifier", "identifier"]:
                field_name = field.text.decode('utf-8')

                if argument:
                    struct_type = self.get_argument_type(argument)

                    base_type = struct_type.rstrip('*').strip()

                    if hasattr(self.parser, 'struct_definitions'):
                        field_type = self.parser.get_struct_field_type(base_type, field_name)
                        if field_type != "unknown":
                            return field_type

            return "unknown"

        elif node_type == "call_expression":
            function = arg_node.child_by_field_name("function")
            if function and function.type == "identifier":
                func_name = function.text.decode('utf-8')

                for (name, sig), return_type in self.records["return_type"].items():
                    if name == func_name:
                        return return_type if return_type else "unknown"

            return "unknown"

        elif node_type == "parenthesized_expression":
            for child in arg_node.named_children:
                return self.get_argument_type(child)
            return "unknown"

        elif node_type == "sizeof_expression":
            return "size_t"

        elif node_type == "conditional_expression":
            consequence = arg_node.child_by_field_name("consequence")
            if consequence:
                return self.get_argument_type(consequence)
            return "unknown"

        elif node_type == "comma_expression":
            children = list(arg_node.named_children)
            if children:
                return self.get_argument_type(children[-1])
            return "unknown"

        elif node_type == "update_expression":
            argument = arg_node.child_by_field_name("argument")
            if argument:
                return self.get_argument_type(argument)
            return "unknown"

        else:
            return "unknown"

    def get_call_signature(self, args_node):
        """
        Extract the signature (parameter types) from a function call.
        Uses type inference to determine actual argument types.

        Returns: tuple of type strings, e.g., ("int", "char*", "double")
        """
        signature = []

        if args_node is None:
            return tuple(signature)

        for arg in args_node.named_children:
            arg_type = self.get_argument_type(arg)
            signature.append(arg_type)

        return tuple(signature)

    def add_function_call_edges(self, node_list):
        """
        Add edges for function calls and returns.
        Connects call sites to function definitions and returns back to callers.

        Supports:
        - Exact signature matching
        - Variadic functions
        - Fuzzy matching by name when signature can't be inferred
        """
        for (func_name, call_signature), call_sites in self.records["function_calls"].items():
            func_key = (func_name, call_signature)
            func_index = None

            if func_key in self.records["function_list"]:
                func_index = self.records["function_list"][func_key]
            else:

                for (def_name, def_signature), idx in self.records["function_list"].items():
                    if def_name == func_name and len(def_signature) > 0 and def_signature[-1] == '...':
                        required_params = def_signature[:-1]
                        if len(call_signature) >= len(required_params):
                            func_index = idx
                            break

                if func_index is None and 'unknown' in call_signature:
                    for (def_name, def_signature), idx in self.records["function_list"].items():
                        if def_name == func_name and len(def_signature) == len(call_signature):
                            func_index = idx
                            break

            if func_index is not None:
                for call_id, parent_id in call_sites:
                    self.add_edge(parent_id, func_index, f"function_call|{call_id}")

                    parent_node = None
                    for key, node in node_list.items():
                        if self.get_index(node) == parent_id:
                            parent_node = node
                            break

                    is_parent_return = parent_node and parent_node.type == "return_statement"

                    if func_index in self.records["return_statement_map"]:
                        for return_id in self.records["return_statement_map"][func_index]:
                            if not is_parent_return:
                                self.add_edge(return_id, parent_id, "function_return")

    def find_enclosing_loop(self, node):
        """Find the nearest enclosing loop for break/continue statements"""
        while node:
            if node.type in self.statement_types["loop_control_statement"]:
                return node
            node = node.parent
        return None

    def CFG_c(self):
        """
        Main CFG construction function for C language.
        Returns (CFG_node_list, CFG_edge_list).

        This implements the multi-pass algorithm:
        1. Extract statement nodes from AST
        2. Create initial sequential edges
        3. Create basic blocks
        4. Build function call map
        5. Add dummy nodes (start/exit)
        6. Add control flow edges
        7. Add function call edges
        """

        node_list, self.CFG_node_list, self.records = c_nodes.get_nodes(
            self.root_node,
            node_list={},
            graph_node_list=[],
            index=self.index,
            records=self.records
        )

        self.node_list = node_list

        cfg_excluded_types = [
            "preproc_include", "preproc_def", "preproc_function_def", "preproc_call",
            "preproc_if", "preproc_ifdef", "preproc_elif", "preproc_else",
            "compound_statement"
        ]

        node_list = {key: node for key, node in node_list.items()
                     if node.type not in cfg_excluded_types and not c_nodes.is_function_declaration(node)}

        filtered_cfg_nodes = []
        excluded_indices = set()
        for node_tuple in self.CFG_node_list:
            node_id = node_tuple[0]
            node_found = False
            for key, node in node_list.items():
                if self.get_index(node) == node_id:
                    filtered_cfg_nodes.append(node_tuple)
                    node_found = True
                    break
            if not node_found:
                excluded_indices.add(node_id)

        self.CFG_node_list = filtered_cfg_nodes

        for key, node in node_list.items():
            current_index = self.get_index(node)

            if node.type in self.statement_types["non_control_statement"]:
                if current_index in self.records["switch_child_map"]:
                    continue

                if node.type == "compound_statement" and len(list(node.named_children)) == 0:
                    continue

                if self.is_last_in_control_block(node):
                    continue

                next_index, next_node = self.get_next_index(node, node_list)

                if next_node is not None:
                    self.add_edge(current_index, next_index, "next_line")

        self.get_basic_blocks(self.CFG_node_list, self.CFG_edge_list)

        updated_node_list = []
        for node_tuple in self.CFG_node_list:
            node_id = node_tuple[0]
            block_idx = self.get_key(node_id, self.records["basic_blocks"])
            if block_idx:
                updated_node_list.append(node_tuple + (block_idx,))
            else:
                updated_node_list.append(node_tuple + (0,))
        self.CFG_node_list = updated_node_list

        for key, node in node_list.items():
            if node.type == "function_definition":
                func_name = c_nodes.get_function_name(node)
                if func_name == "main":
                    self.records["main_function"] = self.get_index(node)
                    break

        self.track_function_pointers(self.root_node)

        self.function_list(self.root_node, node_list)

        for key, node in node_list.items():
            if node.type == "return_statement":
                func_node = self.get_containing_function(node)
                if func_node:
                    func_index = self.get_index(func_node)
                    if func_index not in self.records["return_statement_map"]:
                        self.records["return_statement_map"][func_index] = []
                    self.records["return_statement_map"][func_index].append(self.get_index(node))

        for key, node in node_list.items():
            if node.type == "function_definition":
                func_index = self.get_index(node)
                last_line_result = self.get_block_last_line(node, "body")
                if last_line_result:
                    last_node, _ = last_line_result
                    if last_node and (last_node.start_point, last_node.end_point, last_node.type) in node_list:
                        last_index = self.get_index(last_node)
                        if func_index not in self.records["return_statement_map"]:
                            self.records["return_statement_map"][func_index] = []
                        if last_index not in self.records["return_statement_map"][func_index]:
                            self.records["return_statement_map"][func_index].append(last_index)

        self.CFG_node_list.append((1, 0, "start_node", "start"))

        for key, node in node_list.items():
            current_index = self.get_index(node)

            if node.type == "function_definition":
                func_name = c_nodes.get_function_name(node)

                if "main_function" in self.records:
                    if func_name == "main":
                        self.add_edge(1, current_index, "next")
                else:
                    self.add_edge(1, current_index, "next")

                first_line_result = self.edge_first_line(node, node_list)
                if first_line_result:
                    first_index, _ = first_line_result
                    self.add_edge(current_index, first_index, "first_next_line")

            elif node.type == "if_statement":
                consequence = node.child_by_field_name("consequence")
                if consequence:
                    if consequence.type == "compound_statement":
                        children_list = list(consequence.named_children)
                        if children_list:
                            first_stmt = children_list[0]
                            if (first_stmt.start_point, first_stmt.end_point, first_stmt.type) in node_list:
                                self.add_edge(current_index, self.get_index(first_stmt), "pos_next")
                        else:
                            next_index, _ = self.get_next_index(node, node_list)
                            if next_index != 2:
                                self.add_edge(current_index, next_index, "pos_next")
                    else:
                        if (consequence.start_point, consequence.end_point, consequence.type) in node_list:
                            self.add_edge(current_index, self.get_index(consequence), "pos_next")

                    last_node, _ = self.get_block_last_line(node, "consequence")
                    if last_node and (last_node.start_point, last_node.end_point, last_node.type) in node_list:
                        if last_node.type not in ["return_statement", "break_statement", "continue_statement", "goto_statement"]:
                            outermost_if = node
                            parent = node.parent
                            while parent and parent.type == "if_statement":
                                parent_alt = parent.child_by_field_name("alternative")
                                if parent_alt == outermost_if:
                                    outermost_if = parent
                                    parent = parent.parent
                                else:
                                    break

                            next_index, _ = self.get_next_index(outermost_if, node_list)
                            if next_index != 2:
                                self.add_edge(self.get_index(last_node), next_index, "next_line")

                alternative = node.child_by_field_name("alternative")
                if alternative:
                    alt_content = None
                    for child in alternative.named_children:
                        alt_content = child
                        break

                    if alt_content is None:
                        next_index, _ = self.get_next_index(node, node_list)
                        if next_index != 2:
                            self.add_edge(current_index, next_index, "neg_next")
                    elif alt_content.type == "if_statement":
                        self.add_edge(current_index, self.get_index(alt_content), "neg_next")
                    elif alt_content.type == "compound_statement":
                        children_list = list(alt_content.named_children)
                        if children_list:
                            first_stmt = children_list[0]
                            if (first_stmt.start_point, first_stmt.end_point, first_stmt.type) in node_list:
                                self.add_edge(current_index, self.get_index(first_stmt), "neg_next")
                        else:
                            next_index, _ = self.get_next_index(node, node_list)
                            if next_index != 2:
                                self.add_edge(current_index, next_index, "neg_next")

                        last_node = None
                        if children_list:
                            last_stmt = children_list[-1]
                            if (last_stmt.start_point, last_stmt.end_point, last_stmt.type) in node_list:
                                last_node = last_stmt

                        if last_node and (last_node.start_point, last_node.end_point, last_node.type) in node_list:
                            if last_node.type not in ["return_statement", "break_statement", "continue_statement", "goto_statement"]:
                                outermost_if = node
                                parent = node.parent
                                while parent and parent.type == "if_statement":
                                    parent_alt = parent.child_by_field_name("alternative")
                                    if parent_alt:
                                        parent_alt_content = None
                                        for child in parent_alt.named_children:
                                            parent_alt_content = child
                                            break
                                        if parent_alt_content == outermost_if:
                                            outermost_if = parent
                                            parent = parent.parent
                                        else:
                                            break
                                    else:
                                        break

                                next_index, _ = self.get_next_index(outermost_if, node_list)
                                if next_index != 2:
                                    self.add_edge(self.get_index(last_node), next_index, "next_line")
                    else:
                        if (alt_content.start_point, alt_content.end_point, alt_content.type) in node_list:
                            self.add_edge(current_index, self.get_index(alt_content), "neg_next")

                            if alt_content.type not in ["return_statement", "break_statement", "continue_statement", "goto_statement"]:
                                outermost_if = node
                                parent = node.parent
                                while parent and parent.type == "if_statement":
                                    parent_alt = parent.child_by_field_name("alternative")
                                    if parent_alt:
                                        parent_alt_content = None
                                        for child in parent_alt.named_children:
                                            parent_alt_content = child
                                            break
                                        if parent_alt_content == outermost_if:
                                            outermost_if = parent
                                            parent = parent.parent
                                        else:
                                            break
                                    else:
                                        break

                                next_index, _ = self.get_next_index(outermost_if, node_list)
                                if next_index != 2:
                                    self.add_edge(self.get_index(alt_content), next_index, "next_line")
                else:
                    next_index, _ = self.get_next_index(node, node_list)
                    if next_index != 2:
                        self.add_edge(current_index, next_index, "neg_next")

            elif node.type == "while_statement":
                body = node.child_by_field_name("body")
                if body:
                    if body.type == "compound_statement":
                        children_list = list(body.named_children)
                        if children_list:
                            first_stmt = children_list[0]
                            if (first_stmt.start_point, first_stmt.end_point, first_stmt.type) in node_list:
                                self.add_edge(current_index, self.get_index(first_stmt), "pos_next")
                    else:
                        if (body.start_point, body.end_point, body.type) in node_list:
                            self.add_edge(current_index, self.get_index(body), "pos_next")

                    last_node, _ = self.get_block_last_line(node, "body")
                    if last_node and (last_node.start_point, last_node.end_point, last_node.type) in node_list:
                        if last_node.type not in ["break_statement", "return_statement", "goto_statement"]:
                            self.add_edge(self.get_index(last_node), current_index, "loop_control")

                next_index, _ = self.get_next_index(node, node_list)
                if next_index != 2:
                    self.add_edge(current_index, next_index, "neg_next")

                self.add_edge(current_index, current_index, "loop_update")

            elif node.type == "for_statement":
                body = node.child_by_field_name("body")
                if body:
                    if body.type == "compound_statement":
                        children_list = list(body.named_children)
                        if children_list:
                            first_stmt = children_list[0]
                            if (first_stmt.start_point, first_stmt.end_point, first_stmt.type) in node_list:
                                self.add_edge(current_index, self.get_index(first_stmt), "pos_next")
                    else:
                        if (body.start_point, body.end_point, body.type) in node_list:
                            self.add_edge(current_index, self.get_index(body), "pos_next")

                    last_node, _ = self.get_block_last_line(node, "body")
                    if last_node and (last_node.start_point, last_node.end_point, last_node.type) in node_list:
                        if last_node.type not in ["break_statement", "return_statement", "goto_statement"]:
                            self.add_edge(self.get_index(last_node), current_index, "loop_control")

                next_index, _ = self.get_next_index(node, node_list)
                if next_index != 2:
                    self.add_edge(current_index, next_index, "neg_next")

                self.add_edge(current_index, current_index, "loop_update")

            elif node.type == "do_statement":
                body = node.child_by_field_name("body")
                if body:
                    if body.type == "compound_statement":
                        children_list = list(body.named_children)
                        if children_list:
                            first_stmt = children_list[0]
                            if (first_stmt.start_point, first_stmt.end_point, first_stmt.type) in node_list:
                                self.add_edge(current_index, self.get_index(first_stmt), "pos_next")
                    else:
                        if (body.start_point, body.end_point, body.type) in node_list:
                            self.add_edge(current_index, self.get_index(body), "pos_next")

                    last_node, _ = self.get_block_last_line(node, "body")
                    if last_node and (last_node.start_point, last_node.end_point, last_node.type) in node_list:
                        condition = node.child_by_field_name("condition")
                        if condition:
                            cond_key = (condition.start_point, condition.end_point, condition.type)
                            if cond_key in node_list:
                                cond_index = self.get_index(condition)
                                self.add_edge(self.get_index(last_node), cond_index, "next_line")

                condition = node.child_by_field_name("condition")
                if condition:
                    cond_key = (condition.start_point, condition.end_point, condition.type)
                    if cond_key in node_list:
                        cond_index = self.get_index(condition)
                        self.add_edge(cond_index, current_index, "loop_control")
                        next_index, _ = self.get_next_index(node, node_list)
                        if next_index != 2:
                            self.add_edge(cond_index, next_index, "neg_next")

            elif node.type == "switch_statement":
                body = node.child_by_field_name("body")
                if body:
                    case_statements = []
                    default_stmt = None

                    def find_cases(n):
                        if n.type == "case_statement":
                            case_statements.append(n)
                            if n.children and n.children[0].type == "default":
                                nonlocal default_stmt
                                default_stmt = n
                        for child in n.children:
                            find_cases(child)

                    find_cases(body)

                    for case in case_statements:
                        if (case.start_point, case.end_point, case.type) in node_list:
                            self.add_edge(current_index, self.get_index(case), "switch_case")

                    if not default_stmt:
                        next_index, _ = self.get_next_index(node, node_list)
                        if next_index != 2:
                            self.add_edge(current_index, next_index, "switch_exit")

            elif node.type == "case_statement":
                children = list(node.named_children)

                is_default = node.children and node.children[0].type == "default"

                start_index = 0 if is_default else 1

                if len(children) > start_index:
                    for child in children[start_index:]:
                        if (child.start_point, child.end_point, child.type) in node_list:
                            self.add_edge(current_index, self.get_index(child), "case_next")
                            break

            elif node.type == "break_statement":
                parent = node.parent
                while parent:
                    if parent.type in self.statement_types["loop_control_statement"] or parent.type == "switch_statement":
                        next_index, _ = self.get_next_index(parent, node_list)
                        if next_index != 2:
                            self.add_edge(current_index, next_index, "jump_next")
                        break
                    parent = parent.parent

            elif node.type == "continue_statement":
                loop_node = self.find_enclosing_loop(node)
                if loop_node and (loop_node.start_point, loop_node.end_point, loop_node.type) in node_list:
                    self.add_edge(current_index, self.get_index(loop_node), "jump_next")

            elif node.type == "goto_statement":
                label_node = node.child_by_field_name("label")
                if label_node:
                    label_name = label_node.text.decode("UTF-8")
                    if label_name in self.records["label_statement_map"]:
                        target_key = self.records["label_statement_map"][label_name]
                        if target_key in node_list:
                            target_node = node_list[target_key]
                            self.add_edge(current_index, self.get_index(target_node), "jump_next")

            elif node.type == "labeled_statement":
                if len(node.named_children) > 1:
                    stmt = node.named_children[1]
                    if stmt and (stmt.start_point, stmt.end_point, stmt.type) in node_list:
                        self.add_edge(current_index, self.get_index(stmt), "next_line")

        self.add_function_call_edges(node_list)

        return self.CFG_node_list, self.CFG_edge_list
