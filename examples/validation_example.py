from PyCodeCommenter import PyCodeCommenter

def main():
    # Code with some documentation issues
    code = """
def process_data(data, timeout=30):
    \"\"\"Process the data.
    
    Args:
        data: The data to process.
    \"\"\"
    if timeout > 0:
        return data.strip()
    return data
"""

    commenter = PyCodeCommenter().from_string(code)
    
    # Validate documentation
    report = commenter.validate()
    
    # Print the report summary
    report.print_summary()

if __name__ == "__main__":
    main()
