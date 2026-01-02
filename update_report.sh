#!/bin/bash
# Quick script to pull the latest report from GitHub

echo "Pulling latest trade report from GitHub..."
git pull origin main

if [ -f "docs/index.html" ]; then
    echo "✓ Report updated!"
    echo "Opening report in browser..."
    python3 view_report.py
else
    echo "⚠ Report file not found"
fi

