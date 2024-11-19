import ast
from .templates import get_function_description
from .parameter_descriptions import parameter_descriptions


class PyCodeCommenter:
    def __init__(self):
        self.code = ""
        self.parsed_code = None
        self.comments = []

    def from_string(self, code_string):
        try:
            if code_string is None or code_string.strip() == "":
                print("No code provided. Proceeding with an empty string.")
                self.code = ""
                self.parsed_code = ast.Module(body=[])
            else:
                self.code = code_string
                self.parsed_code = ast.parse(self.code)
        except SyntaxError as e:
            print(f"Syntax error in provided code: {e}")
            self.parsed_code = None
        return self

    def from_file(self, file_path):
        try:
            with open(file_path, 'r') as file:
                self.code = file.read()
            self.parsed_code = ast.parse(self.code)
        except (FileNotFoundError, IOError) as e:
            print(f"Error reading file: {e}")
            self.parsed_code = None
        except SyntaxError as e:
            print(f"Syntax error in provided code: {e}")
            self.parsed_code = None
        return self

    def generate_docstrings(self):
        """Iterates over the parsed code to generate docstrings for functions and classes."""
        if self.parsed_code is None:
            print("No valid code to parse. Please check for errors.")
            return []

        for node in ast.walk(self.parsed_code):
            if isinstance(node, ast.FunctionDef):
                try:
                    self.comments.append(self._generate_function_docstring(node))
                except Exception as e:
                    print(f"Error generating docstring for function '{node.name}': {e}")
            elif isinstance(node, ast.ClassDef):
                try:
                    self.comments.append(self._generate_class_docstring(node))
                except Exception as e:
                    print(f"Error generating docstring for class '{node.name}': {e}")
        return self.comments



    # def _generate_function_docstring(self, func_node):
    #     """Generates a Google-style docstring for a function with an indicator."""
    #     try:
    #         function_description = get_function_description(func_node.name)

    #         docstring = f'function: {func_node.name}\n\n'
    #         docstring += f"{function_description}\n\n"

    #         # Example Generation
    #         example = self._generate_example(func_node)
    #         docstring += f"Example:\n    {example}\n\n"

    #         docstring += "Args:\n"
    #         defaults = [None] * (len(func_node.args.args) - len(func_node.args.defaults)) + func_node.args.defaults

    #         for arg, default in zip(func_node.args.args, defaults):
    #             inferred_type = self._infer_type(arg)
    #             param_description = self._get_parameter_description(func_node.name, arg.arg)
    #             arg_description = f"    {arg.arg} ({inferred_type}): {param_description}"
    #             if default is not None:
    #                 default_value = self._get_default_value(default)
    #                 arg_description += f" (default: {default_value})"
    #             docstring += arg_description + ".\n"

    #         return_type = self._get_return_type(func_node)
    #         docstring += "\nReturns:\n"
    #         docstring += f"    {return_type}: Description of return value.\n"
    #         return docstring

    #     except Exception as e:
    #         print(f"Error generating docstring for function '{func_node.name}': {e}")
    #         return 'Error generating docstring.'


    # styled function docstring
    def _generate_function_docstring(self, func_node):
        """Generates a styled, Google-style docstring for a function with enhanced formatting."""
        try:
            function_description = get_function_description(func_node.name)

            # Header with function title and description
            docstring = (
                "########################################\n"
                f"### Function: {func_node.name}\n"
                f"### Description: {function_description}\n"
                "########################################\n\n"
            )

            # Example Generation
            example = self._generate_example(func_node)
            docstring += (
                "Example Usage:\n"
                "---------------\n"
                f"    {example}\n\n"
            )

            # Args Section with more structured formatting
            docstring += "Args:\n---------------\n"
            defaults = [None] * (len(func_node.args.args) - len(func_node.args.defaults)) + func_node.args.defaults

            for arg, default in zip(func_node.args.args, defaults):
                inferred_type = self._infer_type(arg)
                param_description = self._get_parameter_description(func_node.name, arg.arg)
                arg_description = f"    {arg.arg} ({inferred_type}): {param_description}"
                if default is not None:
                    default_value = self._get_default_value(default)
                    arg_description += f" (default: {default_value})"
                docstring += arg_description + ".\n"

            # Return section with additional spacing for readability
            return_type = self._get_return_type(func_node)
            docstring += "\nReturns:\n---------------\n"
            docstring += f"    {return_type}: Description of return value.\n"
            docstring += "\n####################################################\n"
            return docstring

        except Exception as e:
            print(f"Error generating docstring for function '{func_node.name}': {e}")
            return 'Error generating docstring.'


    # def _generate_class_docstring(self, class_node):
    #     """Generates a docstring for a class with an indicator."""
    #     class_name = class_node.name
    #     docstring = f'class: {class_name}\n\n'
    #     docstring += f"{class_name} class for [describe purpose].\n\n"
        
    #     attributes = self._get_class_attributes(class_node)
    #     docstring += "Attributes:\n"
    #     for attr_name, attr_type in attributes.items():
    #         docstring += f"    {attr_name} ({attr_type}): Description of attribute.\n"

    #     methods = [node.name for node in class_node.body if isinstance(node, ast.FunctionDef)]
    #     docstring += "\nMethods:\n"
    #     for method in methods:
    #         docstring += f"    {method}(): Description of method.\n"
        
    #     return docstring



    # styled class docstring
    def _generate_class_docstring(self, class_node):
        """Generates a styled docstring for a class with enhanced formatting."""
        class_name = class_node.name

        # Header with class title and purpose description
        docstring = (
            "########################################\n"
            f"### Class: {class_name}\n"
            f"### Description: {class_name} class for [describe purpose].\n"
            "########################################\n\n"
        )

        # Attributes section with border and structured formatting
        docstring += "Attributes:\n---------------\n"
        attributes = self._get_class_attributes(class_node)
        if attributes:
            for attr_name, attr_type in attributes.items():
                docstring += f"    {attr_name} ({attr_type}): Description of attribute.\n"
        else:
            docstring += "    None\n"

        # Methods section with border and structured formatting
        docstring += "\nMethods:\n---------------\n"
        methods = [node.name for node in class_node.body if isinstance(node, ast.FunctionDef)]
        if methods:
            for method in methods:
                docstring += f"    {method}(): Description of method.\n"
        else:
            docstring += "    None\n"

        docstring += "\n####################################################\n"
        return docstring

    def _get_parameter_description(self, func_name, param_name):
        """Generates descriptions for parameters based on function and parameter names."""
        return parameter_descriptions.get(func_name, {}).get(param_name, f"{param_name} of the object.")

    def _get_class_attributes(self, class_node):
        """Retrieves attributes from the __init__ method, if defined, to document class variables."""
        attributes = {}
        for item in class_node.body:
            if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                for arg in item.args.args[1:]:
                    inferred_type = self._infer_type(arg)
                    attributes[arg.arg] = inferred_type
        return attributes

    def _indent_text(self, text, spaces):
        """Helper function to indent text by a given number of spaces."""
        indentation = ' ' * spaces
        indented_lines = [indentation + line if line.strip() else line for line in text.splitlines()]
        return "\n".join(indented_lines)

    def generate_variable_descriptions(self):
        """Generates variable descriptions with inferred purposes."""
        variable_descriptions = []
        for node in ast.walk(self.parsed_code):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        var_name = target.id
                        inferred_type = self._infer_type(node.value)
                        purpose = self._infer_purpose(var_name, inferred_type)
                        variable_descriptions.append(f"{var_name} ({inferred_type}): {purpose}")
        return variable_descriptions

    def _infer_type(self, node):
            """Infers the type of a variable based on its initial value."""
            if isinstance(node, ast.List):
                return "list"
            elif isinstance(node, ast.Dict):
                return "dict"
            elif isinstance(node, ast.Num):
                return "int" if isinstance(node.n, int) else "float"
            elif isinstance(node, ast.Str):
                return "str"
            return "unknown_type"

    def _infer_purpose(self, var_name, var_type):
        """Infers purpose based on naming conventions and type."""
        if "list" in var_name.lower() or var_type == "list":
            return "Collection of items for [describe items here]"
        elif "count" in var_name.lower() or var_type == "int":
            return "Integer counter or total for [describe purpose]"
        elif "sum" in var_name.lower() or var_name.startswith("total"):
            return "Accumulated total value for [describe purpose]"
        return "Variable used for [general purpose]"

    
    def _generate_loop_docstring(self, loop_node):
        """Generates documentation for loops."""
        loop_type = "for" if isinstance(loop_node, ast.For) else "while"
        docstring = f"{loop_type.capitalize()} Loop:\n"
        
        if isinstance(loop_node, ast.For):
            loop_var = loop_node.target.id if isinstance(loop_node.target, ast.Name) else "element"
            iterable = self._infer_type(loop_node.iter)
            docstring += f"    Iterates over {iterable}, processing each {loop_var}.\n"
        elif isinstance(loop_node, ast.While):
            condition = ast.dump(loop_node.test)
            docstring += f"    Repeats while the condition ({condition}) is met.\n"
        
        return docstring

    def _generate_conditional_docstring(self, if_node):
        """Generates documentation for conditionals."""
        docstring = "Conditional:\n"
        condition = ast.dump(if_node.test)
        docstring += f"    If condition ({condition}): Executes block if true.\n"
        
        for elif_node in if_node.orelse:
            if isinstance(elif_node, ast.If):
                elif_condition = ast.dump(elif_node.test)
                docstring += f"    Elif condition ({elif_condition}): Executes block if true.\n"
            else:
                docstring += "    Else: Executes if previous conditions are false.\n"
        
        return docstring


    def _generate_example(self, func_node):
        """Generates an example usage for the function."""
        example_args = []
        for arg in func_node.args.args:
            example_value = "None"
            inferred_type = self._infer_type(arg)
            if "int" in inferred_type:
                example_value = "0"
            elif "str" in inferred_type:
                example_value = "''"
            elif "list" in inferred_type:
                example_value = "[]"
            elif "dict" in inferred_type:
                example_value = "{}"
            example_args.append(f"{arg.arg} = {example_value}")

        example = f"{func_node.name}({', '.join(example_args)})"
        return example

    def _infer_type(self, arg):
        """Infers the type of an argument if possible, extracting readable type names."""
        try:
            if hasattr(arg, 'annotation') and arg.annotation:  # Ensure 'annotation' exists
                return self._get_annotation_type(arg.annotation)
            return "Type"
        except Exception as e:
            print(f"Error inferring type for argument '{arg.arg}': {e}")
            return "unknown"


    def _get_annotation_type(self, annotation):
        """Extracts a user-friendly type name from annotation nodes."""
        try:
            if isinstance(annotation, ast.Name):
                return annotation.id
            elif isinstance(annotation, ast.Attribute):
                return f"{annotation.value.id}.{annotation.attr}"
            elif isinstance(annotation, ast.Subscript):
                base_type = self._get_annotation_type(annotation.value)
                sub_type = self._get_annotation_type(annotation.slice.value)
                return f"{base_type}[{sub_type}]"
            return "UnknownType"
        except Exception as e:
            print(f"Error getting annotation type: {e}")
            return "unknown"


    def _get_default_value(self, default_node):
        """Extracts default value for arguments, handling literals and simple expressions."""
        try:
            if isinstance(default_node, ast.Constant):
                return repr(default_node.value)
            elif isinstance(default_node, ast.NameConstant):
                return repr(default_node.value)
            elif isinstance(default_node, ast.Str):
                return repr(default_node.s)
            return "unknown_default"
        except Exception as e:
            print(f"Error getting default value: {e}")
            return "unknown_default"


    def _get_return_type(self, func_node):
        """Infers the return type by analyzing return statements if no annotation is present."""
        # Check for an explicit return annotation
        if func_node.returns:
            return self._describe_return_type(func_node.returns)

        # Analyze return statements in the function body
        return_types = set()
        for stmt in func_node.body:
            if isinstance(stmt, ast.Return) and stmt.value is not None:
                inferred_type = self._infer_expr_type(stmt.value)
                return_types.add(inferred_type)

        # Generate a description based on the inferred return types
        if return_types:
            return_type_description = " | ".join(self._generate_return_type_description(rt) for rt in return_types)
            return return_type_description

        # Default case for functions with no return value
        return "None: This function does not return a value."
        

    def _generate_return_type_description(self, inferred_type):
        """Generate a description template for common return types."""
        type_descriptions = {
            "int": "int: Represents an integer value, often used for counts or indices.",
            "str": "str: Represents a string value, often used for textual information.",
            "list": "list: A list of elements, typically used to store multiple items.",
            "dict": "dict: A dictionary mapping keys to values, commonly used for structured data.",
            "bool": "bool: Returns True or False, typically used for conditional checks.",
            "float": "float: Represents a floating-point number, often used for precision values.",
            "NoneType": "None: This function does not return a value.",
            "unknown_type": "UnknownType: Unable to infer a specific return type.",
        }
        return type_descriptions.get(inferred_type, f"{inferred_type}: Custom return type.")  
        

    def _describe_return_type(self, return_annotation):
        """Describes the return type based on function return annotations."""
        if isinstance(return_annotation, ast.Name):
            return return_annotation.id
        elif isinstance(return_annotation, ast.Subscript):
            base_type = self._describe_return_type(return_annotation.value)
            sub_type = self._describe_return_type(return_annotation.slice.value)
            return f"{base_type}[{sub_type}]"
        return "UnknownType"


    def _infer_expr_type(self, expr):
        """Infers type from an expression node."""
        try:
            if isinstance(expr, ast.Constant):
                return type(expr.value).__name__
            elif isinstance(expr, ast.List):
                return "list"
            elif isinstance(expr, ast.Dict):
                return "dict"
            elif isinstance(expr, ast.Str):
                return "str"
            elif isinstance(expr, ast.Num):
                return "int" if isinstance(expr.n, int) else "float"
            elif isinstance(expr, ast.Name) and expr.id in {'True', 'False'}:
                return "bool"
            return "unknown_type"
        except Exception as e:
            print(f"Error inferring expression type: {e}")
            return "unknown_type"

