import traceback

import networkx as nx
from loguru import logger

from ...utils import cpp_nodes
from .CFG import CFGGraph


class CFGGraph_cpp(CFGGraph):
    def __init__(self, src_language, src_code, properties, root_node, parser):
        super().__init__(src_language, src_code, properties, root_node, parser)

        self.node_list = None
        self.statement_types = cpp_nodes.statement_types
        self.CFG_node_list = []
        self.CFG_edge_list = []
        self.records = {
            "basic_blocks": {},
            "function_list": {},
            "return_type": {},
            "class_list": {},
            "struct_list": {},
            "enum_list": {},
            "union_list": {},
            "typedef_list": {},
            "namespace_list": {},
            "namespace_aliases": {},
            "template_list": {},
            "extends": {},
            "function_calls": {},
            "method_calls": {},
            "static_method_calls": {},
            "operator_calls": {},
            "constructor_calls": {},
            "destructor_calls": {},
            "virtual_functions": {},
            "operator_overloads": {},
            "special_functions": {},
            "functions_with_initializers": {},
            "lambda_map": {},
            "switch_child_map": {},
            "label_statement_map": {},
            "return_statement_map": {},
            "implicit_return_map": {},
            "constexpr_functions": {},
            "inline_functions": {},
            "noexcept_functions": {},
            "attributed_functions": {},
            "function_pointer_assignments": {},
            "indirect_calls": {},
            "lambda_variables": {},
            "lambda_arguments": {},
            "function_parameter_to_lambda": {},
            "variadic_functions": {},
        }
        self.index_counter = max(self.index.values())
        self.CFG_node_indices = []

        self.runtime_types = {}
        self.template_instantiations = {}
        self.scope_objects = {}
        self.object_scope_map = {}
        self.scope_nodes = {}
        self.pointer_targets = {}

        self.symbol_table = self.parser.symbol_table
        self.declaration = self.parser.declaration
        self.declaration_map = self.parser.declaration_map

        self.CFG_node_list, self.CFG_edge_list = self.CFG_cpp()
        self.graph = self.to_networkx(self.CFG_node_list, self.CFG_edge_list)

    def get_index(self, node):
        """Get the unique index for a given AST node"""
        return self.index[(node.start_point, node.end_point, node.type)]

    def get_new_synthetic_index(self):
        """Generate a new unique index for synthetic nodes (implicit returns, etc.)"""
        self.index_counter += 1
        return self.index_counter

    def get_basic_blocks(self, CFG_node_list, CFG_edge_list):
        """Partition CFG into basic blocks using weakly connected components"""
        G = self.to_networkx(CFG_node_list, CFG_edge_list)
        components = nx.weakly_connected_components(G)
        block_index = 1
        for block in components:
            block_list = sorted(list(block))
            self.records["basic_blocks"][block_index] = block_list
            block_index += 1

    def append_block_index(self, CFG_node_list, records):
        """Append block index to each node in CFG_node_list"""
        updated_node_list = []
        for node_tuple in CFG_node_list:
            node_id = node_tuple[0]
            block_idx = self.get_key(node_id, records["basic_blocks"])
            if block_idx is not None:
                updated_node_list.append(node_tuple + (block_idx,))
            else:
                updated_node_list.append(node_tuple + (0,))
        return updated_node_list

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

    def get_containing_class(self, node):
        """Find the enclosing class or struct definition for a given node"""
        while node is not None:
            if node.type in ["class_specifier", "struct_specifier"]:
                return node
            node = node.parent
        return None

    def get_containing_namespace(self, node):
        """Find the enclosing namespace for a given node"""
        while node is not None:
            if node.type == "namespace_definition":
                return node
            node = node.parent
        return None

    def resolve_template_specialization(
        self, base_class_name, template_args, method_name
    ):
        """
        Resolve which template specialization matches the given template arguments.
        Returns the function_id of the matching specialization's method, or None if not found.

        Template specialization resolution follows C++ rules:
        1. Exact match (full specialization) takes highest priority
        2. Partial specialization takes next priority (most specific match)
        3. Primary template is the fallback

        Args:
            base_class_name: The base template class name (e.g., "Container")
            template_args: Tuple of template argument strings (e.g., ("int", "std::string"))
            method_name: The method being called (e.g., "display")

        Returns:
            function_id of the matching method, or None if no match found
        """
        if not template_args:
            return None

        candidates = []

        for ((class_name, fn_name), fn_sig), fn_id in self.records[
            "function_list"
        ].items():
            if fn_name != method_name:
                continue

            fn_key = None
            for key, fid in self.index.items():
                if fid == fn_id:
                    fn_key = key
                    break

            if not fn_key:
                continue

            fn_node = self.node_list.get(fn_key)
            if not fn_node:
                continue

            class_node = self.get_containing_class(fn_node)
            if not class_node:
                continue

            parent = class_node.parent
            if not parent or parent.type != "template_declaration":
                continue

            template_params = []
            template_specs = []

            for child in parent.children:
                if child.type == "template_parameter_list":
                    for param in child.named_children:
                        if param.type in [
                            "type_parameter_declaration",
                            "parameter_declaration",
                        ]:
                            template_params.append(param)

            is_full_specialization = len(template_params) == 0
            is_primary_template = False
            specificity = 0

            for child in class_node.children:
                if child.type == "template_argument_list":
                    template_specs = []
                    for arg in child.named_children:
                        template_specs.append(arg.text.decode("utf-8"))
                    break

            if not template_specs:
                is_primary_template = True
                specificity = 0
            elif is_full_specialization:
                if len(template_specs) == len(template_args):
                    specs_normalized = [s.replace(" ", "") for s in template_specs]
                    args_normalized = [a.replace(" ", "") for a in template_args]

                    if specs_normalized == args_normalized:
                        specificity = 100
                    else:
                        continue
                else:
                    continue
            else:
                if len(template_specs) == len(template_args):
                    match = self._match_template_pattern(template_specs, template_args)
                    if match:
                        specificity = 50
                    else:
                        continue
                else:
                    continue

            candidates.append((specificity, fn_id, class_name))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    def _match_template_pattern(self, pattern, args):
        """
        Check if template arguments match a partial specialization pattern.

        Args:
            pattern: List of pattern strings from partial specialization (e.g., ["T", "T"])
            args: List of actual template arguments (e.g., ["int", "int"])

        Returns:
            True if args match the pattern, False otherwise
        """
        if len(pattern) != len(args):
            return False

        param_map = {}

        for p, a in zip(pattern, args):
            p_norm = p.replace(" ", "")
            a_norm = a.replace(" ", "")

            if p_norm.endswith("*"):
                base_p = p_norm[:-1]
                if not a_norm.endswith("*"):
                    return False
                base_a = a_norm[:-1]

                if base_p in param_map:
                    if param_map[base_p] != base_a:
                        return False
                else:
                    param_map[base_p] = base_a
            else:
                if p_norm in param_map:
                    if param_map[p_norm] != a_norm:
                        return False
                else:
                    if len(p_norm) == 1 and p_norm.isupper():
                        param_map[p_norm] = a_norm
                    elif p_norm == a_norm:
                        continue
                    else:
                        return False

        return True

    def register_template_specializations(self, node_list):
        """
        Scan the AST for template class specializations and register their methods.
        This fixes the issue where partial specializations are recorded as "anonymous_class"
        and not properly added to the function_list.
        """
        for key, node in node_list.items():
            if node.type == "function_definition":
                class_node = self.get_containing_class(node)
                if not class_node or not class_node.parent:
                    continue

                parent = class_node.parent
                if parent.type != "template_declaration":
                    continue

                class_name = "Container"
                template_args = []

                for child in class_node.children:
                    if child.type == "type_identifier":
                        class_name = child.text.decode("utf-8")
                    elif child.type == "template_argument_list":
                        for arg in child.named_children:
                            template_args.append(arg.text.decode("utf-8"))

                fn_name = None
                fn_sig = []

                declarator = None
                for child in node.children:
                    if child.type in [
                        "function_declarator",
                        "pointer_declarator",
                        "reference_declarator",
                    ]:
                        declarator = child
                        break

                if declarator:
                    is_variadic = False

                    def extract_from_declarator(decl_node):
                        nonlocal fn_name, fn_sig, is_variadic
                        for gc in decl_node.children:
                            if gc.type in ["identifier", "field_identifier"]:
                                fn_name = gc.text.decode("utf-8")
                            elif gc.type == "parameter_list":
                                for param in gc.children:
                                    if param.type == "parameter_declaration":
                                        param_type = self.extract_parameter_type(param)
                                        if param_type:
                                            fn_sig.append(param_type)
                                    elif param.type == "...":
                                        is_variadic = True
                                        fn_sig.append("...")
                            elif gc.type in [
                                "function_declarator",
                                "pointer_declarator",
                                "reference_declarator",
                            ]:
                                extract_from_declarator(gc)

                    extract_from_declarator(declarator)

                if not fn_name:
                    continue

                fn_id = self.get_index(node)
                key = ((class_name, fn_name), tuple(fn_sig))

                if key not in self.records["function_list"]:
                    self.records["function_list"][key] = fn_id

                    if is_variadic:
                        self.records["variadic_functions"][key] = True

    def extract_parameter_type(self, param_node):
        """
        Extract the full parameter type from a parameter_declaration node,
        including reference qualifiers (&, &&) and pointer qualifiers (*).

        For example:
        - int x → "int"
        - int& x → "int&"
        - int&& x → "int&&"
        - const int& x → "const int&"
        - int* x → "int*"
        """
        if param_node is None or param_node.type != "parameter_declaration":
            return None

        param_type_node = param_node.child_by_field_name("type")
        if not param_type_node:
            return None

        base_type = param_type_node.text.decode("utf-8")

        param_declarator = param_node.child_by_field_name("declarator")
        if param_declarator:
            if param_declarator.type == "reference_declarator":
                declarator_text = param_declarator.text.decode("utf-8")
                if declarator_text.startswith("&&"):
                    return base_type + "&&"
                else:
                    return base_type + "&"
            elif param_declarator.type == "pointer_declarator":
                return base_type + "*"
            else:
                return base_type

        return base_type

    def get_base_classes(self, class_node):
        """
        Extract base class names from a class_specifier node.
        Returns a set of base class names.
        Example: class Circle : public Shape { } -> {'Shape'}
        Example: class PaintedCircle : public Circle, public Paintable { } -> {'Circle', 'Paintable'}
        """
        base_classes = set()
        if class_node is None:
            return base_classes

        for child in class_node.children:
            if child.type == "base_class_clause":
                for subchild in child.children:
                    if subchild.type == "type_identifier":
                        base_class_name = subchild.text.decode("utf-8")
                        base_classes.add(base_class_name)
                break

        return base_classes

    def get_all_derived_classes(self, base_class_name):
        """
        Find all classes that derive (directly or indirectly) from the given base class.
        Uses the inheritance information stored in self.records["extends"].

        Args:
            base_class_name: The name of the base class to find derived classes for

        Returns:
            A set of class names that derive from base_class_name
        """
        derived_classes = set()

        reverse_inheritance = {}
        for derived, bases in self.records.get("extends", {}).items():
            if not isinstance(bases, list):
                bases = [bases]
            for base in bases:
                if base not in reverse_inheritance:
                    reverse_inheritance[base] = []
                reverse_inheritance[base].append(derived)

        to_process = [base_class_name]
        while to_process:
            current_base = to_process.pop(0)
            for derived in reverse_inheritance.get(current_base, []):
                if derived not in derived_classes:
                    derived_classes.add(derived)
                    to_process.append(derived)

        return derived_classes

    def get_class_namespaces(self, class_name):
        """
        Find all namespaces that contain a class with the given name.
        This is needed because function_list uses (namespace, fn_name) as keys
        for namespaced classes, not (class_name, fn_name).

        Args:
            class_name: The class name to find namespaces for

        Returns:
            A set of namespace names (or None for non-namespaced classes)
        """
        namespaces = set()

        for ((ns_or_class, fn_name), _), _ in self.records.get(
            "function_list", {}
        ).items():
            if fn_name == class_name:
                if ns_or_class == class_name:
                    namespaces.add(None)
                else:
                    namespaces.add(ns_or_class)

        return namespaces

    def get_explicit_base_constructors_in_initializer_list(
        self, constructor_node, base_class_names
    ):
        """
        Check which base class constructors are explicitly called in the constructor's
        field_initializer_list.

        Args:
            constructor_node: The constructor function_definition node
            base_class_names: Set of base class names for this class

        Returns:
            Set of base class names that have explicit constructor calls in the initializer list
        """
        explicit_base_calls = set()

        if constructor_node is None:
            return explicit_base_calls

        field_init_list = None
        for child in constructor_node.children:
            if child.type == "field_initializer_list":
                field_init_list = child
                break

        if not field_init_list:
            return explicit_base_calls

        for child in field_init_list.children:
            if child.type == "field_initializer":
                for subchild in child.children:
                    if subchild.type == "field_identifier":
                        field_name = subchild.text.decode("utf-8")
                        if field_name in base_class_names:
                            explicit_base_calls.add(field_name)
                        break
                    elif subchild.type == "qualified_identifier":
                        field_name = subchild.text.decode("utf-8")
                        if field_name in base_class_names:
                            explicit_base_calls.add(field_name)
                        simple_name = field_name.split("::")[-1]
                        if simple_name in base_class_names:
                            explicit_base_calls.add(simple_name)
                        break

        return explicit_base_calls

    def is_jump_statement(self, node):
        """
        Check if a node is a jump statement that transfers control elsewhere.
        Jump statements should NOT have fall-through edges to the next statement.
        """
        if node is None:
            return False

        jump_types = [
            "break_statement",
            "continue_statement",
            "return_statement",
            "goto_statement",
            "throw_statement",
        ]

        return node.type in jump_types

    def statement_invokes_lambda(self, node):
        """
        Check if a statement invokes a lambda (either stored or immediately invoked).
        Returns True if the statement has a lambda invocation, False otherwise.

        This is used to determine if we should skip creating implicit_return edges
        from this statement, since the lambda's return edges will handle the flow.
        """
        if node is None:
            return False

        def contains_immediate_lambda_call(n):
            if n.type == "call_expression":
                func = n.child_by_field_name("function")
                if func and func.type == "lambda_expression":
                    return True
            for child in n.named_children:
                if contains_immediate_lambda_call(child):
                    return True
            return False

        if contains_immediate_lambda_call(node):
            return True

        def contains_lambda_var_call(n):
            if n.type == "call_expression":
                func = n.child_by_field_name("function")
                if func and func.type == "identifier":
                    var_name = func.text.decode("utf-8")
                    if var_name in self.records.get("lambda_variables", {}):
                        return True
                    containing_func = self.get_containing_function(node)
                    if containing_func:
                        declarator = containing_func.child_by_field_name("declarator")
                        if declarator:
                            parameters = declarator.child_by_field_name("parameters")
                            if parameters:
                                for param in parameters.named_children:
                                    if param.type == "parameter_declaration":
                                        param_decl = param.child_by_field_name(
                                            "declarator"
                                        )
                                        if param_decl:
                                            param_name = None
                                            if param_decl.type == "identifier":
                                                param_name = param_decl.text.decode(
                                                    "utf-8"
                                                )
                                            elif (
                                                param_decl.type
                                                == "reference_declarator"
                                            ):
                                                for child in param_decl.named_children:
                                                    if child.type == "identifier":
                                                        param_name = child.text.decode(
                                                            "utf-8"
                                                        )
                                                        break
                                            if param_name == var_name:
                                                return True
            for child in n.named_children:
                if contains_lambda_var_call(child):
                    return True
            return False

        return contains_lambda_var_call(node)

    def extract_thrown_type(self, throw_node):
        """
        Extract the type of the expression being thrown.
        Returns a tuple: (type_category, type_string)

        type_category: 'int', 'float', 'string', 'class', 'catch_all'
        type_string: detailed type information
        """
        if throw_node.type != "throw_statement":
            return ("unknown", None)

        thrown_expr = None
        for child in throw_node.children:
            if child.type not in ["throw", ";"]:
                thrown_expr = child
                break

        if thrown_expr is None:
            return ("rethrow", None)

        if thrown_expr.type == "number_literal":
            literal_text = thrown_expr.text.decode("utf-8")
            if "f" in literal_text.lower() or "." in literal_text:
                return ("float", "float")
            else:
                return ("int", "int")

        elif thrown_expr.type == "string_literal":
            return ("string", "const char*")

        elif thrown_expr.type == "call_expression":
            func_node = thrown_expr.child_by_field_name("function")
            if func_node:
                func_text = func_node.text.decode("utf-8")
                return ("class", func_text)

        elif thrown_expr.type == "identifier":
            return ("variable", thrown_expr.text.decode("utf-8"))

        return ("unknown", thrown_expr.text.decode("utf-8") if thrown_expr else None)

    def extract_catch_parameter_type(self, catch_node):
        """
        Extract the parameter type from a catch clause.
        Returns a tuple: (type_category, type_string)

        type_category: 'int', 'float', 'string', 'class', 'catch_all'
        type_string: detailed type information
        """
        if catch_node.type != "catch_clause":
            return ("unknown", None)

        param_list = None
        for child in catch_node.children:
            if child.type == "parameter_list":
                param_list = child
                break

        if param_list is None:
            return ("catch_all", "...")

        param_text = param_list.text.decode("utf-8")
        if param_text.startswith("(") and param_text.endswith(")"):
            param_text = param_text[1:-1].strip()

        if param_text == "...":
            return ("catch_all", "...")

        parts = param_text.split()
        if not parts:
            return ("catch_all", "...")

        if "int" in param_text and "point" not in param_text.lower():
            return ("int", "int")
        elif "float" in param_text or "double" in param_text:
            return ("float", "float")
        elif "char*" in param_text or "char *" in param_text:
            return ("string", "const char*")
        elif "exception" in param_text.lower() or "::" in param_text:
            type_part = param_text
            type_part = type_part.replace("const", "").replace("&", "").strip()
            words = type_part.split()
            if len(words) > 1:
                class_name = " ".join(words[:-1])
            else:
                class_name = words[0]
            return ("class", class_name.strip())

        return ("class", param_text)

    def exception_type_matches(self, thrown_type, catch_type):
        """
        Check if a thrown exception type matches a catch parameter type.

        Returns True if the exception can be caught by the catch block.
        Implements C++ exception matching rules:
        1. Exact type match
        2. Derived class to base class (polymorphism)
        3. Catch-all (...) catches everything

        Args:
            thrown_type: tuple (type_category, type_string) from extract_thrown_type
            catch_type: tuple (type_category, type_string) from extract_catch_parameter_type
        """
        thrown_cat, thrown_str = thrown_type
        catch_cat, catch_str = catch_type

        if catch_cat == "catch_all":
            return True

        if thrown_cat == "rethrow":
            return False

        if thrown_cat == catch_cat:
            if thrown_cat in ["int", "float", "string"]:
                return True

            if thrown_cat == "class":
                thrown_normalized = thrown_str.replace(" ", "") if thrown_str else ""
                catch_normalized = catch_str.replace(" ", "") if catch_str else ""

                if thrown_normalized == catch_normalized:
                    return True

                if catch_normalized in ["std::exception", "exception"]:
                    if thrown_normalized.startswith("std::"):
                        if (
                            "error" in thrown_normalized.lower()
                            or "exception" in thrown_normalized.lower()
                        ):
                            return True

        return False

    def get_next_index(self, current_node, node_list):
        """
        Find the next executable statement after current_node.
        Handles:
        - Sequential statements (next_named_sibling)
        - End of blocks (traverse up to parent)
        - Loop back edges
        - Function boundaries
        - Class boundaries
        - Namespace boundaries
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

            if parent.type in ["try_statement", "catch_clause"]:
                if parent.type == "catch_clause":
                    try_parent = parent.parent
                    if try_parent and try_parent.type == "try_statement":
                        current_node = try_parent
                        next_node = current_node.next_named_sibling
                        continue
                else:
                    current_node = parent
                    next_node = current_node.next_named_sibling
                    continue

            if parent.type == "lambda_expression":
                return (2, parent)

            if parent.type == "function_definition":
                if (parent.start_point, parent.end_point, parent.type) in node_list:
                    fn_index = self.get_index(parent)
                    if (
                        self.records.get("implicit_return_map")
                        and fn_index in self.records["implicit_return_map"]
                    ):
                        implicit_return_id = self.records["implicit_return_map"][
                            fn_index
                        ]
                        return (implicit_return_id, None)
                return (2, None)

            if parent.type in ["class_specifier", "struct_specifier"]:
                return (2, None)

            if parent.type == "namespace_definition":
                current_node = parent
                next_node = current_node.next_named_sibling
                continue

            if parent.type in self.statement_types["statement_holders"]:
                current_node = parent
                next_node = current_node.next_named_sibling
                continue

            current_node = parent
            next_node = current_node.next_named_sibling

        if (
            next_node.type == "compound_statement"
            and len(list(next_node.named_children)) == 0
        ):
            current_node = next_node
            return self.get_next_index(current_node, node_list)

        if next_node.type == "compound_statement":
            children_list = list(next_node.named_children)
            if children_list:
                first_child = children_list[0]
                if (
                    first_child.start_point,
                    first_child.end_point,
                    first_child.type,
                ) in node_list:
                    return (self.get_index(first_child), first_child)

        if next_node.type == "field_declaration":

            def find_first_in_wrapper(wrapper_node):
                for child in wrapper_node.named_children:
                    if (child.start_point, child.end_point, child.type) in node_list:
                        return (self.get_index(child), child)
                    result = find_first_in_wrapper(child)
                    if result:
                        return result
                return None

            result = find_first_in_wrapper(next_node)
            if result:
                return result

        if next_node.type in [
            "preproc_include",
            "preproc_def",
            "preproc_function_def",
            "preproc_call",
            "preproc_if",
            "preproc_ifdef",
            "preproc_elif",
            "preproc_else",
        ]:
            return self.get_next_index(next_node, node_list)

        if (next_node.start_point, next_node.end_point, next_node.type) in node_list:
            return (self.get_index(next_node), next_node)

        return self.get_next_index(next_node, node_list)

    def is_last_in_control_block(self, node):
        """
        Check if a node is the last statement in a control flow block (if/else/loop/try/catch).
        These nodes should NOT have edges added in the sequential flow step,
        as they will be handled by the control flow step.
        """
        if node.parent is None:
            return False

        parent = node.parent

        if parent.type == "compound_statement":
            children = list(parent.named_children)
            if children and children[-1] == node:
                grandparent = parent.parent
                if grandparent and grandparent.type in [
                    "if_statement",
                    "while_statement",
                    "for_statement",
                    "for_range_loop",
                    "do_statement",
                    "else_clause",
                    "catch_clause",
                    "try_statement",
                ]:
                    return True

        if parent.type in [
            "if_statement",
            "while_statement",
            "for_statement",
            "for_range_loop",
            "do_statement",
        ]:
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

        if parent.type in ["catch_clause", "try_statement"]:
            body = parent.child_by_field_name("body")
            if body and body == node:
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

        if node.type in ["class_specifier", "struct_specifier"]:
            for child in node.children:
                if child.type == "field_declaration_list":
                    body_node = child
                    break

        if node.type == "namespace_definition":
            for child in node.children:
                if child.type == "declaration_list":
                    body_node = child
                    break

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

    def extract_attributes_from_node(self, node):
        """
        Extract C++ attributes from a node (e.g., [[noreturn]], [[fallthrough]], etc.)
        Returns a list of attribute names.
        """
        attributes = []
        for child in node.children:
            if child.type == "attribute_declaration":
                for attr_child in child.named_children:
                    if attr_child.type == "attribute":
                        attr_text = attr_child.text.decode("utf-8")
                        attr_name = attr_text.split("(")[0].strip()
                        attributes.append(attr_name)
        return attributes

    def contains_function_call(self, node):
        """
        Check if a statement node contains a function call, method call, or constructor call.
        Used to determine if a statement should have sequential flow or if control transfers to a function.

        Returns True if the node contains:
        - call_expression (regular function calls)
        - An identifier followed by parentheses (function calls)

        Returns False otherwise (simple statements, assignments without calls, etc.)
        """
        if node is None:
            return False

        if node.type == "call_expression":
            return True

        for child in node.children:
            if child.type == "call_expression":
                return True
            if self.contains_function_call(child):
                return True

        return False

    def get_last_statement_in_function_body(self, function_node, node_list):
        """
        Find the last executable statement in a function body.
        Used for destructor chaining - we need to find where the destructor body ends
        so we can connect it directly to the base class destructor.

        Args:
            function_node: The function_definition AST node
            node_list: Dictionary of all nodes in the CFG

        Returns:
            (node_id, node) tuple of the last statement, or None if not found
        """
        body_node = function_node.child_by_field_name("body")

        if body_node is None:
            for child in function_node.children:
                if child.type == "compound_statement":
                    body_node = child
                    break

        if body_node is None:
            return None

        named_children = list(body_node.named_children)
        for child in reversed(named_children):
            if (child.start_point, child.end_point, child.type) in node_list:
                return (self.get_index(child), child)

        return None

    def add_edge(self, src, dest, edge_type, additional_data=None):
        """Add an edge to the CFG edge list with validation and deduplication.

        If *edge_type* contains a ``|`` suffix (e.g. ``"function_call|42"``),
        the suffix is extracted into ``additional_data["call_id"]`` and the
        edge type is stored cleanly (``"function_call"``).
        """
        if src is None or dest is None:
            logger.error(f"Attempting to add edge with None: {src} -> {dest}")
            return

        # Extract |suffix from edge_type into dedicated call_id attribute
        if "|" in edge_type:
            base_type, _, suffix = edge_type.partition("|")
            if additional_data is None:
                additional_data = {}
            # Use call_id for numeric ids, call_info for string labels
            try:
                additional_data["call_id"] = int(suffix)
            except ValueError:
                additional_data["call_id"] = suffix
            edge_type = base_type

        if additional_data:
            edge_tuple = (src, dest, edge_type, additional_data)
        else:
            edge_tuple = (src, dest, edge_type)

        if edge_tuple in self.CFG_edge_list:
            return

        self.CFG_edge_list.append(edge_tuple)

    def insert_scope_destructors(self, node_list):
        """
        Insert automatic destructor calls for objects going out of scope (RAII).
        For each scope with tracked objects:
        1. Find the last statement in that scope
        2. Create destructor call chain in reverse construction order
        3. Insert between last statement and next statement outside scope
        """

        index_to_key = {v: k for k, v in self.index.items()}

        for scope_key, objects in self.scope_objects.items():
            if not objects:
                continue

            objects_sorted = sorted(objects, key=lambda x: x[4])

            scope_start, scope_end, scope_type = scope_key
            scope_node = self.scope_nodes.get(scope_key)

            if not scope_node:
                continue

            last_stmt_node = None
            last_stmt_id = None

            for key, node in node_list.items():
                if (
                    node.start_point >= scope_start
                    and node.end_point <= scope_end
                    and node != scope_node
                ):
                    if node.type in self.statement_types["node_list_type"]:
                        if (
                            last_stmt_node is None
                            or node.start_point > last_stmt_node.start_point
                        ):
                            last_stmt_node = node
                            last_stmt_id = self.get_index(node)

            if not last_stmt_node or not last_stmt_id:
                continue

            next_after_scope_id, next_after_scope = self.get_next_index(
                scope_node, node_list
            )

            is_return_at_scope_exit = last_stmt_node.type == "return_statement"

            if next_after_scope_id == 2:
                parent = scope_node.parent
                while parent:
                    if parent.type == "function_definition":
                        if (
                            parent.start_point,
                            parent.end_point,
                            parent.type,
                        ) in node_list:
                            fn_id = self.get_index(parent)
                            if fn_id in self.records.get("implicit_return_map", {}):
                                next_after_scope_id = self.records[
                                    "implicit_return_map"
                                ][fn_id]
                            elif is_return_at_scope_exit:
                                next_after_scope_id = None
                            else:
                                next_after_scope_id = None
                        break
                    parent = parent.parent

            objects_reversed = list(reversed(objects_sorted))

            if next_after_scope_id != 2:
                destructor_ids = []
                for (
                    var_name,
                    class_name,
                    namespace_prefix,
                    decl_id,
                    order,
                ) in objects_reversed:
                    destructor_name = f"~{class_name}"
                    destructor_id = None

                    for ((fn_class_name, fn_name), fn_sig), fn_id in self.records.get(
                        "function_list", {}
                    ).items():
                        if fn_name == destructor_name:
                            if namespace_prefix:
                                if fn_class_name == namespace_prefix:
                                    destructor_id = fn_id
                                    break
                            else:
                                if fn_class_name == class_name:
                                    destructor_id = fn_id
                                    break

                    if destructor_id:
                        destructor_ids.append((var_name, class_name, destructor_id))

                if destructor_ids:

                    if is_return_at_scope_exit:
                        first_var_name, first_class_name, first_dest_id = (
                            destructor_ids[0]
                        )
                        self.add_edge(
                            last_stmt_id, first_dest_id, "scope_exit_destructor"
                        )
                    else:
                        first_var_name, first_class_name, first_dest_id = (
                            destructor_ids[0]
                        )
                        self.add_edge(
                            last_stmt_id, first_dest_id, "scope_exit_destructor"
                        )

                    for i in range(len(destructor_ids)):
                        var_name, class_name, curr_dest_id = destructor_ids[i]

                        implicit_return_id = self.records.get(
                            "implicit_return_map", {}
                        ).get(curr_dest_id)

                        if not implicit_return_id:
                            continue
                        if i < len(destructor_ids) - 1:
                            next_var_name, next_class_name, next_dest_id = (
                                destructor_ids[i + 1]
                            )
                            edge_label = f"destructor_chain|{var_name}"
                            self.add_edge(implicit_return_id, next_dest_id, edge_label)
                        else:
                            edge_label = f"scope_destructor_return|{var_name}"
                            if next_after_scope_id is not None:
                                if not hasattr(self, "_pending_destructor_returns"):
                                    self._pending_destructor_returns = []
                                self._pending_destructor_returns.append(
                                    (
                                        implicit_return_id,
                                        next_after_scope_id,
                                        edge_label,
                                        class_name,
                                    )
                                )

    def chain_base_class_destructors(self):
        """
        Chain base class destructors to derived class destructors.
        In C++, when a derived class destructor completes, the base class destructor
        is automatically called. This method creates edges from the end of derived
        class destructors to their base class destructors.

        For each derived class destructor:
        1. Find its implicit return point
        2. Find base class destructors from inheritance hierarchy
        3. Chain: ~Derived() implicit_return -> ~Base() entry
        4. Chain base destructors if there are multiple levels of inheritance
        """

        inheritance_map = {}

        if "extends" in self.records and self.records["extends"]:
            for class_name, base_classes in self.records["extends"].items():
                if base_classes:
                    inheritance_map[class_name] = (
                        base_classes
                        if isinstance(base_classes, list)
                        else [base_classes]
                    )

        if not inheritance_map:

            def extract_inheritance(node):
                if node.type in ["class_specifier", "struct_specifier"]:
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        class_name = name_node.text.decode("utf-8")

                        base_classes = []
                        for child in node.children:
                            if child.type == "base_class_clause":
                                for subchild in child.children:
                                    if subchild.type in [
                                        "type_identifier",
                                        "qualified_identifier",
                                    ]:
                                        base_name = subchild.text.decode("utf-8")
                                        base_classes.append(base_name)

                        if base_classes:
                            inheritance_map[class_name] = base_classes

                for child in node.children:
                    extract_inheritance(child)

            extract_inheritance(self.root_node)

        for ((fn_class_name, fn_name), fn_sig), fn_id in self.records.get(
            "function_list", {}
        ).items():
            if not fn_name.startswith("~"):
                continue

            actual_class_name = fn_name[1:]

            if actual_class_name not in inheritance_map:
                continue

            base_classes = inheritance_map[actual_class_name]
            if not base_classes:
                continue

            implicit_return_id = self.records.get("implicit_return_map", {}).get(fn_id)
            if not implicit_return_id:
                continue

            for base_class in base_classes:
                base_destructor_name = f"~{base_class}"
                base_destructor_id = None

                candidates = []
                index_to_key = {v: k for k, v in self.index.items()}
                for (
                    (base_fn_class, base_fn_name),
                    base_fn_sig,
                ), base_fn_id in self.records.get("function_list", {}).items():
                    is_match = False
                    if (
                        base_fn_class == base_class
                        and base_fn_name == base_destructor_name
                    ):
                        is_match = True
                    elif base_fn_class in [None, "None"] and base_fn_name.startswith(
                        f"{base_class}::~"
                    ):
                        is_match = True

                    if is_match:
                        has_body = False
                        fn_key = index_to_key.get(base_fn_id)
                        if fn_key:
                            fn_node = self.node_list.get(fn_key)
                            if fn_node:
                                for child in fn_node.children:
                                    if child.type == "compound_statement":
                                        has_body = True
                                        break
                        candidates.append((base_fn_id, has_body))

                for candidate_id, has_body in candidates:
                    if has_body:
                        base_destructor_id = candidate_id
                        break

                if not base_destructor_id and candidates:
                    base_destructor_id = candidates[0][0]

                if base_destructor_id:
                    self.add_edge(
                        implicit_return_id, base_destructor_id, "base_destructor_call"
                    )

                    base_implicit_return_id = self.records.get(
                        "implicit_return_map", {}
                    ).get(base_destructor_id)
                    if base_implicit_return_id:
                        if hasattr(self, "_pending_destructor_returns"):
                            for pend_src, pend_dest, pend_label, pend_class in list(
                                self._pending_destructor_returns
                            ):
                                if pend_src == implicit_return_id:
                                    self.add_edge(
                                        base_implicit_return_id, pend_dest, pend_label
                                    )
                                    self._pending_destructor_returns.remove(
                                        (pend_src, pend_dest, pend_label, pend_class)
                                    )

        if hasattr(self, "_pending_destructor_returns"):
            for (
                pend_src,
                pend_dest,
                pend_label,
                pend_class,
            ) in self._pending_destructor_returns:
                self.add_edge(pend_src, pend_dest, pend_label)

    def extract_inheritance_info(self, root_node):
        """
        Extract inheritance relationships from class definitions.
        Populates self.records["extends"] with class_name -> [base_classes] mapping.
        Should be called early in CFG construction before constructor/destructor processing.
        """

        def extract_from_node(node):
            if node.type in ["class_specifier", "struct_specifier"]:
                name_node = node.child_by_field_name("name")
                if name_node:
                    class_name = name_node.text.decode("utf-8")

                    base_classes = []
                    for child in node.children:
                        if child.type == "base_class_clause":
                            for subchild in child.children:
                                if subchild.type in [
                                    "type_identifier",
                                    "qualified_identifier",
                                ]:
                                    base_name = subchild.text.decode("utf-8")
                                    base_classes.append(base_name)

                    if base_classes:
                        self.records["extends"][class_name] = base_classes

            for child in node.children:
                extract_from_node(child)

        extract_from_node(root_node)

    def function_list(self, root_node, node_list):
        """
        Build a map of all function/method calls in the program.
        Maps function signatures to their call sites.
        Handles:
        - Regular function calls
        - Member function calls (obj.method())
        - Constructor calls (MyClass obj)
        - Operator overload calls
        """
        if root_node.type == "call_expression":
            function_node = root_node.child_by_field_name("function")
            if function_node:
                func_name = None
                is_indirect_call = False
                pointer_var = None
                qualified_scope = None

                if function_node.type == "identifier":
                    func_name = function_node.text.decode("utf-8")

                    if func_name in {
                        "noexcept",
                        "sizeof",
                        "alignof",
                        "decltype",
                        "typeid",
                        "static_assert",
                        "requires",
                    }:
                        return

                    is_constructor = False
                    for ((fn_class_name, fn_name), fn_sig), fn_id in self.records.get(
                        "function_list", {}
                    ).items():
                        if fn_class_name == func_name and fn_name == func_name:
                            is_constructor = True
                            break

                    if is_constructor:
                        class_name = func_name
                        parent_stmt = root_node
                        while (
                            parent_stmt
                            and parent_stmt.type
                            not in self.statement_types["node_list_type"]
                        ):
                            parent_stmt = parent_stmt.parent

                        if (
                            parent_stmt
                            and (
                                parent_stmt.start_point,
                                parent_stmt.end_point,
                                parent_stmt.type,
                            )
                            in node_list
                        ):
                            parent_index = self.get_index(parent_stmt)
                            call_index = self.get_index(root_node)

                            args_node = root_node.child_by_field_name("arguments")
                            signature = self.get_call_signature(args_node)

                            key = (class_name, signature)
                            if key not in self.records["constructor_calls"]:
                                self.records["constructor_calls"][key] = []
                            self.records["constructor_calls"][key].append(
                                (call_index, parent_index)
                            )

                        for child in root_node.children:
                            self.function_list(child, node_list)
                        return

                elif function_node.type == "field_expression":
                    field = function_node.child_by_field_name("field")
                    if field:
                        func_name = field.text.decode("utf-8")

                elif function_node.type == "qualified_identifier":
                    full_name = function_node.text.decode("utf-8")
                    parts = full_name.split("::")
                    if len(parts) >= 2:
                        func_name = parts[-1]
                        qualified_scope = "::".join(parts[:-1])

                        scope_parts = qualified_scope.split("::")
                        if scope_parts[0] in self.records.get("namespace_aliases", {}):
                            actual_namespace = self.records["namespace_aliases"][
                                scope_parts[0]
                            ]
                            if len(scope_parts) > 1:
                                qualified_scope = (
                                    actual_namespace + "::" + "::".join(scope_parts[1:])
                                )
                            else:
                                qualified_scope = actual_namespace
                    else:
                        func_name = full_name
                        qualified_scope = None

                elif function_node.type == "subscript_expression":
                    is_indirect_call = True
                    argument = function_node.child_by_field_name("argument")
                    if argument and argument.type == "identifier":
                        pointer_var = argument.text.decode("utf-8")

                elif function_node.type == "template_function":
                    identifier_node = None
                    for child in function_node.named_children:
                        if child.type == "identifier":
                            identifier_node = child
                            break

                    if identifier_node:
                        func_name = identifier_node.text.decode("utf-8")

                parent_stmt = root_node
                while (
                    parent_stmt
                    and parent_stmt.type not in self.statement_types["node_list_type"]
                ):
                    parent_stmt = parent_stmt.parent

                if (
                    parent_stmt
                    and (
                        parent_stmt.start_point,
                        parent_stmt.end_point,
                        parent_stmt.type,
                    )
                    in node_list
                ):
                    parent_index = self.get_index(parent_stmt)
                    call_index = self.get_index(function_node)

                    args_node = root_node.child_by_field_name("arguments")
                    signature = self.get_call_signature(args_node)

                    self.track_lambda_arguments(root_node, call_index)

                    if is_indirect_call and pointer_var:
                        key = (pointer_var, signature)
                        if key not in self.records["indirect_calls"]:
                            self.records["indirect_calls"][key] = []
                        self.records["indirect_calls"][key].append(
                            (call_index, parent_index)
                        )
                    elif func_name:
                        if function_node.type == "field_expression":
                            object_name = None
                            argument_node = function_node.child_by_field_name(
                                "argument"
                            )
                            if argument_node and argument_node.type == "identifier":
                                object_name = argument_node.text.decode("utf-8")

                            key = (func_name, signature)
                            if key not in self.records["method_calls"]:
                                self.records["method_calls"][key] = []
                            self.records["method_calls"][key].append(
                                (call_index, parent_index, object_name)
                            )
                        elif qualified_scope:
                            key = (qualified_scope, func_name, signature)
                            if key not in self.records["static_method_calls"]:
                                self.records["static_method_calls"][key] = []
                            self.records["static_method_calls"][key].append(
                                (call_index, parent_index)
                            )
                        else:
                            key = (func_name, signature)
                            if key not in self.records["function_calls"]:
                                self.records["function_calls"][key] = []
                            self.records["function_calls"][key].append(
                                (call_index, parent_index)
                            )

        elif root_node.type == "declaration":
            type_node = root_node.child_by_field_name("type")

            class_name = None
            template_args = None

            namespace_prefix = None

            if type_node and type_node.type == "type_identifier":
                class_name = type_node.text.decode("utf-8")
            elif type_node and type_node.type == "qualified_identifier":
                full_name = type_node.text.decode("utf-8")
                parts = full_name.split("::")
                class_name = parts[-1]
                if len(parts) > 1:
                    namespace_prefix = "::".join(parts[:-1])
            elif type_node and type_node.type == "template_type":
                for child in type_node.named_children:
                    if child.type == "type_identifier":
                        class_name = child.text.decode("utf-8")
                    elif child.type == "qualified_identifier":
                        full_name = child.text.decode("utf-8")
                        parts = full_name.split("::")
                        class_name = parts[-1]
                        if len(parts) > 1:
                            namespace_prefix = "::".join(parts[:-1])
                    elif child.type == "template_argument_list":
                        template_args = []
                        for arg in child.named_children:
                            arg_text = arg.text.decode("utf-8")
                            template_args.append(arg_text)
                        template_args = tuple(template_args)

            c_types_no_constructors = {
                "va_list",
                "FILE",
                "size_t",
                "ptrdiff_t",
                "time_t",
                "clock_t",
                "jmp_buf",
                "sig_atomic_t",
                "wchar_t",
                "mbstate_t",
                "fpos_t",
                "div_t",
                "ldiv_t",
                "lldiv_t",
                "imaxdiv_t",
                "tm",
                "vector",
                "list",
                "deque",
                "queue",
                "priority_queue",
                "stack",
                "set",
                "multiset",
                "map",
                "multimap",
                "unordered_set",
                "unordered_multiset",
                "unordered_map",
                "unordered_multimap",
                "string",
                "wstring",
                "u16string",
                "u32string",
                "pair",
                "tuple",
                "array",
                "bitset",
                "unique_ptr",
                "shared_ptr",
                "weak_ptr",
                "optional",
                "variant",
                "any",
                "function",
                "reference_wrapper",
                "istream",
                "ostream",
                "iostream",
                "ifstream",
                "ofstream",
                "fstream",
                "istringstream",
                "ostringstream",
                "stringstream",
                "cin",
                "cout",
                "cerr",
                "clog",
            }

            if class_name and class_name not in c_types_no_constructors:

                parent_stmt = root_node
                while (
                    parent_stmt
                    and parent_stmt.type not in self.statement_types["node_list_type"]
                ):
                    parent_stmt = parent_stmt.parent

                if (
                    parent_stmt
                    and (
                        parent_stmt.start_point,
                        parent_stmt.end_point,
                        parent_stmt.type,
                    )
                    in node_list
                ):
                    parent_index = self.get_index(parent_stmt)
                    call_index = parent_index

                    scope_node = root_node.parent
                    while scope_node:
                        if scope_node.type == "compound_statement":
                            scope_key = (
                                scope_node.start_point,
                                scope_node.end_point,
                                scope_node.type,
                            )
                            if scope_key not in self.scope_objects:
                                self.scope_objects[scope_key] = []
                            if scope_key not in self.scope_nodes:
                                self.scope_nodes[scope_key] = scope_node
                            break
                        scope_node = scope_node.parent

                    has_init_declarator = False
                    var_name = None
                    for child in root_node.children:
                        if child.type == "init_declarator":
                            has_init_declarator = True

                            declarator = child.child_by_field_name("declarator")
                            is_pointer_declarator = False
                            if declarator:
                                if declarator.type == "identifier":
                                    var_name = declarator.text.decode("utf-8")
                                elif declarator.type == "pointer_declarator":
                                    is_pointer_declarator = True
                                    ptr_var_name = None
                                    for ptr_child in declarator.children:
                                        if ptr_child.type == "identifier":
                                            ptr_var_name = ptr_child.text.decode(
                                                "utf-8"
                                            )
                                            break

                                    if ptr_var_name:
                                        value_node = child.child_by_field_name("value")
                                        if (
                                            value_node
                                            and value_node.type == "pointer_expression"
                                        ):
                                            is_address_of = False
                                            target_var = None
                                            for pe_child in value_node.children:
                                                if pe_child.type == "&":
                                                    is_address_of = True
                                                elif (
                                                    pe_child.type == "identifier"
                                                    and is_address_of
                                                ):
                                                    target_var = pe_child.text.decode(
                                                        "utf-8"
                                                    )
                                                    break

                                            if is_address_of and target_var:
                                                for (
                                                    scope_key,
                                                    obj_list,
                                                ) in self.scope_objects.items():
                                                    for obj_info in obj_list:
                                                        if (
                                                            len(obj_info) >= 3
                                                            and obj_info[0]
                                                            == target_var
                                                        ):
                                                            concrete_class = obj_info[1]
                                                            concrete_namespace = (
                                                                obj_info[2]
                                                            )
                                                            self.pointer_targets[
                                                                ptr_var_name
                                                            ] = (
                                                                concrete_class,
                                                                concrete_namespace,
                                                            )
                                                            break

                            if is_pointer_declarator:
                                continue

                            args_node = None
                            has_initializer = False
                            is_move = False
                            is_copy = False
                            is_function_return_init = False

                            for subchild in child.children:
                                if subchild.type == "argument_list":
                                    args_node = subchild
                                    break
                                elif subchild.text.decode("utf-8") == "=":
                                    has_initializer = True
                                elif (
                                    has_initializer
                                    and subchild.type == "call_expression"
                                ):
                                    func_node = subchild.child_by_field_name("function")
                                    if func_node:
                                        func_text = func_node.text.decode("utf-8")
                                        if "move" in func_text:
                                            is_move = True
                                            args = subchild.child_by_field_name(
                                                "arguments"
                                            )
                                            if args and args.named_child_count > 0:
                                                moved_arg = args.named_children[0]
                                                signature = (f"{class_name}&&",)
                                            break
                                        else:
                                            is_function_return_init = True
                                            break
                                elif has_initializer and subchild.type == "identifier":
                                    is_copy = True
                                    signature = (f"const {class_name}&",)
                                    break

                            if args_node:
                                signature = self.get_call_signature(args_node)
                                key = ((namespace_prefix, class_name), signature)
                                if key not in self.records["constructor_calls"]:
                                    self.records["constructor_calls"][key] = []
                                self.records["constructor_calls"][key].append(
                                    (call_index, parent_index)
                                )
                            elif is_move:
                                key = ((namespace_prefix, class_name), signature)
                                if key not in self.records["constructor_calls"]:
                                    self.records["constructor_calls"][key] = []
                                self.records["constructor_calls"][key].append(
                                    (call_index, parent_index)
                                )
                            elif is_copy:
                                key = ((namespace_prefix, class_name), signature)
                                if key not in self.records["constructor_calls"]:
                                    self.records["constructor_calls"][key] = []
                                self.records["constructor_calls"][key].append(
                                    (call_index, parent_index)
                                )
                            elif is_function_return_init:
                                call_expr = None
                                for subchild in child.children:
                                    if subchild.type == "call_expression":
                                        call_expr = subchild
                                        break

                                if call_expr:
                                    func_node = call_expr.child_by_field_name(
                                        "function"
                                    )
                                    if func_node and func_node.type == "identifier":
                                        func_name = func_node.text.decode("utf-8")
                                        args_node = call_expr.child_by_field_name(
                                            "arguments"
                                        )
                                        signature = self.get_call_signature(args_node)
                                        key = (func_name, signature)
                                        func_call_index = self.get_index(call_expr)
                                        if key not in self.records["function_calls"]:
                                            self.records["function_calls"][key] = []
                                        self.records["function_calls"][key].append(
                                            (func_call_index, parent_index)
                                        )
                            else:
                                signature = tuple()
                                key = ((namespace_prefix, class_name), signature)
                                if key not in self.records["constructor_calls"]:
                                    self.records["constructor_calls"][key] = []
                                self.records["constructor_calls"][key].append(
                                    (call_index, parent_index)
                                )

                    if not has_init_declarator:
                        is_pointer_declaration = False
                        for child in root_node.children:
                            if child.type == "pointer_declarator":
                                is_pointer_declaration = True
                                break

                        if not is_pointer_declaration:
                            for child in root_node.children:
                                if child.type == "identifier":
                                    var_name = child.text.decode("utf-8")
                                    break

                            signature = tuple()
                            key = ((namespace_prefix, class_name), signature)
                            if key not in self.records["constructor_calls"]:
                                self.records["constructor_calls"][key] = []
                            self.records["constructor_calls"][key].append(
                                (call_index, parent_index)
                            )

                    if var_name and scope_node:
                        scope_key = (
                            scope_node.start_point,
                            scope_node.end_point,
                            scope_node.type,
                        )
                        order = len(self.scope_objects.get(scope_key, []))
                        self.scope_objects[scope_key].append(
                            (
                                var_name,
                                class_name,
                                namespace_prefix,
                                parent_index,
                                order,
                            )
                        )
                        self.object_scope_map[var_name] = scope_key

                    if var_name and template_args:
                        self.template_instantiations[var_name] = (
                            class_name,
                            template_args,
                            None,
                        )

                    return

        elif root_node.type == "new_expression":
            type_node = root_node.child_by_field_name("type")
            if type_node:
                class_name = None
                if type_node.type == "type_identifier":
                    class_name = type_node.text.decode("utf-8")

                if class_name:
                    parent = root_node.parent
                    var_name = None
                    while parent:
                        if parent.type == "declaration":
                            for child in parent.children:
                                if child.type == "init_declarator":
                                    declarator = child.child_by_field_name("declarator")
                                    if declarator:
                                        if declarator.type == "pointer_declarator":
                                            for subchild in declarator.children:
                                                if subchild.type == "identifier":
                                                    var_name = subchild.text.decode(
                                                        "utf-8"
                                                    )
                                                    break
                                        elif declarator.type == "identifier":
                                            var_name = declarator.text.decode("utf-8")
                                    break
                            break
                        elif parent.type == "assignment_expression":
                            left = parent.child_by_field_name("left")
                            if left and left.type == "identifier":
                                var_name = left.text.decode("utf-8")
                            break
                        parent = parent.parent

                    if var_name:
                        self.runtime_types[var_name] = class_name

                    parent_stmt = root_node
                    while (
                        parent_stmt
                        and parent_stmt.type
                        not in self.statement_types["node_list_type"]
                    ):
                        parent_stmt = parent_stmt.parent

                    if (
                        parent_stmt
                        and (
                            parent_stmt.start_point,
                            parent_stmt.end_point,
                            parent_stmt.type,
                        )
                        in node_list
                    ):
                        parent_index = self.get_index(parent_stmt)

                        call_index = parent_index
                        if (
                            root_node.start_point,
                            root_node.end_point,
                            root_node.type,
                        ) in node_list:
                            call_index = self.get_index(root_node)

                        args_node = root_node.child_by_field_name("arguments")

                        if args_node:
                            signature = self.get_call_signature(args_node)
                        else:
                            signature = tuple()

                        key = (class_name, signature)
                        if key not in self.records["constructor_calls"]:
                            self.records["constructor_calls"][key] = []
                        self.records["constructor_calls"][key].append(
                            (call_index, parent_index)
                        )

        delete_expr_node = None
        if root_node.type == "delete_expression":
            delete_expr_node = root_node
        elif root_node.type == "expression_statement":
            for child in root_node.children:
                if child.type == "delete_expression":
                    delete_expr_node = child
                    break

        if delete_expr_node:
            arg_node = None
            if delete_expr_node.named_child_count > 0:
                arg_node = delete_expr_node.named_children[0]
            if arg_node:
                class_name = None
                var_name = None

                if arg_node.type == "identifier":
                    arg_text = arg_node.text.decode("utf-8")
                    var_name = arg_text

                    if var_name in self.runtime_types:
                        class_name = self.runtime_types[var_name]
                    else:
                        arg_key = (
                            arg_node.start_point,
                            arg_node.end_point,
                            arg_node.type,
                        )
                        if arg_key in self.index:
                            arg_index = self.index[arg_key]
                            if arg_index in self.declaration_map:
                                decl_index = self.declaration_map[arg_index]
                                if decl_index in self.symbol_table.get("data_type", {}):
                                    data_type = self.symbol_table["data_type"][
                                        decl_index
                                    ]
                                    class_name = (
                                        data_type.replace("*", "")
                                        .replace("&", "")
                                        .strip()
                                    )

                if class_name:
                    parent_stmt = root_node
                    while (
                        parent_stmt
                        and parent_stmt.type
                        not in self.statement_types["node_list_type"]
                    ):
                        parent_stmt = parent_stmt.parent

                    if (
                        parent_stmt
                        and (
                            parent_stmt.start_point,
                            parent_stmt.end_point,
                            parent_stmt.type,
                        )
                        in node_list
                    ):
                        parent_index = self.get_index(parent_stmt)

                        call_index = parent_index
                        if (
                            root_node.start_point,
                            root_node.end_point,
                            root_node.type,
                        ) in node_list:
                            call_index = self.get_index(root_node)

                        if class_name not in self.records["destructor_calls"]:
                            self.records["destructor_calls"][class_name] = []
                        self.records["destructor_calls"][class_name].append(
                            (call_index, parent_index)
                        )

        elif root_node.type == "function_definition":
            field_init_list = None
            for child in root_node.children:
                if child.type == "field_initializer_list":
                    field_init_list = child
                    break

            if field_init_list:
                if (
                    root_node.start_point,
                    root_node.end_point,
                    root_node.type,
                ) in node_list:
                    constructor_index = self.get_index(root_node)

                    containing_class = self.get_containing_class(root_node)
                    if containing_class:
                        base_class_names = self.get_base_classes(containing_class)

                        for child in field_init_list.children:
                            if child.type == "field_initializer":
                                field_id = None
                                args_node = None

                                for subchild in child.children:
                                    if subchild.type == "field_identifier":
                                        field_id = subchild.text.decode("utf-8")
                                    elif subchild.type == "argument_list":
                                        args_node = subchild

                                if field_id and field_id in base_class_names:
                                    signature = (
                                        self.get_call_signature(args_node)
                                        if args_node
                                        else tuple()
                                    )
                                    key = (field_id, signature)

                                    call_id = constructor_index
                                    if (
                                        child.start_point,
                                        child.end_point,
                                        child.type,
                                    ) in node_list:
                                        call_id = self.get_index(child)

                                    if key not in self.records["constructor_calls"]:
                                        self.records["constructor_calls"][key] = []
                                    self.records["constructor_calls"][key].append(
                                        (call_id, constructor_index)
                                    )

        elif root_node.type in [
            "binary_expression",
            "assignment_expression",
            "update_expression",
        ]:
            parent_stmt = root_node
            while (
                parent_stmt
                and parent_stmt.type not in self.statement_types["node_list_type"]
            ):
                parent_stmt = parent_stmt.parent

            if (
                parent_stmt
                and (parent_stmt.start_point, parent_stmt.end_point, parent_stmt.type)
                in node_list
            ):
                parent_index = self.get_index(parent_stmt)
                call_index = self.get_index(root_node)

                operator_symbol = None
                left_operand = None
                right_operand = None
                is_member_operator = True

                if root_node.type == "binary_expression":
                    left_operand = root_node.child_by_field_name("left")
                    right_operand = root_node.child_by_field_name("right")
                    for child in root_node.children:
                        if child.type in [
                            "+",
                            "-",
                            "*",
                            "/",
                            "%",
                            "==",
                            "!=",
                            "<",
                            ">",
                            "<=",
                            ">=",
                            "<<",
                            ">>",
                            "&",
                            "|",
                            "^",
                            "&&",
                            "||",
                        ]:
                            operator_symbol = child.type
                            break

                    if operator_symbol in ["<<", ">>"]:
                        is_member_operator = False

                elif root_node.type == "assignment_expression":
                    operator_symbol = "="
                    left_operand = root_node.child_by_field_name("left")
                    right_operand = root_node.child_by_field_name("right")

                elif root_node.type == "update_expression":
                    operand = root_node.child_by_field_name("argument")
                    if operand:
                        left_operand = operand
                        for child in root_node.children:
                            if child.type in ["++", "--"]:
                                operator_symbol = child.type
                                if child.start_byte < operand.start_byte:
                                    operator_symbol = f"{child.type}_prefix"
                                else:
                                    operator_symbol = f"{child.type}_postfix"
                                break

                if operator_symbol and left_operand:
                    if operator_symbol in ["<<", ">>"] and right_operand:
                        operand_type = self.get_operand_type(right_operand)
                    else:
                        operand_type = self.get_operand_type(left_operand)

                    key = (operator_symbol, is_member_operator)
                    if key not in self.records["operator_calls"]:
                        self.records["operator_calls"][key] = []
                    self.records["operator_calls"][key].append(
                        (call_index, parent_index, operand_type)
                    )

        for child in root_node.children:
            self.function_list(child, node_list)

    def get_operand_type(self, operand_node):
        """
        Determine the type of an operand (variable/object).
        Used for operator overload resolution.
        """
        if not operand_node:
            return None

        if operand_node.type == "identifier":
            node_key = (
                operand_node.start_point,
                operand_node.end_point,
                operand_node.type,
            )
            if node_key in self.index:
                node_id = self.index[node_key]
                if hasattr(self.parser, "symbol_table") and isinstance(
                    self.parser.symbol_table, dict
                ):
                    data_type = self.parser.symbol_table.get("data_type", {})

                    if node_id in data_type:
                        return data_type[node_id]

                    if (
                        hasattr(self.parser, "declaration_map")
                        and node_id in self.parser.declaration_map
                    ):
                        decl_id = self.parser.declaration_map[node_id]
                        if decl_id in data_type:
                            return data_type[decl_id]

            var_name = operand_node.text.decode("utf-8")
            return var_name

        elif operand_node.type == "field_expression":
            argument = operand_node.child_by_field_name("argument")
            if argument:
                return self.get_operand_type(argument)

        elif operand_node.type == "subscript_expression":
            argument = operand_node.child_by_field_name("argument")
            if argument:
                return self.get_operand_type(argument)

        elif operand_node.type == "qualified_identifier":
            return operand_node.text.decode("utf-8")

        elif operand_node.type == "parenthesized_expression":
            for child in operand_node.children:
                if child.type not in ["(", ")"]:
                    return self.get_operand_type(child)
            return None

        elif operand_node.type == "pointer_expression":
            argument = operand_node.child_by_field_name("argument")
            if argument:
                if argument.type == "this":
                    containing_class = self.get_containing_class(operand_node)
                    if containing_class:
                        class_name_node = None
                        for child in containing_class.children:
                            if child.type == "type_identifier":
                                class_name_node = child
                                break
                        if class_name_node:
                            return class_name_node.text.decode("utf-8")
                    return None

                base_type = self.get_operand_type(argument)
                if base_type and base_type.endswith("*"):
                    return base_type[:-1]
                return base_type

        elif operand_node.type == "this":
            containing_class = self.get_containing_class(operand_node)
            if containing_class:
                class_name_node = None
                for child in containing_class.children:
                    if child.type == "type_identifier":
                        class_name_node = child
                        break
                if class_name_node:
                    return class_name_node.text.decode("utf-8") + "*"
            return None

        return None

    def get_call_signature(self, args_node):
        """
        Extract the signature (tuple of argument types) from an argument_list node.
        Used for function overload resolution.
        """
        signature = []
        if args_node is None:
            return tuple(signature)

        for child in args_node.named_children:
            arg_type = self.get_argument_type(child)
            signature.append(arg_type)

        return tuple(signature)

    def is_template_parameter(self, type_name):
        """
        Check if a type name is a template parameter.

        Template parameters are typically:
        - Single uppercase letters: T, U, V, K, etc.
        - Common template parameter names: _Tp, _Ty, TValue, etc.
        - Type names used in template declarations

        Args:
            type_name: The type name to check

        Returns:
            bool: True if type_name is a template parameter
        """
        if not type_name:
            return False

        type_clean = type_name.strip()

        if len(type_clean) == 1 and type_clean.isupper():
            return True

        if type_clean.startswith("_T") and len(type_clean) <= 4:
            return True

        if (
            type_clean.startswith("T")
            and len(type_clean) <= 10
            and type_clean[0].isupper()
        ):
            common_types = {"Table", "Tree", "Time", "Token", "Type", "Text", "Tuple"}
            if type_clean not in common_types:
                return True

        return False

    def signatures_match(self, call_sig, func_sig):
        """
        Check if a call signature matches a function signature with lenient matching rules.

        Lenient matching rules:
        - Exact match: 'int' matches 'int'
        - Template parameters: 'T' matches any concrete type like 'int', 'double', etc.
        - Lvalue to value: 'int&' matches 'int' (lvalue can bind to value parameter)
        - Const reference to value: 'const int&' matches 'int'
        - 'unknown' matches any type (for cases where we can't infer the type)
        - Variadic functions: If func_sig ends with '...', call_sig can have any number of extra arguments

        Args:
            call_sig: Tuple of argument types from the call site
            func_sig: Tuple of parameter types from the function definition

        Returns:
            bool: True if signatures are compatible, False otherwise
        """
        is_variadic = len(func_sig) > 0 and func_sig[-1] == "..."

        if is_variadic:
            fixed_param_count = len(func_sig) - 1

            if len(call_sig) < fixed_param_count:
                return False

            params_to_check = zip(
                call_sig[:fixed_param_count], func_sig[:fixed_param_count]
            )
        else:
            if len(call_sig) != len(func_sig):
                return False

            params_to_check = zip(call_sig, func_sig)

        for call_type, func_type in params_to_check:
            if call_type == func_type:
                continue

            if call_type == "unknown" or func_type == "unknown":
                continue

            if self.is_template_parameter(func_type):
                continue

            call_type_clean = call_type.strip()
            func_type_clean = func_type.strip()

            if call_type_clean.endswith("&") and not call_type_clean.endswith("&&"):
                base_call_type = call_type_clean[:-1].strip()
                base_call_type_no_const = base_call_type.replace("const", "").strip()
                func_type_no_const = func_type_clean.replace("const", "").strip()
                if base_call_type_no_const == func_type_no_const:
                    continue

            if "const" in call_type_clean and call_type_clean.endswith("&"):
                base_call_type = (
                    call_type_clean.replace("const", "").replace("&", "").strip()
                )
                func_type_no_const = func_type_clean.replace("const", "").strip()
                if base_call_type == func_type_no_const:
                    continue

            if "*" in call_type_clean or "*" in func_type_clean:
                call_type_no_const = call_type_clean.replace("const", "").strip()
                func_type_no_const = func_type_clean.replace("const", "").strip()
                if call_type_no_const == func_type_no_const:
                    continue

            if (
                "char*" in call_type_clean or "char *" in call_type_clean
            ) and "string" in func_type_clean:
                continue

            return False

        return True

    def get_argument_type(self, arg_node):
        """
        Infer the type of an argument expression for C++ with value category detection.
        Returns type with appropriate reference qualifier (&, &&, or none).

        Value categories:
        - Lvalues (identifiers, dereferencing) → append '&'
        - Rvalues (literals, temporaries) → no qualifier (prvalues) or '&&' (xvalues)
        - std::move() → append '&&'
        - std::forward<T>() → preserve T's reference type
        """
        if arg_node is None:
            return "unknown"

        node_type = arg_node.type

        if node_type == "call_expression":
            function_node = arg_node.child_by_field_name("function")

            if function_node:
                func_text = function_node.text.decode("utf-8")

                if func_text in ["std::move", "move"]:
                    args_node = arg_node.child_by_field_name("arguments")
                    if args_node and len(args_node.named_children) > 0:
                        inner_arg = args_node.named_children[0]
                        base_type = self.get_argument_type(inner_arg)
                        base_type = base_type.rstrip("&").rstrip()
                        return base_type + "&&"

                elif func_text in ["std::forward", "forward"] or "forward" in func_text:
                    if function_node.type == "template_function":
                        for child in function_node.named_children:
                            if child.type == "template_argument_list":
                                if len(child.named_children) > 0:
                                    template_arg = child.named_children[0]
                                    return template_arg.text.decode("utf-8")

                    args_node = arg_node.child_by_field_name("arguments")
                    if args_node and len(args_node.named_children) > 0:
                        inner_arg = args_node.named_children[0]
                        return self.get_argument_type(inner_arg)

                return "unknown"

        if node_type == "identifier":
            arg_index_key = (arg_node.start_point, arg_node.end_point, arg_node.type)
            if arg_index_key in self.index:
                arg_index = self.index[arg_index_key]
                if arg_index in self.declaration_map:
                    decl_index = self.declaration_map[arg_index]
                    if decl_index in self.symbol_table["data_type"]:
                        data_type = self.symbol_table["data_type"][decl_index]

                        decl_node_key = None
                        for key, idx in self.index.items():
                            if idx == decl_index:
                                decl_node_key = key
                                break

                        is_array = False
                        if decl_node_key and decl_node_key in self.node_list:
                            decl_node = self.node_list[decl_node_key]
                            parent = decl_node.parent
                            if parent:
                                for child in parent.children:
                                    if child.type == "array_declarator":
                                        is_array = True
                                        break
                                    if child.type == "init_declarator":
                                        for subchild in child.children:
                                            if subchild.type == "array_declarator":
                                                is_array = True
                                                break

                        if not is_array:
                            var_name = arg_node.text.decode("utf-8")

                            def find_array_declaration(node, var_name):
                                if node.type == "array_declarator":
                                    for child in node.children:
                                        if (
                                            child.type == "identifier"
                                            and child.text.decode("utf-8") == var_name
                                        ):
                                            return True
                                        if find_array_declaration(child, var_name):
                                            return True
                                for child in node.children:
                                    if find_array_declaration(child, var_name):
                                        return True
                                return False

                            if self.root_node and find_array_declaration(
                                self.root_node, var_name
                            ):
                                is_array = True

                        if is_array:
                            return data_type + "*"

                        if data_type.endswith("&&"):
                            base_type = data_type[:-2].rstrip()
                            return base_type + "&"
                        elif data_type.endswith("&"):
                            return data_type
                        else:
                            return data_type + "&"
            return "unknown"

        elif node_type == "number_literal":
            text = arg_node.text.decode("utf-8").lower()
            if "." in text or "e" in text:
                return "float" if text.endswith("f") else "double"
            else:
                return "int"

        elif node_type == "string_literal":
            return "const char*"

        elif node_type == "char_literal":
            return "char"

        elif node_type in ["true", "false"]:
            return "bool"

        elif node_type == "nullptr":
            return "nullptr_t"

        elif node_type == "pointer_expression":
            operator = None
            operand = None
            for child in arg_node.children:
                if child.type == "&":
                    operator = "&"
                elif child.type == "*":
                    operator = "*"
                elif child.is_named:
                    operand = child

            if operator == "&" and operand:
                base_type = self.get_argument_type(operand)
                base_type = base_type.rstrip("&").rstrip()
                return base_type + "*"
            elif operator == "*" and operand:
                base_type = self.get_argument_type(operand)
                if base_type.endswith("*"):
                    return base_type[:-1].rstrip() + "&"
                else:
                    return base_type.rstrip("&").rstrip() + "&"
            else:
                for child in arg_node.named_children:
                    base_type = self.get_argument_type(child)
                    if base_type.endswith("*"):
                        return base_type[:-1].rstrip() + "&"
                    else:
                        return base_type.rstrip("&").rstrip() + "&"

        elif node_type == "subscript_expression":
            argument = arg_node.child_by_field_name("argument")
            if argument:
                base_type = self.get_argument_type(argument)
                base_type = base_type.rstrip("&").rstrip()
                if base_type.endswith("*"):
                    element_type = base_type[:-1].rstrip()
                    return element_type + "&"
                else:
                    return base_type + "&"

        elif node_type == "field_expression":
            return "unknown&"

        return "unknown"

    def add_dummy_nodes(self):
        """Add start and exit dummy nodes to CFG"""
        self.CFG_node_list.append((1, 0, "start_node", "start"))

    def handle_static_initialization_phase(self, node_list):
        """
        Handle static/global initialization phase in C++.

        In C++, static and global variables are initialized before main() starts.
        This function creates the proper control flow:
        - start_node -> first_static_init -> ... -> last_static_init -> main()

        Static initializations that need to be connected:
        1. Static member variable definitions with initializers
           Example: int MyClass::staticVar = 42;
        2. Global variable definitions with initializers
           Example: int globalVar = 10;

        Function definitions are NOT included (they're not executed, just defined).
        """
        static_inits = []

        for key, node in node_list.items():
            if node.type != "declaration":
                continue

            parent = node.parent
            if not parent or parent.type != "translation_unit":
                continue

            has_initializer = False
            for child in node.named_children:
                if child.type == "init_declarator":
                    has_initializer = True
                    break

            if has_initializer:
                node_index = self.get_index(node)
                line_num = node.start_point[0]
                static_inits.append((line_num, node_index, node))

        static_inits.sort(key=lambda x: x[0])

        main_index = self.records.get("main_function", None)

        if static_inits:
            first_line, first_index, first_node = static_inits[0]
            self.add_edge(1, first_index, "static_init_start")

            for i in range(len(static_inits) - 1):
                current_line, current_index, current_node = static_inits[i]
                next_line, next_index, next_node = static_inits[i + 1]
                self.add_edge(current_index, next_index, "static_init_next")

            if main_index:
                last_line, last_index, last_node = static_inits[-1]
                self.add_edge(last_index, main_index, "static_init_to_main")
        else:
            if main_index:
                self.add_edge(1, main_index, "next")

    def track_namespace_aliases(self, root_node):
        """
        Track namespace alias definitions to resolve qualified identifiers.
        Handles:
        - namespace OI = Outer::Inner;
        - namespace short = very::long::namespace::path;
        """
        if root_node.type == "namespace_alias_definition":
            alias_name = None
            for child in root_node.children:
                if child.type == "namespace_identifier":
                    alias_name = child.text.decode("utf-8")
                    break

            actual_namespace = None
            for child in root_node.children:
                if child.type == "nested_namespace_specifier":
                    actual_namespace = child.text.decode("utf-8")
                    break
                elif (
                    child.type == "namespace_identifier"
                    and alias_name != child.text.decode("utf-8")
                ):
                    actual_namespace = child.text.decode("utf-8")
                    break

            if alias_name and actual_namespace:
                self.records["namespace_aliases"][alias_name] = actual_namespace

        for child in root_node.children:
            self.track_namespace_aliases(child)

    def track_function_pointer_assignments(self, root_node):
        """
        Track assignments to function pointers.
        Handles:
        - Simple assignments: mathFunc = add;
        - Address-of assignments: greetFunc = &greet;
        - Array initializers: int (*ops[2])(int, int) = {add, multiply};
        """
        if root_node.type == "assignment_expression":
            left = root_node.child_by_field_name("left")
            right = root_node.child_by_field_name("right")

            if left and right:
                pointer_var = None
                function_name = None

                if left.type == "identifier":
                    pointer_var = left.text.decode("utf-8")

                if right.type == "identifier":
                    function_name = right.text.decode("utf-8")
                elif right.type == "pointer_expression":
                    arg = right.child_by_field_name("argument")
                    if arg and arg.type == "identifier":
                        function_name = arg.text.decode("utf-8")

                if pointer_var and function_name:
                    if pointer_var not in self.records["function_pointer_assignments"]:
                        self.records["function_pointer_assignments"][pointer_var] = []
                    if (
                        function_name
                        not in self.records["function_pointer_assignments"][pointer_var]
                    ):
                        self.records["function_pointer_assignments"][
                            pointer_var
                        ].append(function_name)

        elif root_node.type == "init_declarator":
            declarator = root_node.child_by_field_name("declarator")
            value = root_node.child_by_field_name("value")

            if declarator and value and value.type == "initializer_list":
                array_name = None

                def find_array_declarator(node):
                    if node is None:
                        return None
                    if node.type == "array_declarator":
                        for child in node.named_children:
                            if child.type == "identifier":
                                return child.text.decode("utf-8")
                    for child in node.named_children:
                        result = find_array_declarator(child)
                        if result:
                            return result
                    return None

                array_name = find_array_declarator(declarator)

                if array_name:
                    for child in value.named_children:
                        if child.type == "identifier":
                            function_name = child.text.decode("utf-8")
                            if (
                                array_name
                                not in self.records["function_pointer_assignments"]
                            ):
                                self.records["function_pointer_assignments"][
                                    array_name
                                ] = []
                            if (
                                function_name
                                not in self.records["function_pointer_assignments"][
                                    array_name
                                ]
                            ):
                                self.records["function_pointer_assignments"][
                                    array_name
                                ].append(function_name)

        for child in root_node.children:
            self.track_function_pointer_assignments(child)

    def add_function_call_edges(self):
        """
        Add edges for function calls and returns.
        Handles:
        - Regular function calls
        - Member function calls
        - Constructor calls
        - Virtual function dispatch
        """
        index_to_key = {v: k for k, v in self.index.items()}

        for (func_name, signature), call_list in self.records["function_calls"].items():
            for ((class_name, fn_name), fn_sig), fn_id in self.records[
                "function_list"
            ].items():
                if fn_name == func_name and self.signatures_match(signature, fn_sig):
                    for call_id, parent_id in call_list:
                        self.map_function_parameters_to_lambdas(fn_id, call_id)

                        self.add_edge(parent_id, fn_id, f"function_call|{call_id}")

                        has_noreturn = False
                        if fn_id in self.records.get("attributed_functions", {}):
                            attributes = self.records["attributed_functions"][fn_id]
                            has_noreturn = "noreturn" in attributes

                        if has_noreturn:
                            continue

                        if (
                            self.records.get("return_statement_map")
                            and fn_id in self.records["return_statement_map"]
                        ):
                            for return_id in self.records["return_statement_map"][
                                fn_id
                            ]:
                                is_implicit_return = (
                                    self.records.get("implicit_return_map")
                                    and return_id
                                    in self.records["implicit_return_map"].values()
                                )

                                parent_key = index_to_key.get(parent_id)
                                if not parent_key:
                                    continue
                                parent_node = self.node_list.get(parent_key)
                                if not parent_node:
                                    continue

                                return_key = index_to_key.get(return_id)
                                return_node = (
                                    self.node_list.get(return_key)
                                    if return_key
                                    else None
                                )
                                is_throw_statement = (
                                    return_node
                                    and return_node.type == "throw_statement"
                                )

                                if is_throw_statement:
                                    caller_parent = parent_node.parent
                                    found_caller_try = False
                                    while caller_parent is not None:
                                        if caller_parent.type == "try_statement":
                                            thrown_type = self.extract_thrown_type(
                                                return_node
                                            )

                                            for child in caller_parent.children:
                                                if child.type == "catch_clause":
                                                    if (
                                                        child.start_point,
                                                        child.end_point,
                                                        child.type,
                                                    ) in self.node_list:
                                                        catch_type = self.extract_catch_parameter_type(
                                                            child
                                                        )

                                                        if self.exception_type_matches(
                                                            thrown_type, catch_type
                                                        ):
                                                            catch_index = (
                                                                self.get_index(child)
                                                            )
                                                            self.add_edge(
                                                                return_id,
                                                                catch_index,
                                                                "function_return",
                                                            )
                                                            found_caller_try = True
                                                            break

                                            break
                                        caller_parent = caller_parent.parent

                                    if found_caller_try:
                                        continue
                                    else:
                                        continue

                                return_target = None

                                return_target = parent_id

                                if parent_id != fn_id and return_target:
                                    return_key = index_to_key.get(return_id)

                                    if is_implicit_return:
                                        self.add_edge(
                                            return_id, return_target, "function_return"
                                        )
                                    elif not return_key:
                                        fn_key = index_to_key.get(fn_id)
                                        fn_node = (
                                            self.node_list.get(fn_key)
                                            if fn_key
                                            else None
                                        )

                                        if fn_node:
                                            last_stmt = self.get_last_statement_in_function_body(
                                                fn_node, self.node_list
                                            )
                                            if last_stmt:
                                                last_stmt_id, _ = last_stmt
                                                self.add_edge(
                                                    last_stmt_id,
                                                    return_target,
                                                    "function_return",
                                                )
                                            else:
                                                self.add_edge(
                                                    fn_id,
                                                    return_target,
                                                    "function_return",
                                                )
                                    else:
                                        return_node = self.node_list.get(return_key)
                                        if return_node:
                                            parent_func = self.get_containing_function(
                                                parent_node
                                            )
                                            return_func = self.get_containing_function(
                                                return_node
                                            )
                                            if (
                                                parent_func != return_func
                                                or parent_func is None
                                            ):
                                                self.add_edge(
                                                    return_id,
                                                    return_target,
                                                    "function_return",
                                                )

        for (method_name, signature), call_list in self.records["method_calls"].items():
            for call_id, parent_id, object_name in call_list:
                template_instantiation = None
                if object_name and object_name in self.template_instantiations:
                    template_instantiation = self.template_instantiations[object_name]

                object_class = None
                if object_name:
                    for idx, var_name in self.declaration.items():
                        if var_name == object_name:
                            data_type = self.symbol_table.get("data_type", {}).get(idx)
                            if data_type:
                                object_class = data_type
                                object_class = (
                                    object_class.replace("*", "")
                                    .replace("&", "")
                                    .replace("class ", "")
                                    .replace("struct ", "")
                                    .strip()
                                )
                                break

                known_concrete_type = None
                known_concrete_namespace = None
                if object_name and object_name in self.pointer_targets:
                    known_concrete_type, known_concrete_namespace = (
                        self.pointer_targets[object_name]
                    )

                if (
                    object_name
                    and not known_concrete_type
                    and object_name in self.runtime_types
                ):
                    known_concrete_type = self.runtime_types[object_name]

                matching_functions = []

                derived_classes = set()
                derived_class_namespaces = set()
                if object_class:
                    derived_classes = self.get_all_derived_classes(object_class)
                    for derived_class in derived_classes:
                        namespaces = self.get_class_namespaces(derived_class)
                        derived_class_namespaces.update(namespaces)

                has_derived_implementation = False
                if derived_classes or derived_class_namespaces:
                    for ((ns_or_class, fn_name), fn_sig), fn_id in self.records[
                        "function_list"
                    ].items():
                        name_matches = fn_name == method_name or fn_name.endswith(
                            "::" + method_name
                        )
                        if name_matches and (
                            ns_or_class in derived_classes
                            or ns_or_class in derived_class_namespaces
                        ):
                            has_derived_implementation = True
                            break

                allowed_identifiers = {object_class} if object_class else set()
                if has_derived_implementation and object_class:
                    if known_concrete_type:
                        allowed_identifiers = set()
                        allowed_identifiers.add(known_concrete_type)
                        if known_concrete_namespace:
                            allowed_identifiers.add(known_concrete_namespace)
                    else:
                        allowed_identifiers.update(derived_classes)
                        allowed_identifiers.update(derived_class_namespaces)
                    allowed_identifiers.discard(None)

                for ((ns_or_class, fn_name), fn_sig), fn_id in self.records[
                    "function_list"
                ].items():
                    name_matches = fn_name == method_name or fn_name.endswith(
                        "::" + method_name
                    )

                    if object_class and ns_or_class not in allowed_identifiers:
                        continue

                    if name_matches and self.signatures_match(signature, fn_sig):
                        matching_functions.append((fn_id, ns_or_class))

                target_functions = []

                if template_instantiation:
                    base_class, template_args, _ = template_instantiation
                    resolved_fn_id = self.resolve_template_specialization(
                        base_class, template_args, method_name
                    )

                    if resolved_fn_id:
                        target_functions.append((resolved_fn_id, False))
                    else:
                        for fn_id, class_name in matching_functions:
                            target_functions.append((fn_id, False))
                else:
                    is_virtual_method = False

                    for fn_id, _ in matching_functions:
                        if fn_id in self.records["virtual_functions"]:
                            is_virtual_method = True
                            break

                    non_template_matches = []
                    for fn_id, class_name in matching_functions:
                        fn_key = index_to_key.get(fn_id)
                        if fn_key:
                            fn_node = self.node_list.get(fn_key)
                            if fn_node:
                                class_node = self.get_containing_class(fn_node)
                                if class_node and class_node.parent:
                                    if class_node.parent.type == "template_declaration":
                                        continue
                        non_template_matches.append((fn_id, class_name))

                    if len(non_template_matches) > 1 and is_virtual_method:
                        for fn_id, _ in non_template_matches:
                            target_functions.append((fn_id, True))
                    elif non_template_matches:
                        for fn_id, _ in non_template_matches:
                            target_functions.append((fn_id, False))
                    elif matching_functions:
                        for fn_id, _ in matching_functions:
                            target_functions.append((fn_id, False))

                for fn_id, is_virtual in target_functions:
                    if is_virtual:
                        self.add_edge(parent_id, fn_id, f"virtual_call|{call_id}")
                    else:
                        self.add_edge(parent_id, fn_id, f"method_call|{call_id}")

                    if (
                        self.records.get("return_statement_map")
                        and fn_id in self.records["return_statement_map"]
                    ):
                        parent_key = index_to_key.get(parent_id)
                        if not parent_key:
                            continue
                        parent_node = self.node_list.get(parent_key)
                        if not parent_node:
                            continue

                        return_target = parent_id

                        if return_target and parent_id != fn_id:
                            for return_id in self.records["return_statement_map"][
                                fn_id
                            ]:
                                is_implicit_return = (
                                    self.records.get("implicit_return_map")
                                    and return_id
                                    in self.records["implicit_return_map"].values()
                                )

                                return_key = index_to_key.get(return_id)
                                return_node = (
                                    self.node_list.get(return_key)
                                    if return_key
                                    else None
                                )
                                is_throw_statement = (
                                    return_node
                                    and return_node.type == "throw_statement"
                                )

                                if is_throw_statement:
                                    caller_parent = parent_node.parent
                                    found_caller_try = False
                                    while caller_parent is not None:
                                        if caller_parent.type == "try_statement":
                                            thrown_type = self.extract_thrown_type(
                                                return_node
                                            )

                                            for child in caller_parent.children:
                                                if child.type == "catch_clause":
                                                    if (
                                                        child.start_point,
                                                        child.end_point,
                                                        child.type,
                                                    ) in self.node_list:
                                                        catch_type = self.extract_catch_parameter_type(
                                                            child
                                                        )

                                                        if self.exception_type_matches(
                                                            thrown_type, catch_type
                                                        ):
                                                            catch_index = (
                                                                self.get_index(child)
                                                            )
                                                            self.add_edge(
                                                                return_id,
                                                                catch_index,
                                                                "method_return",
                                                            )
                                                            found_caller_try = True
                                                            break

                                            break
                                        caller_parent = caller_parent.parent

                                    if found_caller_try:
                                        continue
                                    else:
                                        continue

                                if is_implicit_return:
                                    if return_target:
                                        self.add_edge(
                                            return_id, return_target, "method_return"
                                        )
                                else:
                                    return_key = index_to_key.get(return_id)
                                    if return_key:
                                        return_node = self.node_list.get(return_key)
                                        if return_node:
                                            parent_func = self.get_containing_function(
                                                parent_node
                                            )
                                            return_func = self.get_containing_function(
                                                return_node
                                            )
                                            if (
                                                parent_func != return_func
                                                or parent_func is None
                                            ):
                                                self.add_edge(
                                                    return_id,
                                                    return_target,
                                                    "method_return",
                                                )

        for (class_name, method_name, signature), call_list in self.records[
            "static_method_calls"
        ].items():
            for ((fn_class_name, fn_name), fn_sig), fn_id in self.records[
                "function_list"
            ].items():
                if (
                    fn_class_name == class_name
                    and fn_name == method_name
                    and self.signatures_match(signature, fn_sig)
                ):
                    for call_id, parent_id in call_list:
                        self.add_edge(parent_id, fn_id, f"static_call|{call_id}")

                        if (
                            self.records.get("return_statement_map")
                            and fn_id in self.records["return_statement_map"]
                        ):
                            for return_id in self.records["return_statement_map"][
                                fn_id
                            ]:
                                is_implicit_return = (
                                    self.records.get("implicit_return_map")
                                    and return_id
                                    in self.records["implicit_return_map"].values()
                                )

                                parent_key = index_to_key.get(parent_id)
                                if not parent_key:
                                    continue
                                parent_node = self.node_list.get(parent_key)
                                if not parent_node:
                                    continue

                                return_key = index_to_key.get(return_id)
                                return_node = (
                                    self.node_list.get(return_key)
                                    if return_key
                                    else None
                                )
                                is_throw_statement = (
                                    return_node
                                    and return_node.type == "throw_statement"
                                )

                                if is_throw_statement:
                                    caller_parent = parent_node.parent
                                    found_caller_try = False
                                    while caller_parent is not None:
                                        if caller_parent.type == "try_statement":
                                            thrown_type = self.extract_thrown_type(
                                                return_node
                                            )

                                            for child in caller_parent.children:
                                                if child.type == "catch_clause":
                                                    if (
                                                        child.start_point,
                                                        child.end_point,
                                                        child.type,
                                                    ) in self.node_list:
                                                        catch_type = self.extract_catch_parameter_type(
                                                            child
                                                        )

                                                        if self.exception_type_matches(
                                                            thrown_type, catch_type
                                                        ):
                                                            catch_index = (
                                                                self.get_index(child)
                                                            )
                                                            self.add_edge(
                                                                return_id,
                                                                catch_index,
                                                                "static_return",
                                                            )
                                                            found_caller_try = True
                                                            break

                                            break
                                        caller_parent = caller_parent.parent

                                    if found_caller_try:
                                        continue
                                    else:
                                        continue

                                return_target = parent_id

                                if parent_id != fn_id and return_target:
                                    return_key = index_to_key.get(return_id)

                                    if is_implicit_return:
                                        self.add_edge(
                                            return_id, return_target, "static_return"
                                        )
                                    elif not return_key:
                                        fn_key = index_to_key.get(fn_id)
                                        fn_node = (
                                            self.node_list.get(fn_key)
                                            if fn_key
                                            else None
                                        )

                                        if fn_node:
                                            last_stmt = self.get_last_statement_in_function_body(
                                                fn_node, self.node_list
                                            )
                                            if last_stmt:
                                                last_stmt_id, _ = last_stmt
                                                self.add_edge(
                                                    last_stmt_id,
                                                    return_target,
                                                    "static_return",
                                                )
                                            else:
                                                self.add_edge(
                                                    fn_id,
                                                    return_target,
                                                    "static_return",
                                                )
                                    else:
                                        return_node = self.node_list.get(return_key)
                                        if return_node:
                                            parent_func = self.get_containing_function(
                                                parent_node
                                            )
                                            return_func = self.get_containing_function(
                                                return_node
                                            )
                                            if (
                                                parent_func != return_func
                                                or parent_func is None
                                            ):
                                                self.add_edge(
                                                    return_id,
                                                    return_target,
                                                    "static_return",
                                                )

        for (operator_symbol, is_member), call_list in self.records[
            "operator_calls"
        ].items():
            operator_to_function_name = {
                "+": "operator+",
                "-": "operator-",
                "*": "operator*",
                "/": "operator/",
                "%": "operator%",
                "==": "operator==",
                "!=": "operator!=",
                "<": "operator<",
                ">": "operator>",
                "<=": "operator<=",
                ">=": "operator>=",
                "<<": "operator<<",
                ">>": "operator>>",
                "&": "operator&",
                "|": "operator|",
                "^": "operator^",
                "&&": "operator&&",
                "||": "operator||",
                "=": "operator=",
                "++_prefix": "operator++",
                "++_postfix": "operator++",
                "--_prefix": "operator--",
                "--_postfix": "operator--",
            }

            operator_func_name = operator_to_function_name.get(operator_symbol)
            if not operator_func_name:
                continue

            for call_id, parent_id, operand_type in call_list:
                matching_functions = []

                for ((fn_class_name, fn_name), fn_sig), fn_id in self.records[
                    "function_list"
                ].items():
                    if fn_name == operator_func_name:
                        if is_member:
                            if operand_type and fn_class_name == operand_type:
                                if operator_symbol in ["++_prefix", "--_prefix"]:
                                    if fn_sig == () or fn_sig == ("",):
                                        matching_functions.append(fn_id)
                                elif operator_symbol in ["++_postfix", "--_postfix"]:
                                    if fn_sig == ("int",) or "int" in str(fn_sig):
                                        matching_functions.append(fn_id)
                                else:
                                    matching_functions.append(fn_id)
                        else:
                            if operand_type and fn_sig:
                                type_match = False
                                for param_type in fn_sig:
                                    param_simple = (
                                        param_type.replace("const", "")
                                        .replace("&", "")
                                        .replace("*", "")
                                        .strip()
                                    )
                                    if (
                                        operand_type in param_simple
                                        or param_simple in operand_type
                                    ):
                                        type_match = True
                                        break
                                if type_match:
                                    matching_functions.append(fn_id)
                            elif not operand_type:
                                matching_functions.append(fn_id)

                for fn_id in matching_functions:
                    edge_label = f"operator_call|{call_id}"
                    if operator_symbol.startswith("++") or operator_symbol.startswith(
                        "--"
                    ):
                        edge_label = (
                            f"{operator_symbol.split('_')[1]}_increment_call|{call_id}"
                        )
                    self.add_edge(parent_id, fn_id, edge_label)

                    if (
                        self.records.get("return_statement_map")
                        and fn_id in self.records["return_statement_map"]
                    ):
                        for return_id in self.records["return_statement_map"][fn_id]:
                            is_implicit_return = (
                                self.records.get("implicit_return_map")
                                and return_id
                                in self.records["implicit_return_map"].values()
                            )

                            parent_key = index_to_key.get(parent_id)
                            if not parent_key:
                                continue
                            parent_node = self.node_list.get(parent_key)
                            if not parent_node:
                                continue

                            return_target = parent_id

                            if parent_id != fn_id and return_target:
                                return_key = index_to_key.get(return_id)

                                if is_implicit_return or not return_key:
                                    fn_key = index_to_key.get(fn_id)
                                    fn_node = (
                                        self.node_list.get(fn_key) if fn_key else None
                                    )

                                    if fn_node:
                                        last_stmt = (
                                            self.get_last_statement_in_function_body(
                                                fn_node, self.node_list
                                            )
                                        )
                                        if last_stmt:
                                            last_stmt_id, _ = last_stmt
                                            self.add_edge(
                                                last_stmt_id,
                                                return_target,
                                                "operator_return",
                                            )
                                        else:
                                            self.add_edge(
                                                fn_id, return_target, "operator_return"
                                            )
                                else:
                                    return_node = self.node_list.get(return_key)
                                    if return_node:
                                        parent_func = self.get_containing_function(
                                            parent_node
                                        )
                                        return_func = self.get_containing_function(
                                            return_node
                                        )
                                        if (
                                            parent_func != return_func
                                            or parent_func is None
                                        ):
                                            self.add_edge(
                                                return_id,
                                                return_target,
                                                "operator_return",
                                            )

        for ((namespace_prefix, class_name), signature), call_list in self.records[
            "constructor_calls"
        ].items():
            found_constructor = False
            for ((fn_class_name, fn_name), fn_sig), fn_id in self.records[
                "function_list"
            ].items():
                is_constructor_match = False
                if namespace_prefix is None:
                    is_constructor_match = (
                        fn_class_name == class_name and fn_name == class_name
                    )
                else:
                    is_constructor_match = (
                        fn_class_name == namespace_prefix and fn_name == class_name
                    )
                if is_constructor_match:
                    sig_match = False

                    if fn_sig == signature:
                        sig_match = True
                    elif (
                        signature == (f"const {class_name}&",)
                        and len(fn_sig) == 1
                        and class_name in fn_sig[0]
                    ):
                        sig_match = True
                    elif (
                        signature == (f"{class_name}&&",)
                        and len(fn_sig) == 1
                        and class_name in fn_sig[0]
                    ):
                        sig_match = True
                    elif len(signature) <= len(fn_sig):
                        all_match = True
                        for i, call_param in enumerate(signature):
                            if i < len(fn_sig):
                                fn_param = fn_sig[i]
                                fn_param_simple = (
                                    fn_param.replace("const", "")
                                    .replace("&", "")
                                    .replace("*", "")
                                    .strip()
                                )
                                call_param_simple = (
                                    call_param.replace("const", "")
                                    .replace("&", "")
                                    .replace("*", "")
                                    .strip()
                                )

                                if call_param_simple == "unknown":
                                    continue

                                numeric_types = [
                                    "int",
                                    "double",
                                    "float",
                                    "long",
                                    "short",
                                    "char",
                                    "size_t",
                                    "uint",
                                    "int8",
                                    "int16",
                                    "int32",
                                    "int64",
                                    "uint8",
                                    "uint16",
                                    "uint32",
                                    "uint64",
                                    "ptrdiff",
                                ]
                                fn_is_numeric = any(
                                    nt in fn_param_simple for nt in numeric_types
                                )
                                call_is_numeric = any(
                                    nt in call_param_simple for nt in numeric_types
                                )

                                if fn_is_numeric and call_is_numeric:
                                    continue

                                if call_param == "const char*" and (
                                    "string" in fn_param_simple.lower()
                                ):
                                    continue

                                if fn_param_simple != call_param_simple:
                                    all_match = False
                                    break
                        if all_match:
                            sig_match = True

                    if sig_match:
                        found_constructor = True

                        fn_key = index_to_key.get(fn_id)
                        fn_node = self.node_list.get(fn_key) if fn_key else None

                        base_classes = []
                        if class_name in self.records.get("extends", {}):
                            base_classes = self.records["extends"][class_name]
                            if not isinstance(base_classes, list):
                                base_classes = [base_classes]

                        if not base_classes and fn_node:
                            containing_class = self.get_containing_class(fn_node)
                            if containing_class:
                                base_classes = list(
                                    self.get_base_classes(containing_class)
                                )

                        explicit_base_calls = set()
                        if fn_node and base_classes:
                            explicit_base_calls = (
                                self.get_explicit_base_constructors_in_initializer_list(
                                    fn_node, set(base_classes)
                                )
                            )

                        implicit_base_constructors = []
                        for base_class in base_classes:
                            if base_class not in explicit_base_calls:
                                base_constructor_id = None
                                base_constructor_key = ((base_class, base_class), ())
                                if (
                                    base_constructor_key
                                    in self.records["function_list"]
                                ):
                                    base_constructor_id = self.records["function_list"][
                                        base_constructor_key
                                    ]
                                else:
                                    for (
                                        (bc_class, bc_name),
                                        bc_sig,
                                    ), bc_id in self.records["function_list"].items():
                                        if (
                                            bc_class == base_class
                                            and bc_name == base_class
                                        ):
                                            if bc_sig == ():
                                                base_constructor_id = bc_id
                                                break
                                            elif base_constructor_id is None:
                                                base_constructor_id = bc_id

                                if base_constructor_id:
                                    implicit_base_constructors.append(
                                        (base_class, base_constructor_id)
                                    )

                        for call_id, parent_id in call_list:
                            if implicit_base_constructors:
                                prev_target = parent_id

                                for (
                                    base_class,
                                    base_constructor_id,
                                ) in implicit_base_constructors:
                                    if prev_target == parent_id:
                                        self.add_edge(
                                            parent_id,
                                            base_constructor_id,
                                            f"implicit_base_constructor_call|{call_id}",
                                        )
                                    else:
                                        self.add_edge(
                                            prev_target,
                                            base_constructor_id,
                                            "implicit_base_constructor_call",
                                        )

                                    base_fn_key = index_to_key.get(base_constructor_id)
                                    base_fn_node = (
                                        self.node_list.get(base_fn_key)
                                        if base_fn_key
                                        else None
                                    )
                                    if base_fn_node:
                                        base_last_stmt = (
                                            self.get_last_statement_in_function_body(
                                                base_fn_node, self.node_list
                                            )
                                        )
                                        if base_last_stmt:
                                            prev_target = base_last_stmt[0]
                                        else:
                                            prev_target = base_constructor_id
                                    else:
                                        prev_target = base_constructor_id

                                if prev_target != parent_id:
                                    self.add_edge(
                                        prev_target,
                                        fn_id,
                                        "base_constructor_return_to_derived",
                                    )
                                else:
                                    self.add_edge(
                                        parent_id, fn_id, f"constructor_call|{call_id}"
                                    )
                            else:
                                self.add_edge(
                                    parent_id, fn_id, f"constructor_call|{call_id}"
                                )

                        if fn_node:
                            for call_id, parent_id in call_list:
                                parent_key = index_to_key.get(parent_id)
                                if not parent_key:
                                    continue
                                parent_node = self.node_list.get(parent_key)
                                if not parent_node:
                                    continue

                                is_base_constructor_call = False
                                if parent_node.type == "function_definition":
                                    for pchild in parent_node.children:
                                        if pchild.type == "field_initializer_list":
                                            is_base_constructor_call = True
                                            break

                                if is_base_constructor_call:
                                    first_line = self.edge_first_line(
                                        parent_node, self.node_list
                                    )
                                    if first_line:
                                        return_target = first_line[0]
                                    else:
                                        return_target = None
                                else:
                                    return_target = parent_id

                                if return_target and parent_id != fn_id:
                                    last_stmt = (
                                        self.get_last_statement_in_function_body(
                                            fn_node, self.node_list
                                        )
                                    )
                                    if last_stmt:
                                        last_stmt_id, _ = last_stmt
                                        if is_base_constructor_call:
                                            self.add_edge(
                                                last_stmt_id,
                                                return_target,
                                                "base_constructor_return",
                                            )
                                        else:
                                            self.add_edge(
                                                last_stmt_id,
                                                return_target,
                                                "constructor_return",
                                            )
                                    else:
                                        if is_base_constructor_call:
                                            self.add_edge(
                                                fn_id,
                                                return_target,
                                                "base_constructor_return",
                                            )
                                        else:
                                            self.add_edge(
                                                fn_id,
                                                return_target,
                                                "constructor_return",
                                            )

                        if (
                            self.records.get("return_statement_map")
                            and fn_id in self.records["return_statement_map"]
                        ):
                            for return_id in self.records["return_statement_map"][
                                fn_id
                            ]:
                                is_implicit_return = (
                                    self.records.get("implicit_return_map")
                                    and return_id
                                    in self.records["implicit_return_map"].values()
                                )

                                for call_id, parent_id in call_list:
                                    parent_key = index_to_key.get(parent_id)
                                    if not parent_key:
                                        continue
                                    parent_node = self.node_list.get(parent_key)
                                    if not parent_node:
                                        continue

                                    is_base_constructor_call = False
                                    if parent_node.type == "function_definition":
                                        for pchild in parent_node.children:
                                            if pchild.type == "field_initializer_list":
                                                is_base_constructor_call = True
                                                break

                                    if is_base_constructor_call:
                                        first_line = self.edge_first_line(
                                            parent_node, self.node_list
                                        )
                                        if first_line:
                                            return_target = first_line[0]
                                        else:
                                            if parent_id in self.records.get(
                                                "implicit_return_map", {}
                                            ):
                                                return_target = self.records[
                                                    "implicit_return_map"
                                                ][parent_id]
                                            else:
                                                return_target = None
                                    else:
                                        return_target = parent_id

                                    if is_implicit_return:
                                        fn_key = index_to_key.get(fn_id)
                                        fn_node = (
                                            self.node_list.get(fn_key)
                                            if fn_key
                                            else None
                                        )

                                        if fn_node and return_target:
                                            last_stmt = self.get_last_statement_in_function_body(
                                                fn_node, self.node_list
                                            )
                                            if last_stmt:
                                                last_stmt_id, _ = last_stmt
                                                if parent_id != fn_id:
                                                    self.add_edge(
                                                        last_stmt_id,
                                                        return_target,
                                                        "constructor_return",
                                                    )
                                                elif is_base_constructor_call:
                                                    self.add_edge(
                                                        last_stmt_id,
                                                        return_target,
                                                        "base_constructor_return",
                                                    )
                                            else:
                                                if parent_id != fn_id:
                                                    self.add_edge(
                                                        fn_id,
                                                        return_target,
                                                        "constructor_return",
                                                    )
                                                elif is_base_constructor_call:
                                                    self.add_edge(
                                                        fn_id,
                                                        return_target,
                                                        "base_constructor_return",
                                                    )
                                    else:
                                        if parent_id != fn_id and return_target:
                                            return_key = index_to_key.get(return_id)

                                            if return_key:
                                                return_node = self.node_list.get(
                                                    return_key
                                                )

                                                if return_node:
                                                    parent_func = (
                                                        self.get_containing_function(
                                                            parent_node
                                                        )
                                                    )
                                                    return_func = (
                                                        self.get_containing_function(
                                                            return_node
                                                        )
                                                    )
                                                    if (
                                                        parent_func != return_func
                                                        or parent_func is None
                                                    ):
                                                        self.add_edge(
                                                            return_id,
                                                            return_target,
                                                            "constructor_return",
                                                        )
                                        elif is_base_constructor_call and return_target:
                                            self.add_edge(
                                                return_id,
                                                return_target,
                                                "base_constructor_return",
                                            )

            if not found_constructor and signature == ():
                synthetic_constructor_id = self.get_new_synthetic_index()
                synthetic_label = f"implicit_default_constructor_{class_name}"

                self.CFG_node_list.append(
                    (
                        synthetic_constructor_id,
                        0,
                        synthetic_label,
                        "synthetic_constructor",
                    )
                )

                key = ((class_name, class_name), ())
                self.records["function_list"][key] = synthetic_constructor_id

                base_classes = []
                if "extends" in self.records and class_name in self.records["extends"]:
                    base_classes = self.records["extends"][class_name]
                    if not isinstance(base_classes, list):
                        base_classes = [base_classes]

                for call_id, parent_id in call_list:
                    self.add_edge(
                        parent_id,
                        synthetic_constructor_id,
                        f"constructor_call|{call_id}",
                    )

                    if base_classes:
                        for base_class in base_classes:
                            base_constructor_key = ((base_class, base_class), ())
                            if base_constructor_key in self.records["function_list"]:
                                base_constructor_id = self.records["function_list"][
                                    base_constructor_key
                                ]
                                self.add_edge(
                                    synthetic_constructor_id,
                                    base_constructor_id,
                                    "base_constructor_call",
                                )

                                if parent_id and parent_id != 2:
                                    self.add_edge(
                                        base_constructor_id,
                                        parent_id,
                                        "constructor_return",
                                    )
                            else:
                                base_synthetic_id = self.get_new_synthetic_index()
                                base_synthetic_label = (
                                    f"implicit_default_constructor_{base_class}"
                                )
                                self.CFG_node_list.append(
                                    (
                                        base_synthetic_id,
                                        0,
                                        base_synthetic_label,
                                        "synthetic_constructor",
                                    )
                                )
                                self.records["function_list"][
                                    base_constructor_key
                                ] = base_synthetic_id

                                self.add_edge(
                                    synthetic_constructor_id,
                                    base_synthetic_id,
                                    "base_constructor_call",
                                )

                                if parent_id and parent_id != 2:
                                    self.add_edge(
                                        base_synthetic_id,
                                        parent_id,
                                        "constructor_return",
                                    )
                    else:
                        if parent_id and parent_id != 2:
                            self.add_edge(
                                synthetic_constructor_id,
                                parent_id,
                                "constructor_return",
                            )

        if self.records.get("destructor_calls"):
            for class_name, call_list in self.records["destructor_calls"].items():
                import sys

                destructor_chain = []

                derived_destructor_name = f"~{class_name}"
                for ((fn_class_name, fn_name), fn_sig), fn_id in self.records[
                    "function_list"
                ].items():
                    if (
                        fn_name == derived_destructor_name
                        and fn_class_name == class_name
                    ):
                        implicit_ret = self.records.get("implicit_return_map", {}).get(
                            fn_id
                        )
                        destructor_chain.append((class_name, fn_id, implicit_ret))
                        break

                all_destructors = []
                for ((fn_class_name, fn_name), fn_sig), fn_id in self.records[
                    "function_list"
                ].items():
                    if fn_name.startswith("~") and fn_name != derived_destructor_name:
                        if (
                            self.records.get("virtual_functions", {})
                            .get(fn_id, {})
                            .get("is_virtual")
                        ):
                            implicit_ret = self.records.get(
                                "implicit_return_map", {}
                            ).get(fn_id)
                            all_destructors.append(
                                (fn_class_name, fn_id, implicit_ret, fn_name)
                            )

                for fn_class_name, fn_id, implicit_ret, fn_name in all_destructors:
                    destructor_chain.append((fn_class_name, fn_id, implicit_ret))

                for call_id, parent_id in call_list:
                    parent_key = index_to_key.get(parent_id)
                    if not parent_key:
                        continue
                    parent_node = self.node_list.get(parent_key)
                    if not parent_node:
                        continue

                    next_index, next_node = self.get_next_index(
                        parent_node, self.node_list
                    )
                    final_return_target = next_index if next_index != 2 else None

                    if destructor_chain:
                        first_class, first_fn_id, first_implicit_ret = destructor_chain[
                            0
                        ]
                        self.add_edge(
                            parent_id, first_fn_id, f"destructor_call|{call_id}"
                        )

                        for i in range(len(destructor_chain)):
                            curr_class, curr_fn_id, curr_implicit_ret = (
                                destructor_chain[i]
                            )

                            curr_fn_key = index_to_key.get(curr_fn_id)
                            curr_fn_node = (
                                self.node_list.get(curr_fn_key) if curr_fn_key else None
                            )

                            if i < len(destructor_chain) - 1:
                                next_class, next_fn_id, next_implicit_ret = (
                                    destructor_chain[i + 1]
                                )
                                return_target = next_fn_id
                                edge_label = "destructor_chain"
                            else:
                                return_target = final_return_target
                                edge_label = "destructor_return"

                            if return_target and curr_fn_node:
                                last_stmt = self.get_last_statement_in_function_body(
                                    curr_fn_node, self.node_list
                                )

                                if last_stmt:
                                    last_stmt_id, last_stmt_node = last_stmt
                                    self.add_edge(
                                        last_stmt_id, return_target, edge_label
                                    )
                                else:
                                    self.add_edge(curr_fn_id, return_target, edge_label)

        for (pointer_var, signature), call_list in self.records[
            "indirect_calls"
        ].items():
            if (
                self.records.get("function_pointer_assignments")
                and pointer_var in self.records["function_pointer_assignments"]
            ):
                function_names = self.records["function_pointer_assignments"][
                    pointer_var
                ]

                for func_name in function_names:
                    for ((class_name, fn_name), fn_sig), fn_id in self.records[
                        "function_list"
                    ].items():
                        if fn_name == func_name:
                            for call_id, parent_id in call_list:
                                self.add_edge(
                                    parent_id, fn_id, f"function_call|{call_id}"
                                )

                                if (
                                    self.records.get("return_statement_map")
                                    and fn_id in self.records["return_statement_map"]
                                ):
                                    for return_id in self.records[
                                        "return_statement_map"
                                    ][fn_id]:
                                        is_implicit_return = (
                                            self.records.get("implicit_return_map")
                                            and return_id
                                            in self.records[
                                                "implicit_return_map"
                                            ].values()
                                        )

                                        parent_key = index_to_key.get(parent_id)
                                        if not parent_key:
                                            continue
                                        parent_node = self.node_list.get(parent_key)
                                        if not parent_node:
                                            continue

                                        return_target = parent_id

                                        if is_implicit_return:
                                            if parent_id != fn_id and return_target:
                                                fn_key = index_to_key.get(fn_id)
                                                fn_node = (
                                                    self.node_list.get(fn_key)
                                                    if fn_key
                                                    else None
                                                )

                                                if fn_node:
                                                    last_stmt = self.get_last_statement_in_function_body(
                                                        fn_node, self.node_list
                                                    )
                                                    if last_stmt:
                                                        last_stmt_id, _ = last_stmt
                                                        self.add_edge(
                                                            last_stmt_id,
                                                            return_target,
                                                            "function_return",
                                                        )
                                                    else:
                                                        self.add_edge(
                                                            fn_id,
                                                            return_target,
                                                            "function_return",
                                                        )
                                        else:
                                            if parent_id != fn_id and return_target:
                                                return_key = index_to_key.get(return_id)

                                                if return_key:
                                                    return_node = self.node_list.get(
                                                        return_key
                                                    )

                                                    if return_node:
                                                        parent_func = self.get_containing_function(
                                                            parent_node
                                                        )
                                                        return_func = self.get_containing_function(
                                                            return_node
                                                        )
                                                        if (
                                                            parent_func != return_func
                                                            or parent_func is None
                                                        ):
                                                            self.add_edge(
                                                                return_id,
                                                                return_target,
                                                                "function_return",
                                                            )

        for (func_name, signature), call_list in list(
            self.records["function_calls"].items()
        ):
            found_direct_match = False
            for ((class_name, fn_name), fn_sig), fn_id in self.records[
                "function_list"
            ].items():
                if fn_name == func_name:
                    found_direct_match = True
                    break

            if (
                not found_direct_match
                and func_name in self.records["function_pointer_assignments"]
            ):
                function_names = self.records["function_pointer_assignments"][func_name]

                for target_func in function_names:
                    for ((class_name, fn_name), fn_sig), fn_id in self.records[
                        "function_list"
                    ].items():
                        if fn_name == target_func:
                            for call_id, parent_id in call_list:
                                self.add_edge(
                                    parent_id, fn_id, f"function_call|{call_id}"
                                )

                                if (
                                    self.records.get("return_statement_map")
                                    and fn_id in self.records["return_statement_map"]
                                ):
                                    for return_id in self.records[
                                        "return_statement_map"
                                    ][fn_id]:
                                        is_implicit_return = (
                                            self.records.get("implicit_return_map")
                                            and return_id
                                            in self.records[
                                                "implicit_return_map"
                                            ].values()
                                        )

                                        parent_key = index_to_key.get(parent_id)
                                        if not parent_key:
                                            continue
                                        parent_node = self.node_list.get(parent_key)
                                        if not parent_node:
                                            continue

                                        return_target = parent_id

                                        if is_implicit_return:
                                            if parent_id != fn_id and return_target:
                                                fn_key = index_to_key.get(fn_id)
                                                fn_node = (
                                                    self.node_list.get(fn_key)
                                                    if fn_key
                                                    else None
                                                )

                                                if fn_node:
                                                    last_stmt = self.get_last_statement_in_function_body(
                                                        fn_node, self.node_list
                                                    )
                                                    if last_stmt:
                                                        last_stmt_id, _ = last_stmt
                                                        self.add_edge(
                                                            last_stmt_id,
                                                            return_target,
                                                            "function_return",
                                                        )
                                                    else:
                                                        self.add_edge(
                                                            fn_id,
                                                            return_target,
                                                            "function_return",
                                                        )
                                        else:
                                            if parent_id != fn_id and return_target:
                                                return_key = index_to_key.get(return_id)

                                                if return_key:
                                                    return_node = self.node_list.get(
                                                        return_key
                                                    )

                                                    if return_node:
                                                        parent_func = self.get_containing_function(
                                                            parent_node
                                                        )
                                                        return_func = self.get_containing_function(
                                                            return_node
                                                        )
                                                        if (
                                                            parent_func != return_func
                                                            or parent_func is None
                                                        ):
                                                            self.add_edge(
                                                                return_id,
                                                                return_target,
                                                                "function_return",
                                                            )

        for (func_name, signature), call_list in self.records["function_calls"].items():
            for call_id, parent_id in call_list:
                parent_key = index_to_key.get(parent_id)
                if not parent_key:
                    continue
                parent_node = self.node_list.get(parent_key)
                if not parent_node:
                    continue

                containing_func = self.get_containing_function(parent_node)
                if not containing_func:
                    continue

                containing_func_key = (
                    containing_func.start_point,
                    containing_func.end_point,
                    containing_func.type,
                )
                if containing_func_key not in self.node_list:
                    continue

                containing_func_id = self.get_index(containing_func)

                param_key = (containing_func_id, func_name)
                if param_key in self.records["function_parameter_to_lambda"]:
                    lambda_var = self.records["function_parameter_to_lambda"][param_key]
                    lambda_key = self.records["lambda_variables"].get(lambda_var)

                    if lambda_key:
                        lambda_node = self.node_list.get(lambda_key)
                        if lambda_node:
                            lambda_body_first_id = self.get_lambda_body_first_stmt(
                                lambda_node, self.node_list
                            )

                            if lambda_body_first_id:
                                self.add_edge(
                                    parent_id, lambda_body_first_id, "lambda_invocation"
                                )

                                lambda_id = self.index[lambda_key]
                                self.add_lambda_return_edges(
                                    lambda_node, lambda_id, parent_id, self.node_list
                                )

        edges_to_remove = []

        for (func_name, signature), call_list in self.records["function_calls"].items():
            for ((class_name, fn_name), fn_sig), fn_id in self.records[
                "function_list"
            ].items():
                if fn_name == func_name and self.signatures_match(signature, fn_sig):
                    has_noreturn = False
                    if fn_id in self.records.get("attributed_functions", {}):
                        attributes = self.records["attributed_functions"][fn_id]
                        has_noreturn = "noreturn" in attributes

                    if has_noreturn:
                        for call_id, parent_id in call_list:
                            for edge in self.CFG_edge_list:
                                if edge[0] == parent_id and edge[2] == "next_line":
                                    edges_to_remove.append(edge)
                                    break

        for edge in edges_to_remove:
            if edge in self.CFG_edge_list:
                self.CFG_edge_list.remove(edge)

    def track_lambda_variables(self, node_list):
        """
        Early pass to identify and track lambda variables.
        This must be called before function_list() so that lambda arguments can be tracked.

        Populates self.records["lambda_variables"]: lambda_var_name -> lambda_node_key
        """
        for lambda_key, statement_node in self.records["lambda_map"].items():
            var_name = self.extract_lambda_variable_name(
                statement_node, self.node_list.get(lambda_key)
            )

            if var_name:
                self.records["lambda_variables"][var_name] = lambda_key

    def track_lambda_arguments(self, call_expression_node, call_index):
        """
        Track when lambda variables are passed as function arguments.
        This enables connecting indirect lambda invocations to lambda bodies.

        Example:
            auto f = []() { ... };
            myFunction(f);  // Track that 'f' is passed to myFunction

        Args:
            call_expression_node: The call_expression AST node
            call_index: The index of this call expression
        """
        args_node = call_expression_node.child_by_field_name("arguments")
        if not args_node:
            return

        arg_index = 0
        for child in args_node.named_children:
            if child.type == "identifier":
                arg_name = child.text.decode("utf-8")
                if arg_name in self.records["lambda_variables"]:
                    key = (call_index, arg_index)
                    self.records["lambda_arguments"][key] = arg_name
                arg_index += 1
            elif child.type == "call_expression":
                arg_index += 1
            else:
                arg_index += 1

    def map_function_parameters_to_lambdas(self, fn_id, call_id):
        """
        Map function parameters to lambda variables when lambdas are passed as arguments.

        Example:
            void myFunction(function<void()> func) { ... }  // fn_id = function definition
            myFunction(message);  // call_id = function call, message is a lambda

        This creates a mapping: (fn_id, "func") -> "message"

        Args:
            fn_id: The function definition node ID
            call_id: The function call node ID
        """
        index_to_key = {v: k for k, v in self.index.items()}
        fn_key = index_to_key.get(fn_id)
        if not fn_key:
            return

        fn_node = self.node_list.get(fn_key)
        if not fn_node or fn_node.type != "function_definition":
            return

        declarator = fn_node.child_by_field_name("declarator")
        if not declarator:
            return

        parameters = declarator.child_by_field_name("parameters")
        if not parameters:
            return

        param_names = []
        for param in parameters.named_children:
            if param.type == "parameter_declaration":
                declarator_child = param.child_by_field_name("declarator")
                if declarator_child:
                    if declarator_child.type == "identifier":
                        param_names.append(declarator_child.text.decode("utf-8"))
                    elif declarator_child.type == "reference_declarator":
                        for child in declarator_child.named_children:
                            if child.type == "identifier":
                                param_names.append(child.text.decode("utf-8"))
                                break

        for arg_index, param_name in enumerate(param_names):
            key = (call_id, arg_index)
            if key in self.records["lambda_arguments"]:
                lambda_var = self.records["lambda_arguments"][key]
                param_key = (fn_id, param_name)
                self.records["function_parameter_to_lambda"][param_key] = lambda_var

    def extract_lambda_variable_name(self, statement_node, lambda_node):
        """
        Extract the variable name that a lambda is assigned to.
        Example: auto f = [...]() { }; => returns "f"

        AST structure:
        declaration  (this is statement_node)
          placeholder_type_specifier (auto)
          init_declarator
            identifier (variable_name)
            lambda_expression
        """
        if statement_node.type == "declaration":
            for decl_child in statement_node.named_children:
                if decl_child.type == "init_declarator":
                    for init_child in decl_child.named_children:
                        if init_child.type == "identifier":
                            return init_child.text.decode("utf-8")
        return None

    def find_lambda_call_sites(self, var_name, definition_node):
        """
        Find all call sites for a lambda variable within the same function.
        Returns list of statement nodes that call the lambda.
        """
        call_sites = []

        containing_function = self.get_containing_function(definition_node)
        if not containing_function:
            return call_sites

        def search_for_calls(node):
            if node.type in self.statement_types["non_control_statement"]:
                for child in node.named_children:
                    if self.is_lambda_call(child, var_name):
                        if node != definition_node:
                            call_sites.append(node)
                        break

            for child in node.named_children:
                search_for_calls(child)

        search_for_calls(containing_function)
        return call_sites

    def is_lambda_call(self, node, var_name):
        """
        Check if a node is a call_expression calling the specified variable.
        Example: var_name() or var_name(args)
        """
        if node.type == "call_expression":
            func = node.child_by_field_name("function")
            if func and func.type == "identifier":
                if func.text.decode("utf-8") == var_name:
                    return True
        for child in node.named_children:
            if self.is_lambda_call(child, var_name):
                return True
        return False

    def get_lambda_body_first_stmt(self, lambda_node, node_list):
        """
        Get the first statement in a lambda's body.
        Returns the node ID of the first statement, or None if not found.
        """
        body = lambda_node.child_by_field_name("body")
        if body and body.type == "compound_statement":
            children = list(body.named_children)
            if children:
                first_stmt = children[0]
                first_stmt_key = (
                    first_stmt.start_point,
                    first_stmt.end_point,
                    first_stmt.type,
                )
                if first_stmt_key in node_list:
                    return self.get_index(first_stmt)
        return None

    def add_lambda_return_edges(self, lambda_node, lambda_id, call_site_id, node_list):
        """
        Add return edges from lambda exit points to the statement after the call site.
        Also removes the automatic next_line edge from call site to prevent bypassing lambda execution.

        Args:
            lambda_node: The lambda_expression node
            lambda_id: The node ID of the lambda_expression
            call_site_id: The node ID of the statement that calls the lambda
            node_list: The node list dictionary
        """
        exit_points = []

        body = lambda_node.child_by_field_name("body")
        if not body or body.type != "compound_statement":
            return

        def find_exit_points(node, in_lambda_body=False):
            node_key = (node.start_point, node.end_point, node.type)

            if node_key in node_list:
                in_lambda_body = True

                if node.type == "return":
                    exit_points.append(node)
                    return

                parent = node.parent
                if parent == body:
                    siblings = list(body.named_children)
                    if siblings and siblings[-1] == node:
                        if node.type != "return":
                            exit_points.append(node)

            if (
                node.type not in ["function_definition", "lambda_expression"]
                or node == lambda_node
            ):
                for child in node.named_children:
                    find_exit_points(child, in_lambda_body)

        find_exit_points(body)

        call_site_node = None
        for key, node in node_list.items():
            if self.index.get(key) == call_site_id:
                call_site_node = node
                break

        if not call_site_node:
            return

        next_index, next_node = self.get_next_index(call_site_node, node_list)

        for exit_node in exit_points:
            exit_key = (exit_node.start_point, exit_node.end_point, exit_node.type)
            if exit_key in node_list:
                exit_id = self.get_index(exit_node)
                if next_index and next_index not in [0, 1, 2]:
                    self.add_edge(exit_id, next_index, "lambda_return")
                elif next_index == 2:
                    func = self.get_containing_function(call_site_node)
                    if func:
                        func_index = self.get_index(func)
                        if func_index in self.records["implicit_return_map"]:
                            implicit_return_id = self.records["implicit_return_map"][
                                func_index
                            ]
                            self.add_edge(exit_id, implicit_return_id, "lambda_return")

    def add_lambda_edges(self):
        """
        Add edges for lambda invocations and returns.

        This function handles two cases:
        1. Immediately-invoked lambdas: [...]() { body }();
        2. Stored lambdas: auto f = [...]() { body }; ... f();

        For each lambda:
        - Creates invocation edges from definition (for case 1) or call sites (for case 2)
        - Creates return edges from lambda exit points back to statements after calls
        """
        for lambda_key, statement_node in self.records["lambda_map"].items():
            lambda_node = self.node_list.get(lambda_key)
            if lambda_node is None:
                continue

            stmt_key = (
                statement_node.start_point,
                statement_node.end_point,
                statement_node.type,
            )
            if stmt_key not in self.node_list:
                continue

            stmt_id = self.get_index(statement_node)
            lambda_id = self.index[lambda_key]

            is_immediately_invoked = False
            if statement_node.type == "expression_statement":
                for child in statement_node.named_children:
                    if child.type == "call_expression":
                        func_child = child.child_by_field_name("function")
                        if func_child and func_child.type == "lambda_expression":
                            if (
                                func_child.start_point,
                                func_child.end_point,
                                func_child.type,
                            ) == lambda_key:
                                is_immediately_invoked = True
                                break

            lambda_body_first_id = self.get_lambda_body_first_stmt(
                lambda_node, self.node_list
            )
            if lambda_body_first_id is None:
                continue

            if is_immediately_invoked:
                self.add_edge(stmt_id, lambda_body_first_id, "lambda_invocation")

                self.add_lambda_return_edges(
                    lambda_node, lambda_id, stmt_id, self.node_list
                )
            else:
                var_name = self.extract_lambda_variable_name(
                    statement_node, lambda_node
                )

                if var_name:
                    if var_name not in self.records["lambda_variables"]:
                        self.records["lambda_variables"][var_name] = lambda_key

                    call_sites = self.find_lambda_call_sites(var_name, statement_node)

                    for call_site_node in call_sites:
                        call_site_key = (
                            call_site_node.start_point,
                            call_site_node.end_point,
                            call_site_node.type,
                        )
                        if call_site_key in self.node_list:
                            call_site_id = self.get_index(call_site_node)

                            self.add_edge(
                                call_site_id, lambda_body_first_id, "lambda_invocation"
                            )

                            self.add_lambda_return_edges(
                                lambda_node, lambda_id, call_site_id, self.node_list
                            )

    def CFG_cpp(self):
        """
        Main CFG construction function for C++.
        Returns (CFG_node_list, CFG_edge_list)

        STEP 1: Extract statement nodes from AST
        STEP 2: Create initial sequential edges
        STEP 3: Create basic blocks
        STEP 4: Build function call map
        STEP 5: Add dummy nodes
        STEP 6: Add control flow edges
        STEP 7: Add function call edges
        STEP 8: Add lambda edges
        STEP 9: Return results
        """

        root_node, node_list, graph_node_list, records = cpp_nodes.get_nodes(
            root_node=self.root_node,
            node_list={},
            graph_node_list=[],
            index=self.index,
            records=self.records,
        )

        self.node_list = node_list
        self.CFG_node_list = graph_node_list
        self.records = records

        self.register_template_specializations(node_list)

        for key, node in node_list.items():
            if node.type in self.statement_types["non_control_statement"]:
                if node.type == "lambda_expression":
                    continue

                if self.is_last_in_control_block(node):
                    continue

                if node.type not in [
                    "field_declaration",
                    "access_specifier",
                ] and cpp_nodes.has_inner_definition(node):
                    continue

                parent = node.parent
                if parent and parent.type == "field_declaration_list":
                    continue

                if parent and parent.type == "declaration_list":
                    grandparent = parent.parent if parent else None
                    if grandparent and grandparent.type == "namespace_definition":
                        continue

                if parent and parent.type == "translation_unit":
                    continue

                if node.type == "attributed_statement":
                    attributes = self.extract_attributes_from_node(node)
                    if "fallthrough" in attributes:
                        parent_case = node.parent
                        while parent_case and parent_case.type != "case_statement":
                            parent_case = parent_case.parent

                        next_case = None
                        if parent_case:
                            sibling = parent_case.next_sibling
                            while sibling:
                                if sibling.type == "case_statement":
                                    next_case = sibling
                                    break
                                sibling = sibling.next_sibling

                        if next_case:
                            for child in next_case.named_children:
                                if child.type in self.statement_types["node_list_type"]:
                                    if (
                                        child.start_point,
                                        child.end_point,
                                        child.type,
                                    ) in node_list:
                                        current_index = self.get_index(node)
                                        first_stmt_index = self.get_index(child)
                                        self.add_edge(
                                            current_index,
                                            first_stmt_index,
                                            "fallthrough",
                                        )
                                        break
                            continue

                next_index, next_node = self.get_next_index(node, node_list)

                if next_index != 2 and next_node is not None:
                    next_parent = next_node.parent if next_node else None
                    if next_parent and next_parent.type == "field_declaration_list":
                        continue

                    if next_parent and next_parent.type == "declaration_list":
                        next_grandparent = next_parent.parent if next_parent else None
                        if (
                            next_grandparent
                            and next_grandparent.type == "namespace_definition"
                        ):
                            continue

                    if next_parent and next_parent.type == "translation_unit":
                        continue

                    current_index = self.get_index(node)
                    self.add_edge(current_index, next_index, "next_line")

        self.get_basic_blocks(self.CFG_node_list, self.CFG_edge_list)
        self.CFG_node_list = self.append_block_index(self.CFG_node_list, self.records)

        self.track_namespace_aliases(self.root_node)

        self.extract_inheritance_info(self.root_node)

        self.track_lambda_variables(node_list)

        self.function_list(self.root_node, node_list)

        self.track_function_pointer_assignments(self.root_node)

        self.add_dummy_nodes()

        self.handle_static_initialization_phase(node_list)

        for key, node in node_list.items():
            current_index = self.get_index(node)

            if node.type == "function_definition":
                if (
                    "main_function" in self.records
                    and self.records["main_function"] == current_index
                ):
                    pass

                attributes = self.extract_attributes_from_node(node)
                if attributes:
                    self.records["attributed_functions"][current_index] = attributes

                first_line = self.edge_first_line(node, node_list)
                has_statements = first_line is not None
                if first_line:
                    first_index, first_node = first_line
                    self.add_edge(current_index, first_index, "first_next_line")

                return_type_node = node.child_by_field_name("type")
                is_void = False
                is_constructor = False
                is_destructor = False
                is_pure_virtual = False

                if return_type_node:
                    return_type_text = return_type_node.text.decode("utf-8")
                    is_void = return_type_text == "void"
                else:
                    declarator = node.child_by_field_name("declarator")
                    if declarator:
                        for child in declarator.named_children:
                            if child.type == "destructor_name":
                                is_destructor = True
                                break
                            elif child.type == "qualified_identifier":
                                qualified_text = child.text.decode("utf-8")
                                if "~" in qualified_text:
                                    is_destructor = True
                                    break
                            elif child.type == "identifier":
                                is_constructor = True
                                break

                has_body = node.child_by_field_name("body") is not None
                for child in node.children:
                    if child.type == "pure_virtual_clause":
                        is_pure_virtual = True
                        break

                should_create_implicit_return = (
                    is_destructor and has_body and not is_pure_virtual
                )

                should_add_last_stmt_as_return = (
                    is_void and has_body and not is_pure_virtual
                )

                if should_create_implicit_return:
                    implicit_return_id = self.get_new_synthetic_index()

                    declarator = node.child_by_field_name("declarator")
                    func_name = "unknown"
                    if declarator:
                        for child in declarator.named_children:
                            if child.type == "identifier":
                                func_name = child.text.decode("utf-8")
                                break
                            elif child.type == "field_identifier":
                                func_name = child.text.decode("utf-8")
                                break
                            elif child.type == "destructor_name":
                                func_name = child.text.decode("utf-8")
                                break
                            elif child.type == "qualified_identifier":
                                func_name = child.text.decode("utf-8")
                                break

                    implicit_return_label = f"implicit_return_{func_name}"
                    self.CFG_node_list.append(
                        (
                            implicit_return_id,
                            0,
                            implicit_return_label,
                            "implicit_return",
                        )
                    )

                    self.records["implicit_return_map"][
                        current_index
                    ] = implicit_return_id

                    if current_index not in self.records["return_statement_map"]:
                        self.records["return_statement_map"][current_index] = []
                    self.records["return_statement_map"][current_index].append(
                        implicit_return_id
                    )

                    has_noreturn = "noreturn" in attributes if attributes else False

                    if not has_noreturn:
                        if not has_statements:
                            self.add_edge(
                                current_index, implicit_return_id, "implicit_return"
                            )
                        else:
                            last_stmt = self.get_last_statement_in_function_body(
                                node, node_list
                            )
                            if last_stmt:
                                last_stmt_id, last_stmt_node = last_stmt
                                compound_control_stmts = [
                                    "if_statement",
                                    "while_statement",
                                    "for_statement",
                                    "for_range_loop",
                                    "do_statement",
                                    "switch_statement",
                                    "try_statement",
                                ]

                                invokes_lambda = self.statement_invokes_lambda(
                                    last_stmt_node
                                )

                                if (
                                    not self.is_jump_statement(last_stmt_node)
                                    and last_stmt_node.type
                                    not in compound_control_stmts
                                    and not invokes_lambda
                                ):
                                    self.add_edge(
                                        last_stmt_id,
                                        implicit_return_id,
                                        "implicit_return",
                                    )

                if should_add_last_stmt_as_return:
                    has_explicit_returns = current_index in self.records.get(
                        "return_statement_map", {}
                    )

                    if not has_explicit_returns:
                        last_stmt = self.get_last_statement_in_function_body(
                            node, node_list
                        )
                        if last_stmt:
                            last_stmt_id, last_stmt_node = last_stmt
                            if (
                                current_index
                                not in self.records["return_statement_map"]
                            ):
                                self.records["return_statement_map"][current_index] = []
                            self.records["return_statement_map"][current_index].append(
                                last_stmt_id
                            )

            elif node.type in ["class_specifier", "struct_specifier"]:
                pass

            elif node.type == "namespace_definition":
                pass

            elif node.type == "if_statement":
                consequence = node.child_by_field_name("consequence")
                if consequence:
                    if consequence.type == "compound_statement":
                        children = list(consequence.named_children)
                        if children:
                            first_stmt = children[0]
                            if (
                                first_stmt.start_point,
                                first_stmt.end_point,
                                first_stmt.type,
                            ) in node_list:
                                self.add_edge(
                                    current_index,
                                    self.get_index(first_stmt),
                                    "pos_next",
                                )
                    else:
                        if (
                            consequence.start_point,
                            consequence.end_point,
                            consequence.type,
                        ) in node_list:
                            self.add_edge(
                                current_index, self.get_index(consequence), "pos_next"
                            )

                    last_line, _ = self.get_block_last_line(node, "consequence")
                    if (
                        last_line
                        and (last_line.start_point, last_line.end_point, last_line.type)
                        in node_list
                    ):
                        if not self.is_jump_statement(last_line):
                            next_index, next_node = self.get_next_index(node, node_list)
                            if next_index != 2:
                                self.add_edge(
                                    self.get_index(last_line), next_index, "next_line"
                                )
                            else:
                                func = self.get_containing_function(node)
                                if func:
                                    func_index = self.get_index(func)
                                    if (
                                        func_index
                                        in self.records["implicit_return_map"]
                                    ):
                                        implicit_return_id = self.records[
                                            "implicit_return_map"
                                        ][func_index]
                                        self.add_edge(
                                            self.get_index(last_line),
                                            implicit_return_id,
                                            "next_line",
                                        )

                alternative = node.child_by_field_name("alternative")
                if alternative:
                    else_body = alternative
                    if alternative.type == "else_clause":
                        else_children = list(alternative.named_children)
                        if else_children:
                            else_body = else_children[0]

                    if else_body.type == "compound_statement":
                        children = list(else_body.named_children)
                        if children:
                            first_stmt = children[0]
                            if (
                                first_stmt.start_point,
                                first_stmt.end_point,
                                first_stmt.type,
                            ) in node_list:
                                self.add_edge(
                                    current_index,
                                    self.get_index(first_stmt),
                                    "neg_next",
                                )
                    elif else_body.type == "if_statement":
                        if (
                            else_body.start_point,
                            else_body.end_point,
                            else_body.type,
                        ) in node_list:
                            self.add_edge(
                                current_index, self.get_index(else_body), "neg_next"
                            )
                    else:
                        if (
                            else_body.start_point,
                            else_body.end_point,
                            else_body.type,
                        ) in node_list:
                            self.add_edge(
                                current_index, self.get_index(else_body), "neg_next"
                            )

                    if alternative.type == "else_clause":
                        if else_body.type == "compound_statement":
                            children = list(else_body.named_children)
                            if children:
                                last_stmt = children[-1]
                                if (
                                    last_stmt.start_point,
                                    last_stmt.end_point,
                                    last_stmt.type,
                                ) in node_list:
                                    if not self.is_jump_statement(last_stmt):
                                        next_index, next_node = self.get_next_index(
                                            node, node_list
                                        )
                                        if next_index != 2:
                                            self.add_edge(
                                                self.get_index(last_stmt),
                                                next_index,
                                                "next_line",
                                            )
                                        else:
                                            func = self.get_containing_function(node)
                                            if func:
                                                func_index = self.get_index(func)
                                                if (
                                                    func_index
                                                    in self.records[
                                                        "implicit_return_map"
                                                    ]
                                                ):
                                                    implicit_return_id = self.records[
                                                        "implicit_return_map"
                                                    ][func_index]
                                                    self.add_edge(
                                                        self.get_index(last_stmt),
                                                        implicit_return_id,
                                                        "next_line",
                                                    )
                        elif else_body.type != "if_statement":
                            if (
                                else_body.start_point,
                                else_body.end_point,
                                else_body.type,
                            ) in node_list:
                                if not self.is_jump_statement(else_body):
                                    next_index, next_node = self.get_next_index(
                                        node, node_list
                                    )
                                    if next_index != 2:
                                        self.add_edge(
                                            self.get_index(else_body),
                                            next_index,
                                            "next_line",
                                        )
                                    else:
                                        func = self.get_containing_function(node)
                                        if func:
                                            func_index = self.get_index(func)
                                            if (
                                                func_index
                                                in self.records["implicit_return_map"]
                                            ):
                                                implicit_return_id = self.records[
                                                    "implicit_return_map"
                                                ][func_index]
                                                self.add_edge(
                                                    self.get_index(else_body),
                                                    implicit_return_id,
                                                    "next_line",
                                                )
                    elif (
                        else_body.type == "compound_statement"
                        or else_body.type != "if_statement"
                    ):
                        last_line, _ = self.get_block_last_line(node, "alternative")
                        if (
                            last_line
                            and (
                                last_line.start_point,
                                last_line.end_point,
                                last_line.type,
                            )
                            in node_list
                        ):
                            if not self.is_jump_statement(last_line):
                                next_index, next_node = self.get_next_index(
                                    node, node_list
                                )
                                if next_index != 2:
                                    self.add_edge(
                                        self.get_index(last_line),
                                        next_index,
                                        "next_line",
                                    )
                                else:
                                    func = self.get_containing_function(node)
                                    if func:
                                        func_index = self.get_index(func)
                                        if (
                                            func_index
                                            in self.records["implicit_return_map"]
                                        ):
                                            implicit_return_id = self.records[
                                                "implicit_return_map"
                                            ][func_index]
                                            self.add_edge(
                                                self.get_index(last_line),
                                                implicit_return_id,
                                                "next_line",
                                            )
                else:
                    next_index, next_node = self.get_next_index(node, node_list)
                    if next_index != 2:
                        self.add_edge(current_index, next_index, "neg_next")
                    else:
                        func = self.get_containing_function(node)
                        if func:
                            func_index = self.get_index(func)
                            if func_index in self.records["implicit_return_map"]:
                                implicit_return_id = self.records[
                                    "implicit_return_map"
                                ][func_index]
                                self.add_edge(
                                    current_index, implicit_return_id, "neg_next"
                                )

            elif node.type == "while_statement":
                body = node.child_by_field_name("body")
                if body:
                    if body.type == "compound_statement":
                        children = list(body.named_children)
                        if children:
                            first_stmt = children[0]
                            if (
                                first_stmt.start_point,
                                first_stmt.end_point,
                                first_stmt.type,
                            ) in node_list:
                                self.add_edge(
                                    current_index,
                                    self.get_index(first_stmt),
                                    "pos_next",
                                )
                    else:
                        if (body.start_point, body.end_point, body.type) in node_list:
                            self.add_edge(
                                current_index, self.get_index(body), "pos_next"
                            )

                    last_line, _ = self.get_block_last_line(node, "body")
                    if (
                        last_line
                        and (last_line.start_point, last_line.end_point, last_line.type)
                        in node_list
                    ):
                        if (
                            not self.is_jump_statement(last_line)
                            and last_line.type != "try_statement"
                        ):
                            self.add_edge(
                                self.get_index(last_line), current_index, "loop_control"
                            )

                next_index, next_node = self.get_next_index(node, node_list)
                if next_index != 2:
                    self.add_edge(current_index, next_index, "neg_next")

            elif node.type == "for_statement":
                body = node.child_by_field_name("body")
                if body:
                    if body.type == "compound_statement":
                        children = list(body.named_children)
                        if children:
                            first_stmt = children[0]
                            if (
                                first_stmt.start_point,
                                first_stmt.end_point,
                                first_stmt.type,
                            ) in node_list:
                                self.add_edge(
                                    current_index,
                                    self.get_index(first_stmt),
                                    "pos_next",
                                )
                    else:
                        if (body.start_point, body.end_point, body.type) in node_list:
                            self.add_edge(
                                current_index, self.get_index(body), "pos_next"
                            )

                    last_line, _ = self.get_block_last_line(node, "body")
                    if (
                        last_line
                        and (last_line.start_point, last_line.end_point, last_line.type)
                        in node_list
                    ):
                        if (
                            not self.is_jump_statement(last_line)
                            and last_line.type != "try_statement"
                        ):
                            self.add_edge(
                                self.get_index(last_line), current_index, "loop_control"
                            )

                next_index, next_node = self.get_next_index(node, node_list)
                if next_index != 2:
                    self.add_edge(current_index, next_index, "neg_next")

                self.add_edge(current_index, current_index, "loop_update")

            elif node.type == "for_range_loop":
                body = node.child_by_field_name("body")
                if body:
                    if body.type == "compound_statement":
                        children = list(body.named_children)
                        if children:
                            first_stmt = children[0]
                            if (
                                first_stmt.start_point,
                                first_stmt.end_point,
                                first_stmt.type,
                            ) in node_list:
                                self.add_edge(
                                    current_index,
                                    self.get_index(first_stmt),
                                    "pos_next",
                                )
                    else:
                        if (body.start_point, body.end_point, body.type) in node_list:
                            self.add_edge(
                                current_index, self.get_index(body), "pos_next"
                            )

                    last_line, _ = self.get_block_last_line(node, "body")
                    if (
                        last_line
                        and (last_line.start_point, last_line.end_point, last_line.type)
                        in node_list
                    ):
                        if (
                            not self.is_jump_statement(last_line)
                            and last_line.type != "try_statement"
                        ):
                            self.add_edge(
                                self.get_index(last_line), current_index, "loop_control"
                            )

                next_index, next_node = self.get_next_index(node, node_list)
                if next_index != 2:
                    self.add_edge(current_index, next_index, "neg_next")

                self.add_edge(current_index, current_index, "loop_update")

            elif node.type == "do_statement":
                body = node.child_by_field_name("body")
                first_stmt_index = None
                if body:
                    if body.type == "compound_statement":
                        children = list(body.named_children)
                        if children:
                            first_stmt = children[0]
                            if (
                                first_stmt.start_point,
                                first_stmt.end_point,
                                first_stmt.type,
                            ) in node_list:
                                first_stmt_index = self.get_index(first_stmt)
                                self.add_edge(
                                    current_index, first_stmt_index, "first_next_line"
                                )
                    else:
                        if (body.start_point, body.end_point, body.type) in node_list:
                            first_stmt_index = self.get_index(body)
                            self.add_edge(
                                current_index, first_stmt_index, "first_next_line"
                            )

                    last_line, _ = self.get_block_last_line(node, "body")
                    if (
                        last_line
                        and (last_line.start_point, last_line.end_point, last_line.type)
                        in node_list
                    ):
                        condition = node.child_by_field_name("condition")
                        if condition:
                            cond_key = (
                                condition.start_point,
                                condition.end_point,
                                condition.type,
                            )
                            if cond_key in node_list:
                                cond_index = self.get_index(condition)
                                if (
                                    not self.is_jump_statement(last_line)
                                    and last_line.type != "try_statement"
                                ):
                                    self.add_edge(
                                        self.get_index(last_line),
                                        cond_index,
                                        "next_line",
                                    )

                condition = node.child_by_field_name("condition")
                if condition:
                    cond_key = (
                        condition.start_point,
                        condition.end_point,
                        condition.type,
                    )
                    if cond_key in node_list:
                        cond_index = self.get_index(condition)

                        if first_stmt_index is not None:
                            self.add_edge(cond_index, first_stmt_index, "pos_next")

                        next_index, next_node = self.get_next_index(node, node_list)
                        if next_index != 2:
                            self.add_edge(cond_index, next_index, "neg_next")

            elif node.type == "break_statement":
                parent = node.parent
                while parent is not None:
                    if parent.type in [
                        "while_statement",
                        "for_statement",
                        "for_range_loop",
                        "do_statement",
                        "switch_statement",
                    ]:
                        next_index, next_node = self.get_next_index(parent, node_list)
                        if next_index != 2:
                            self.add_edge(current_index, next_index, "jump_next")
                        break
                    parent = parent.parent

            elif node.type == "continue_statement":
                parent = node.parent
                while parent is not None:
                    if parent.type in self.statement_types["loop_control_statement"]:
                        if (
                            parent.start_point,
                            parent.end_point,
                            parent.type,
                        ) in node_list:
                            loop_index = self.get_index(parent)
                            self.add_edge(current_index, loop_index, "jump_next")
                        break
                    parent = parent.parent

            elif node.type == "return_statement":
                func = self.get_containing_function(node)
                if func and (func.start_point, func.end_point, func.type) in node_list:
                    func_index = self.get_index(func)
                    if func_index not in self.records["return_statement_map"]:
                        self.records["return_statement_map"][func_index] = []
                    if (
                        current_index
                        not in self.records["return_statement_map"][func_index]
                    ):
                        self.records["return_statement_map"][func_index].append(
                            current_index
                        )

            elif node.type == "goto_statement":
                label_node = node.child_by_field_name("label")
                if label_node:
                    label_name = label_node.text.decode("utf-8") + ":"
                    if label_name in self.records["label_statement_map"]:
                        label_key = self.records["label_statement_map"][label_name]
                        if label_key in node_list:
                            label_index = self.index[label_key]
                            self.add_edge(current_index, label_index, "jump_next")

            elif node.type == "labeled_statement":
                children = list(node.named_children)
                if len(children) >= 2:
                    stmt = children[1]
                    if (stmt.start_point, stmt.end_point, stmt.type) in node_list:
                        self.add_edge(current_index, self.get_index(stmt), "next_line")

            elif node.type == "switch_statement":
                body = node.child_by_field_name("body")
                has_default = False
                if body:
                    case_nodes = []
                    for child in body.named_children:
                        if child.type == "case_statement":
                            case_nodes.append(child)
                            if child.child_by_field_name("value") is None:
                                has_default = True

                    for case_node in case_nodes:
                        if (
                            case_node.start_point,
                            case_node.end_point,
                            case_node.type,
                        ) in node_list:
                            case_index = self.get_index(case_node)
                            self.add_edge(current_index, case_index, "switch_case")

                if not has_default:
                    next_index, next_node = self.get_next_index(node, node_list)
                    if next_index != 2:
                        self.add_edge(current_index, next_index, "switch_exit")

            elif node.type == "case_statement":
                children = list(node.named_children)
                if children:
                    value_field = node.child_by_field_name("value")

                    start_index = 0 if value_field is None else 1

                    for i in range(start_index, len(children)):
                        if children[i].type in self.statement_types["node_list_type"]:
                            if (
                                children[i].start_point,
                                children[i].end_point,
                                children[i].type,
                            ) in node_list:
                                self.add_edge(
                                    current_index,
                                    self.get_index(children[i]),
                                    "case_next",
                                )
                            break

            elif node.type == "try_statement":
                body = node.child_by_field_name("body")
                if body:
                    if body.type == "compound_statement":
                        children = list(body.named_children)
                        if children:
                            first_stmt = children[0]
                            if (
                                first_stmt.start_point,
                                first_stmt.end_point,
                                first_stmt.type,
                            ) in node_list:
                                self.add_edge(
                                    current_index,
                                    self.get_index(first_stmt),
                                    "try_next",
                                )

                catch_clauses = []
                for child in node.children:
                    if child.type == "catch_clause":
                        catch_clauses.append(child)

                for catch_node in catch_clauses:
                    if (
                        catch_node.start_point,
                        catch_node.end_point,
                        catch_node.type,
                    ) in node_list:
                        catch_index = self.get_index(catch_node)
                        self.add_edge(current_index, catch_index, "catch_exception")

                last_line, _ = self.get_block_last_line(node, "body")
                if (
                    last_line
                    and (last_line.start_point, last_line.end_point, last_line.type)
                    in node_list
                ):
                    if not self.is_jump_statement(last_line):
                        next_index, next_node = self.get_next_index(node, node_list)
                        if next_index != 2:
                            self.add_edge(
                                self.get_index(last_line), next_index, "try_exit"
                            )

            elif node.type == "catch_clause":
                body = node.child_by_field_name("body")
                if body:
                    if body.type == "compound_statement":
                        children = list(body.named_children)
                        if children:
                            first_stmt = children[0]
                            if (
                                first_stmt.start_point,
                                first_stmt.end_point,
                                first_stmt.type,
                            ) in node_list:
                                self.add_edge(
                                    current_index,
                                    self.get_index(first_stmt),
                                    "catch_next",
                                )

                last_line, _ = self.get_block_last_line(node, "body")
                if (
                    last_line
                    and (last_line.start_point, last_line.end_point, last_line.type)
                    in node_list
                ):
                    if not self.is_jump_statement(last_line):
                        parent_try = node.parent
                        if parent_try and parent_try.type == "try_statement":
                            next_index, next_node = self.get_next_index(
                                parent_try, node_list
                            )
                            if next_index != 2:
                                self.add_edge(
                                    self.get_index(last_line), next_index, "catch_exit"
                                )

            elif node.type == "throw_statement":
                thrown_type = self.extract_thrown_type(node)

                parent = node.parent
                found_try = False
                while parent is not None:
                    if parent.type == "try_statement":
                        for child in parent.children:
                            if child.type == "catch_clause":
                                if (
                                    child.start_point,
                                    child.end_point,
                                    child.type,
                                ) in node_list:
                                    catch_type = self.extract_catch_parameter_type(
                                        child
                                    )

                                    if self.exception_type_matches(
                                        thrown_type, catch_type
                                    ):
                                        catch_index = self.get_index(child)
                                        self.add_edge(
                                            current_index, catch_index, "throw_exit"
                                        )
                                        found_try = True
                                        break

                        break
                    parent = parent.parent

                if not found_try:
                    func = self.get_containing_function(node)
                    if (
                        func
                        and (func.start_point, func.end_point, func.type) in node_list
                    ):
                        func_index = self.get_index(func)
                        if func_index not in self.records["return_statement_map"]:
                            self.records["return_statement_map"][func_index] = []
                        if (
                            current_index
                            not in self.records["return_statement_map"][func_index]
                        ):
                            self.records["return_statement_map"][func_index].append(
                                current_index
                            )

            elif node.type == "lambda_expression":
                pass

        self.insert_scope_destructors(node_list)

        self.chain_base_class_destructors()

        global_declarations = []

        for key, node in node_list.items():
            if node.parent and node.parent.type == "translation_unit":
                if node.type in [
                    "class_specifier",
                    "struct_specifier",
                    "enum_specifier",
                    "type_definition",
                    "namespace_definition",
                    "declaration",
                ]:
                    node_id = self.get_index(node)
                    global_declarations.append((node_id, node.start_point[0]))

        global_declarations.sort(key=lambda x: x[1])

        self.add_function_call_edges()

        self.add_lambda_edges()

        if "main_function" not in self.records:
            first_function_id = None
            for key, node in node_list.items():
                if node.type == "function_definition":
                    parent = node.parent
                    if parent and parent.type == "translation_unit":
                        first_function_id = self.get_index(node)
                        break

            if first_function_id:
                self.add_edge(1, first_function_id, "program_entry")

        return self.CFG_node_list, self.CFG_edge_list
