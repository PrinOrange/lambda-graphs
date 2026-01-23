import subprocess

from tree_sitter import Parser

from atlas import get_language_map


def get_commit_hash(directory):
    try:
        result = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=directory, capture_output=True, text=True)
        if result.returncode == 0:
            commit_hash = result.stdout.strip()
            return commit_hash
        return None
    except FileNotFoundError:
        return None


class CustomParser:
    """Custom parser for the src_language"""

    def __init__(self, src_language, src_code):
        """Initialize the parser with the language.
        Language options are: c, cpp"""

        self.src_language = src_language
        self.src_code = src_code
        self.index = {}
        self.language_map = get_language_map()
        self.root_node, self.tree = self.parse()
        self.all_tokens = []
        self.label = {}
        self.method_map = []
        self.method_calls = []
        self.start_line = {}
        self.declaration = {}
        self.declaration_map = {}
        self.symbol_table = {
            "scope_stack": [0],
            "scope_map": {},
            "scope_id": 0,
            "data_type": {},
        }

    def create_AST_id(self, root_node, AST_index, AST_id):
        """Create an id for each node in the AST. This AST id is maintained and used across all code views so that
        it is possible to easily combine graphs"""
        if root_node.is_named:
            current_node_id = AST_id[0]
            AST_id[0] += 1
            AST_index[
                (root_node.start_point, root_node.end_point, root_node.type)
            ] = current_node_id
            for child in root_node.children:
                if child.is_named:
                    self.create_AST_id(child, AST_index, AST_id)
            return

    def parse(self):
        parser = Parser()
        parser.set_language(self.language_map[self.src_language])
        tree = parser.parse(bytes(self.src_code, "utf8"))
        self.root_node = tree.root_node
        self.create_AST_id(self.root_node, self.index, [5])
        return self.root_node, tree
