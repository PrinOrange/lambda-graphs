"""Tree-sitter language helpers — kept in a leaf module to avoid circular imports."""

from tree_sitter import Language

import tree_sitter_c
import tree_sitter_cpp
import tree_sitter_java
import tree_sitter_javascript

SUPPORTED_LANGUAGES = ("c", "cpp", "java", "javascript")


def get_language_map():
    """Return a mapping from language name to tree-sitter Language object."""
    return {
        "c": Language(tree_sitter_c.language()),
        "cpp": Language(tree_sitter_cpp.language()),
        "java": Language(tree_sitter_java.language()),
        "javascript": Language(tree_sitter_javascript.language()),
    }
