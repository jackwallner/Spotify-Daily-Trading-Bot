#!/usr/bin/env python3
"""
Simple script to view the trade report locally
Opens the HTML report in your default browser
"""

import os
import webbrowser
import subprocess
from pathlib import Path

def view_report():
    """Open the trade report in the default browser"""
    report_path = Path(__file__).parent / 'docs' / 'index.html'
    
    if not report_path.exists():
        print(f"Report not found at {report_path}")
        print("Make sure the workflow has run at least once to generate the report.")
        print("\nTo get the latest report from GitHub, run:")
        print("  git pull")
        return
    
    # Convert to absolute path and file:// URL
    abs_path = report_path.resolve()
    file_url = f"file://{abs_path}"
    
    print(f"Opening report: {file_url}")
    print("\nNote: This shows your local file. To get the latest from GitHub, run:")
    print("  git pull")
    print("  python3 view_report.py")
    print()
    
    webbrowser.open(file_url)
    print("Report opened in your default browser!")

if __name__ == "__main__":
    view_report()

