"""JavaScript AST node type categorizations for tree-sitter.

The ``statement_types`` dict maps semantic categories to lists of
tree-sitter JavaScript AST node type strings.  These are consumed by
the CFG builder.
"""

statement_types = {
    "node_list_type": [
        "expression_statement",
        "labeled_statement",
        "if_statement",
        "while_statement",
        "for_statement",
        "for_in_statement",
        "for_of_statement",
        "do_statement",
        "break_statement",
        "continue_statement",
        "return_statement",
        "switch_statement",
        "throw_statement",
        "try_statement",
        "catch_clause",
        "finally_clause",
        "function_declaration",
        "function_expression",
        "method_definition",
        "arrow_function",
        "generator_function_declaration",
        "class_declaration",
        "lexical_declaration",
        "variable_declaration",
        "import_statement",
        "export_statement",
        "debugger_statement",
        "empty_statement",
        "with_statement",
    ],
    "non_control_statement": [
        "expression_statement",
        "lexical_declaration",
        "variable_declaration",
        "import_statement",
        "export_statement",
        "debugger_statement",
        "empty_statement",
    ],
    "control_statement": [
        "if_statement",
        "while_statement",
        "for_statement",
        "for_in_statement",
        "for_of_statement",
        "do_statement",
        "break_statement",
        "continue_statement",
        "return_statement",
        "switch_statement",
        "throw_statement",
        "try_statement",
        "catch_clause",
        "finally_clause",
        "labeled_statement",
        "with_statement",
    ],
    "loop_control_statement": [
        "while_statement",
        "for_statement",
        "for_in_statement",
        "for_of_statement",
        "do_statement",
    ],
    "not_implemented": [],
    "inner_node_type": [
        "expression_statement",
        "lexical_declaration",
        "variable_declaration",
    ],
    "outer_node_type": [
        "for_statement",
        "for_in_statement",
        "for_of_statement",
    ],
    "statement_holders": [
        "statement_block",
        "program",
        "switch_body",
        "class_body",
    ],
    "definition_types": [
        "function_declaration",
        "function_expression",
        "method_definition",
        "arrow_function",
        "generator_function_declaration",
        "class_declaration",
    ],
}

method_return_types = [
    "identifier",
    "number",
    "string",
    "true",
    "false",
    "null",
    "undefined",
    "array",
    "object",
]


# ---------------------------------------------------------------------------
# Helper: walk the AST and collect every node that is a "statement"
# ---------------------------------------------------------------------------


def get_nodes(root_node, node_list, index):
    """Populate *node_list* with every named AST node whose type is in
    ``statement_types["node_list_type"]``.

    *node_list* is a dict mapping ``(start_point, end_point, type)`` →
    tree-sitter ``Node`` object.
    """
    if root_node.is_named and root_node.type in statement_types["node_list_type"]:
        node_list[(root_node.start_point, root_node.end_point, root_node.type)] = (
            root_node
        )
    for child in root_node.children:
        get_nodes(child, node_list, index)


def get_child_of_type(node, child_type):
    """Return the first direct named child of *node* whose type matches *child_type*."""
    for child in node.named_children:
        if child.type == child_type:
            return child
    return None


def return_switch_child(node, node_list):
    """If *node* is inside a switch, return the enclosing switch_case / switch_default."""
    parent = node.parent
    while parent is not None:
        if parent.type in ("switch_case", "switch_default"):
            if (parent.start_point, parent.end_point, parent.type) in node_list:
                return parent
        parent = parent.parent
    return None
