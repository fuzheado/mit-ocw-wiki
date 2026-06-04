#!/usr/bin/env python3
"""
Thin wrapper — delegates to the article-footer-linter package.

Usage:
    python3 scripts/lint-article-footer.py "Article"
    python3 scripts/lint-article-footer.py --fix "Article"
    python3 scripts/lint-article-footer.py --survey 50
"""

import sys, os

# Ensure the package is importable from its tools/ location
TOOLS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "article-footer-linter", "src")
sys.path.insert(0, TOOLS_DIR)

from article_footer_linter.cli import main

if __name__ == "__main__":
    main()
