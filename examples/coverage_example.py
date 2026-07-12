import os
from PyCodeCommenter import CoverageAnalyzer

def main():
    # Analyze the current directory (or any directory)
    analyzer = CoverageAnalyzer()
    
    # We'll analyze the parent directory where the project resides
    current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print(f"Analyzing coverage for: {current_dir}")
    
    project = analyzer.analyze_directory(current_dir)
    
    # Print a beautiful report
    project.print_report()

if __name__ == "__main__":
    main()
