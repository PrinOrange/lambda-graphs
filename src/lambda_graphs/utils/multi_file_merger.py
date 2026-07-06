"""
Multi-file merger module for combining multiple C/C++ source files into a single file.

This module uses tree-sitter to parse and extract code elements from multiple files,
then combines them in the correct order for graph generation.
"""

import os
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from tree_sitter import Parser
from loguru import logger

from lambda_graphs import get_language_map


class MultiFileMerger:
    """
    Merges multiple C/C++ source files from a folder into a single file.

    The merger extracts and orders code elements properly:
    1. System includes
    2. Macro definitions and preprocessor directives
    3. Type definitions (structs, unions, enums, typedefs)
    4. Global variable declarations
    5. Function declarations (prototypes)
    6. Function definitions
    """

    def __init__(self, folder_path: str, language: str):
        """
        Initialize the multi-file merger.

        Args:
            folder_path: Path to the folder containing source files
            language: Target language ('c' or 'cpp')
        """
        self.folder_path = Path(folder_path)
        self.language = language.lower()

        if self.language not in ["c", "cpp", "java"]:
            raise ValueError(
                f"Unsupported language: {language}. Use 'c', 'cpp', or 'java'."
            )

        if not self.folder_path.exists():
            raise FileNotFoundError(f"Folder not found: {folder_path}")

        if not self.folder_path.is_dir():
            raise ValueError(f"Path is not a directory: {folder_path}")

        self.language_map = get_language_map()
        self.parser = Parser(self.language_map[self.language])

        self.system_includes: List[str] = []
        self.local_includes: List[str] = []
        self.macro_definitions: List[str] = []
        self.type_definitions: List[str] = []
        self.global_declarations: List[str] = []
        self.function_declarations: List[str] = []
        self.function_definitions: List[Tuple[str, str]] = []

        self.seen_includes: set = set()
        self.seen_macros: set = set()
        self.seen_types: set = set()
        self.seen_function_decls: set = set()
        self.seen_function_defs: set = set()
        self.seen_globals: set = set()

    def _get_source_files(self) -> Tuple[List[Path], List[Path]]:
        """
        Get all source files from the folder.

        Returns:
            Tuple of (header_files, source_files)
        """
        header_files = []
        source_files = []

        if self.language == "c":
            source_extensions = [".c"]
            header_extensions = [".h"]
        elif self.language == "java":
            source_extensions = [".java"]
            header_extensions = []
        else:
            source_extensions = [".cpp", ".cc", ".cxx", ".c++"]
            header_extensions = [".h", ".hpp", ".hh", ".hxx", ".h++"]

        for root, _, files in os.walk(self.folder_path):
            for file in sorted(files):
                file_path = Path(root) / file
                ext = file_path.suffix.lower()

                if ext in header_extensions:
                    header_files.append(file_path)
                elif ext in source_extensions:
                    source_files.append(file_path)

        header_files.sort()
        source_files.sort()

        logger.debug(
            f"Found {len(header_files)} header files and {len(source_files)} source files"
        )

        return header_files, source_files

    def _parse_file(self, file_path: Path) -> None:
        """
        Parse a single file and extract its elements.

        Args:
            file_path: Path to the source file
        """
        logger.debug(f"Parsing file: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception as e:
            logger.warning(f"Failed to read file {file_path}: {e}")
            return

        tree = self.parser.parse(bytes(content, "utf-8"))
        root_node = tree.root_node

        for child in root_node.children:
            self._process_node(child, content)

    def _process_node(self, node, content: str) -> None:
        """
        Process a top-level AST node and categorize it.

        Args:
            node: Tree-sitter node
            content: Original source code
        """
        node_text = content[node.start_byte : node.end_byte]

        if node.type == "comment":
            return

        if node.type == "preproc_include":
            self._handle_include(node_text)
        elif node.type == "preproc_def":
            self._handle_macro(node_text)
        elif node.type == "preproc_function_def":
            self._handle_macro(node_text)
        elif node.type == "preproc_ifdef":
            self._handle_preprocessor_conditional(node, content)
        elif node.type == "preproc_ifndef":
            self._handle_preprocessor_conditional(node, content)
        elif node.type == "preproc_if":
            self._handle_preprocessor_conditional(node, content)

        elif node.type == "struct_specifier":
            self._handle_type_definition(node_text)
        elif node.type == "union_specifier":
            self._handle_type_definition(node_text)
        elif node.type == "enum_specifier":
            self._handle_type_definition(node_text)
        elif node.type == "type_definition":
            self._handle_type_definition(node_text)

        elif node.type == "declaration":
            self._handle_declaration(node, node_text)

        elif node.type == "function_definition":
            self._handle_function_definition(node, node_text)

        elif node.type == "class_specifier":
            self._handle_type_definition(node_text)
        elif node.type == "namespace_definition":
            self._handle_type_definition(node_text)
        elif node.type == "template_declaration":
            self._handle_template(node, content, node_text)
        elif node.type == "using_declaration":
            self._handle_type_definition(node_text)
        elif node.type == "alias_declaration":
            self._handle_type_definition(node_text)

        elif node.type == "linkage_specification":
            self._handle_linkage_spec(node, content)

        elif node.type == "declaration_list":
            for child in node.children:
                self._process_node(child, content)

    def _handle_include(self, text: str) -> None:
        """Handle include directives."""
        text = text.strip()
        if text in self.seen_includes:
            return
        self.seen_includes.add(text)

        if "<" in text:
            self.system_includes.append(text)
        else:
            self.local_includes.append(text)

    def _handle_macro(self, text: str) -> None:
        """Handle macro definitions."""
        text = text.strip()
        lines = text.split("\n")
        first_line = lines[0]
        parts = first_line.split()
        if len(parts) >= 2:
            macro_name = parts[1].split("(")[0]
            if macro_name in self.seen_macros:
                return
            self.seen_macros.add(macro_name)

        self.macro_definitions.append(text)

    def _handle_preprocessor_conditional(self, node, content: str) -> None:
        """Handle preprocessor conditionals (ifdef, ifndef, if) by processing their children."""
        for child in node.children:
            if child.type not in [
                "#ifndef",
                "#ifdef",
                "#if",
                "#endif",
                "#else",
                "identifier",
            ]:
                self._process_node(child, content)

    def _handle_linkage_spec(self, node, content: str) -> None:
        """Handle linkage specification (extern "C" { ... })."""
        for child in node.children:
            if child.type == "declaration_list":
                for subchild in child.children:
                    self._process_node(subchild, content)

    def _handle_type_definition(self, text: str) -> None:
        """Handle struct, union, enum, typedef, class definitions."""
        text = text.strip()
        if text in self.seen_types:
            return
        self.seen_types.add(text)
        self.type_definitions.append(text)

    def _handle_declaration(self, node, text: str) -> None:
        """Handle variable and function declarations."""
        text = text.strip()

        is_function_decl = False
        for child in node.children:
            if child.type == "function_declarator":
                is_function_decl = True
                break
            if child.type == "pointer_declarator":
                for subchild in child.children:
                    if subchild.type == "function_declarator":
                        is_function_decl = True
                        break

        if is_function_decl:
            if text not in self.seen_function_decls:
                self.seen_function_decls.add(text)
                self.function_declarations.append(text)
        else:
            if text not in self.seen_globals:
                self.seen_globals.add(text)
                self.global_declarations.append(text)

    def _handle_function_definition(self, node, text: str) -> None:
        """Handle function definitions."""
        text = text.strip()

        func_name = self._extract_function_name(node)

        if func_name in self.seen_function_defs:
            logger.warning(f"Duplicate function definition: {func_name}")
            return

        self.seen_function_defs.add(func_name)
        self.function_definitions.append((func_name, text))

    def _handle_template(self, node, content: str, text: str) -> None:
        """Handle C++ template declarations."""
        text = text.strip()

        has_function_def = False
        for child in node.children:
            if child.type == "function_definition":
                has_function_def = True
                break

        if has_function_def:
            func_name = f"template_{len(self.function_definitions)}"
            if text not in self.seen_function_defs:
                self.seen_function_defs.add(text)
                self.function_definitions.append((func_name, text))
        else:
            if text not in self.seen_types:
                self.seen_types.add(text)
                self.type_definitions.append(text)

    def _extract_function_name(self, node) -> str:
        """Extract function name from a function definition node."""
        for child in node.children:
            if child.type == "function_declarator":
                for subchild in child.children:
                    if subchild.type == "identifier":
                        return subchild.text.decode("utf-8")
                    elif subchild.type == "field_identifier":
                        return subchild.text.decode("utf-8")
                    elif subchild.type == "destructor_name":
                        return subchild.text.decode("utf-8")
                    elif subchild.type == "qualified_identifier":
                        return subchild.text.decode("utf-8")
            elif child.type == "pointer_declarator":
                return self._extract_function_name_from_declarator(child)

        return f"unknown_func_{len(self.function_definitions)}"

    def _extract_function_name_from_declarator(self, node) -> str:
        """Recursively extract function name from declarator."""
        for child in node.children:
            if child.type == "function_declarator":
                for subchild in child.children:
                    if subchild.type == "identifier":
                        return subchild.text.decode("utf-8")
            elif child.type == "pointer_declarator":
                return self._extract_function_name_from_declarator(child)
        return "unknown_func"

    def merge(self) -> str:
        """
        Merge all source files into a single string.

        Returns:
            Merged source code
        """
        header_files, source_files = self._get_source_files()

        if not header_files and not source_files:
            raise ValueError(f"No source files found in {self.folder_path}")

        for header_file in header_files:
            self._parse_file(header_file)

        for source_file in source_files:
            self._parse_file(source_file)

        output_parts = []

        output_parts.append(f"/* Merged source from {self.folder_path} */")
        output_parts.append(f"/* Generated by lambda-graphs Multi-File Merger */")
        output_parts.append("")

        if self.system_includes:
            output_parts.append("/* System Includes */")
            for inc in self.system_includes:
                output_parts.append(inc)
            output_parts.append("")

        if self.macro_definitions:
            output_parts.append("/* Macro Definitions */")
            for macro in self.macro_definitions:
                output_parts.append(macro)
            output_parts.append("")

        if self.type_definitions:
            output_parts.append("/* Type Definitions */")
            for typedef in self.type_definitions:
                output_parts.append(typedef)
                output_parts.append("")

        if self.global_declarations:
            output_parts.append("/* Global Declarations */")
            for decl in self.global_declarations:
                output_parts.append(decl)
            output_parts.append("")

        if self.function_declarations:
            output_parts.append("/* Function Declarations */")
            for decl in self.function_declarations:
                output_parts.append(decl)
            output_parts.append("")

        if self.function_definitions:
            output_parts.append("/* Function Definitions */")
            for func_name, func_code in self.function_definitions:
                output_parts.append(f"/* Function: {func_name} */")
                output_parts.append(func_code)
                output_parts.append("")

        return "\n".join(output_parts)

    def merge_to_file(self, output_path: Optional[str] = None) -> str:
        """
        Merge all source files and write to a file.

        Args:
            output_path: Optional path for the output file. If not provided,
                        a temporary file will be created.

        Returns:
            Path to the merged file
        """
        merged_code = self.merge()

        if output_path is None:
            if self.language == "c":
                suffix = ".c"
            else:
                suffix = ".cpp"

            temp_dir = tempfile.mkdtemp(prefix="lambda_graphs_merged_")
            output_path = os.path.join(temp_dir, f"project{suffix}")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(merged_code)

        logger.info(f"Merged source written to: {output_path}")

        return output_path


def merge_files(
    folder_path: str, language: str, output_path: Optional[str] = None
) -> str:
    """
    Convenience function to merge a folder of source files.

    Args:
        folder_path: Path to the folder containing source files
        language: Target language ('c' or 'cpp')
        output_path: Optional path for the output file

    Returns:
        Path to the merged file
    """
    merger = MultiFileMerger(folder_path, language)
    return merger.merge_to_file(output_path)


FolderCombiner = MultiFileMerger
combine_folder = merge_files
