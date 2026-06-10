import ast

try:
    ast.parse('def 世界_function(name="世界"): return name')
    print("Chinese characters are valid Python identifiers!")
except SyntaxError as e:
    print("Chinese characters failed:", e)

try:
    ast.parse('def 🚀_function(): pass')
    print("Emoji characters are valid Python identifiers!")
except SyntaxError as e:
    print("Emoji characters failed:", e)
