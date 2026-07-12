import sys
import os
# Add parent directory to path so we can import PyCodeCommenter if not installed
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from PyCodeCommenter import PyCodeCommenter

def run_ci_check():
    """
    Simulates a CI/CD check for documentation quality.
    Fails (exit 1) if there are any ERROR level issues.
    """
    # In a real CI, you might iterate over all changed files
    test_file = os.path.abspath(os.path.join(os.path.dirname(__file__), 'basic_usage.py'))
    
    print(f"Checking documentation for {test_file}...")
    commenter = PyCodeCommenter().from_file(test_file)
    report = commenter.validate()
    
    if report.stats.errors > 0:
        print("❌ Documentation check FAILED!")
        report.print_summary()
        sys.exit(1)
    
    print(f"✅ Documentation check PASSED! ({report.stats.coverage_percentage:.1f}% coverage)")
    sys.exit(0)

if __name__ == "__main__":
    run_ci_check()
