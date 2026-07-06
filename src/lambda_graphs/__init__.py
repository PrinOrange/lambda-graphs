from tree_sitter import Language

import tree_sitter_c
import tree_sitter_cpp
import tree_sitter_java


def get_language_map():
    """Return a mapping from language name to tree-sitter Language object.

    Uses pre-compiled grammar libraries from pip packages instead of
    cloning and building grammars at runtime.
    """
    return {
        "c": Language(tree_sitter_c.language()),
        "cpp": Language(tree_sitter_cpp.language()),
        "java": Language(tree_sitter_java.language()),
    }
