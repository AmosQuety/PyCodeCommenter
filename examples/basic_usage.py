from PyCodeCommenter import PyCodeCommenter


def main():
    # Example code to document
    code = """
def calculate_discount(price: float, rate: float = 0.1) -> float:
    return price * (1 - rate)

class ShoppingCart:
    def __init__(self, items: list):
        self.items = items

    def add_item(self, item):
        self.items.append(item)
"""

    print("--- ORIGINAL CODE ---")
    print(code)

    # Initialize commenter
    commenter = PyCodeCommenter().from_string(code)

    # Generate docstrings
    docstrings = commenter.generate_docstrings()
    print("\n--- GENERATED DOCSTRINGS ---")
    for doc in docstrings:
        print(doc)

    # Get patched code
    patched_code = commenter.get_patched_code()
    print("\n--- PATCHED CODE ---")
    print(patched_code)


if __name__ == "__main__":
    main()
