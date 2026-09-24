import sys
import ast
import traceback


from PyCodeCommenter.commenter import PyCodeCommenter

code = """
async def simple_async():
    return 1
"""


def test():
    with open("modern_results.txt", "w") as f:
        f.write(f"Python version: {sys.version}\n")
        try:
            ast.parse(code)
            f.write("ast.parse(code) Success\n")
        except Exception as e:
            f.write(f"ast.parse(code) Failed: {e}\n")
            f.write(traceback.format_exc())

        commenter = PyCodeCommenter()
        commenter.from_string(code)

        if commenter.parsed_code is None:
            f.write("commenter.parsed_code is None\n")
        else:
            f.write("commenter.parsed_code is NOT None\n")
            f.write(f"Patched Code:\n{commenter.get_patched_code()}\n")


if __name__ == "__main__":
    test()
