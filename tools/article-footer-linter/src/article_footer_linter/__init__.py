"""
Article Footer Linter — lint and fix Wikipedia article footers.

Public API:
    analyze_footer(wikitext)         → [Issue]
    apply_fixes(wikitext, issues)    → (wikitext, [fixes_applied])
    check_links(wikitext)            → [LinkResult]   (Phase 2)
"""

from .analyze import analyze_footer, Issue, RECOMMENDED_ORDER
from .fix import apply_fixes, FixResult

__all__ = ["analyze_footer", "apply_fixes", "Issue", "FixResult", "RECOMMENDED_ORDER"]
