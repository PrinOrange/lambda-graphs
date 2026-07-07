"""JavaScript Control Flow Graph builder."""

import networkx as nx
from loguru import logger

from .CFG import CFGGraph
from ...utils import js_nodes


class CFGGraph_js(CFGGraph):
    def __init__(self, src_language, src_code, properties, root_node, parser):
        super().__init__(src_language, src_code, properties, root_node, parser)

        self.node_list = None
        self.statement_types = js_nodes.statement_types
        self.CFG_node_list = []
        self.CFG_edge_list = []
        self.records = {
            "basic_blocks": {},
            "function_list": {},
            "function_calls": {},
            "switch_child_map": {},
            "return_statement_map": {},
        }
        self.index_counter = max(self.index.values()) if self.index else 0
        self.CFG_node_indices = []
        self.symbol_table = self.parser.symbol_table
        self.declaration = self.parser.declaration
        self.declaration_map = self.parser.declaration_map
        self.CFG_node_list, self.CFG_edge_list = self._build_cfg()
        self.graph = self.to_networkx(self.CFG_node_list, self.CFG_edge_list)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def get_index(self, node):
        return self.index[(node.start_point, node.end_point, node.type)]

    def _get_new_synthetic_index(self):
        self.index_counter += 1
        return self.index_counter

    def get_key(self, val, dictionary):
        for key, value in dictionary.items():
            if val in value:
                return key
        return None

    def get_basic_blocks(self, CFG_node_list, CFG_edge_list):
        G = self.to_networkx(CFG_node_list, CFG_edge_list)
        components = nx.weakly_connected_components(G)
        block_index = 1
        for block in components:
            block_list = sorted(list(block))
            self.records["basic_blocks"][block_index] = block_list
            block_index += 1

    def add_edge(self, src, dest, edge_type, additional_data=None):
        if src is None or dest is None:
            return
        if "|" in edge_type:
            base_type, _, suffix = edge_type.partition("|")
            if additional_data is None:
                additional_data = {}
            try:
                additional_data["call_id"] = int(suffix)
            except ValueError:
                additional_data["call_id"] = suffix
            edge_type = base_type
        if additional_data:
            t = (src, dest, edge_type, additional_data)
        else:
            t = (src, dest, edge_type)
        if t not in self.CFG_edge_list:
            self.CFG_edge_list.append(t)

    def _get_next_index(self, current_node, node_list):
        """Find the next statement after *current_node* in execution order."""
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
            if parent.type in ("try_statement", "catch_clause", "finally_clause"):
                if parent.type in ("catch_clause", "finally_clause"):
                    try_parent = parent.parent
                    if try_parent and try_parent.type == "try_statement":
                        current_node = try_parent
                        next_node = current_node.next_named_sibling
                        continue
                else:
                    current_node = parent
                    next_node = current_node.next_named_sibling
                    continue
            if parent.type == "arrow_function":
                return (2, parent)
            if parent.type in ("function_declaration", "method_definition"):
                return (2, None)
            if parent.type == "class_declaration":
                return (2, None)
            if parent.type in self.statement_types["statement_holders"]:
                current_node = parent
                next_node = current_node.next_named_sibling
                continue
            current_node = parent
            next_node = current_node.next_named_sibling

        if next_node.type == "statement_block":
            children = list(next_node.named_children)
            if (
                children
                and (children[0].start_point, children[0].end_point, children[0].type)
                in node_list
            ):
                return (self.get_index(children[0]), children[0])

        if (next_node.start_point, next_node.end_point, next_node.type) in node_list:
            return (self.get_index(next_node), next_node)

        return self._get_next_index(next_node, node_list)

    def _get_block_last_line(self, block_node, node_list):
        """Return the last statement inside a block body."""
        named = list(block_node.named_children)
        if not named:
            return (None, None)
        last = named[-1]
        if last.type in self.statement_types["node_list_type"]:
            return (self.get_index(last), last)
        return (self.get_index(last), last)

    def _edge_first_line(self, node, node_list):
        """Return the first statement inside a node."""
        body = node.child_by_field_name("body")
        if body is None:
            for child in node.children:
                if child.type == "statement_block":
                    body = child
                    break
        if body is None:
            return None
        for child in body.named_children:
            if (child.start_point, child.end_point, child.type) in node_list:
                return (self.get_index(child), child)
        return None

    def get_containing_function(self, node):
        while node is not None:
            if node.type in (
                "function_declaration",
                "method_definition",
                "arrow_function",
            ):
                return node
            node = node.parent
        return None

    def get_function_name(self, fn_node):
        """Extract the function name from a function node."""
        if fn_node is None:
            return "<anonymous>"
        name_node = fn_node.child_by_field_name("name")
        if name_node is not None:
            return name_node.text.decode("utf-8")
        # Arrow functions and anonymous functions
        return "<anonymous>"

    # ------------------------------------------------------------------
    # main builder
    # ------------------------------------------------------------------

    def _build_cfg(self):
        """Main CFG construction for JavaScript."""
        node_list = {}
        js_nodes.get_nodes(self.root_node, node_list, self.index)
        self.node_list = node_list

        # Build graph node list from AST statement nodes
        graph_node_list = []
        for key, node in node_list.items():
            idx = self.get_index(node)
            line_num = node.start_point[0]
            label_text = (
                node.text.decode("utf-8")[:80].replace("\n", " ").replace('"', '\\"')
            )
            type_label = node.type
            graph_node_list.append((idx, line_num, label_text, type_label))

        self.CFG_node_list.extend(graph_node_list)

        # ---- sequential flow for non-control statements ----
        for key, node in node_list.items():
            if node.type in self.statement_types["non_control_statement"]:
                idx = self.get_index(node)
                next_idx, _ = self._get_next_index(node, node_list)
                if next_idx and next_idx != 2:
                    self.CFG_edge_list.append((idx, next_idx, "next"))

        # ---- control flow statements ----
        for key, node in node_list.items():
            ntype = node.type
            idx = self.get_index(node)

            if ntype == "if_statement":
                consequence = node.child_by_field_name("consequence")
                alternative = node.child_by_field_name("alternative")

                if consequence is not None:
                    first = self._edge_first_line(node, node_list)
                    if first:
                        self.CFG_edge_list.append((idx, first[0], "pos_next"))

                if alternative is not None:
                    alt_first = self._edge_first_line(alternative, node_list)
                    if alt_first:
                        self.CFG_edge_list.append((idx, alt_first[0], "neg_next"))
                else:
                    next_idx, _ = self._get_next_index(node, node_list)
                    if next_idx and next_idx != 2:
                        self.CFG_edge_list.append((idx, next_idx, "neg_next"))

                last_consequence = None
                if consequence is not None:
                    for c in consequence.named_children:
                        if c.type in self.statement_types["node_list_type"]:
                            last_consequence = c
                if last_consequence is not None:
                    next_idx, _ = self._get_next_index(node, node_list)
                    if next_idx and next_idx != 2:
                        self.CFG_edge_list.append(
                            (self.get_index(last_consequence), next_idx, "else_next")
                        )

            elif ntype in ("while_statement", "do_statement"):
                first = self._edge_first_line(node, node_list)
                if first:
                    self.CFG_edge_list.append((idx, first[0], "loop_next"))
                next_idx, _ = self._get_next_index(node, node_list)
                if next_idx and next_idx != 2:
                    self.CFG_edge_list.append((idx, next_idx, "loop_exit"))

            elif ntype == "for_statement":
                body = node.child_by_field_name("body")
                if body is not None:
                    first = self._edge_first_line(node, node_list)
                    if first:
                        self.CFG_edge_list.append((idx, first[0], "loop_next"))
                next_idx, _ = self._get_next_index(node, node_list)
                if next_idx and next_idx != 2:
                    self.CFG_edge_list.append((idx, next_idx, "loop_exit"))

            elif ntype == "for_in_statement":
                body = node.child_by_field_name("body")
                if body is not None:
                    first = self._edge_first_line(node, node_list)
                    if first:
                        self.CFG_edge_list.append((idx, first[0], "loop_next"))
                next_idx, _ = self._get_next_index(node, node_list)
                if next_idx and next_idx != 2:
                    self.CFG_edge_list.append((idx, next_idx, "loop_exit"))

            elif ntype == "switch_statement":
                switch_body = None
                for c in node.children:
                    if c.type == "switch_body":
                        switch_body = c
                        break
                if switch_body is not None:
                    cases = []
                    for c in switch_body.named_children:
                        if c.type in ("switch_case", "switch_default"):
                            cases.append(c)
                    for ci, case_node in enumerate(cases):
                        first_child = None
                        for c in case_node.named_children:
                            if c.type in self.statement_types["node_list_type"]:
                                first_child = c
                                break
                        if first_child is not None:
                            self.CFG_edge_list.append(
                                (idx, self.get_index(first_child), "case_next")
                            )
                        # break statement connects to next after switch
                    next_idx, _ = self._get_next_index(node, node_list)
                    if next_idx and next_idx != 2:
                        self.CFG_edge_list.append((idx, next_idx, "switch_default"))

            elif ntype == "return_statement":
                fn = self.get_containing_function(node)
                if fn is not None and fn.type != "arrow_function":
                    fn_idx = (
                        self.get_index(fn)
                        if (fn.start_point, fn.end_point, fn.type) in node_list
                        else None
                    )
                    if fn_idx is not None:
                        self.records.setdefault("return_statement_map", {}).setdefault(
                            fn_idx, []
                        ).append(idx)

            elif ntype == "throw_statement":
                pass  # throw transfers control to nearest catch

            elif ntype == "break_statement":
                # Connect to the next statement after the enclosing loop/switch
                parent = node.parent
                while parent is not None:
                    if parent.type in (
                        "while_statement",
                        "for_statement",
                        "for_in_statement",
                        "do_statement",
                        "switch_statement",
                    ):
                        next_idx, _ = self._get_next_index(parent, node_list)
                        if next_idx and next_idx != 2:
                            self.CFG_edge_list.append((idx, next_idx, "break"))
                        break
                    parent = parent.parent

            elif ntype == "continue_statement":
                parent = node.parent
                while parent is not None:
                    if parent.type in (
                        "while_statement",
                        "for_statement",
                        "for_in_statement",
                        "do_statement",
                    ):
                        self.CFG_edge_list.append(
                            (idx, self.get_index(parent), "continue")
                        )
                        break
                    parent = parent.parent

            elif ntype == "try_statement":
                body = node.child_by_field_name("body")
                handler = node.child_by_field_name("handler")
                finalizer = node.child_by_field_name("finalizer")

                if body is not None:
                    first = self._edge_first_line(node, node_list)
                    if first:
                        self.CFG_edge_list.append((idx, first[0], "try_body"))

                if handler is not None:
                    handler_first = self._edge_first_line(handler, node_list)
                    if handler_first:
                        self.CFG_edge_list.append((idx, handler_first[0], "catch_next"))
                else:
                    next_idx, _ = self._get_next_index(node, node_list)
                    if finalizer is not None:
                        fin_first = self._edge_first_line(finalizer, node_list)
                        if fin_first and next_idx and next_idx != 2:
                            self.CFG_edge_list.append(
                                (idx, fin_first[0], "finally_next")
                            )
                    elif next_idx and next_idx != 2:
                        self.CFG_edge_list.append((idx, next_idx, "catch_next"))

                if finalizer is not None:
                    fin_first = self._edge_first_line(finalizer, node_list)
                    if fin_first:
                        # try body exit -> finally
                        pass  # handled via sequential flow

            # function_declaration: add edge to first statement in body
            elif ntype in ("function_declaration", "method_definition"):
                first = self._edge_first_line(node, node_list)
                if first:
                    self.CFG_edge_list.append((idx, first[0], "first_next_line"))

                fn_name = self.get_function_name(node)
                fn_id = idx
                self.records["function_list"][(fn_name, ())] = fn_id

        # ---- add dummy start node ----
        start_idx = 1
        self.CFG_node_list.append((start_idx, 0, "start_node", "start"))

        # Find top-level statements and connect start -> first
        top_level = []
        for key, node in node_list.items():
            if node.parent is not None and node.parent.type == "program":
                top_level.append((key, node))
        top_level.sort(key=lambda x: x[1].start_point)

        if top_level:
            first_tl = self.get_index(top_level[0][1])
            self.CFG_edge_list.append((start_idx, first_tl, "next"))
        else:
            self.CFG_edge_list.append((start_idx, 2, "next"))

        return self.CFG_node_list, self.CFG_edge_list
