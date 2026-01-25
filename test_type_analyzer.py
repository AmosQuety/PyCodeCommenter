import os
import sys
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(parent_dir)

import ast
from PyCodeCommenter.type_analyzer import TypeAnalyzer

def test():
    analyzer = TypeAnalyzer()
    
    # Test Constant
    print(f"int: {analyzer.infer_expr_type(ast.parse('1').body[0].value)}")
    print(f"str: {analyzer.infer_expr_type(ast.parse(\"'s'\").body[0].value)}")
    
    # Test List
    print(f"list: {analyzer.infer_expr_type(ast.parse('[]').body[0].value)}")
    
    # Test Annotation
    ann = ast.parse("x: int | str").body[0].annotation
    print(f"Union: {analyzer.get_annotation_type(ann)}")
    
    # Test list[int]
    ann2 = ast.parse("x: list[int]").body[0].annotation
    print(f"Generic: {analyzer.get_annotation_type(ann2)}")

if __name__ == "__main__":
    test()
