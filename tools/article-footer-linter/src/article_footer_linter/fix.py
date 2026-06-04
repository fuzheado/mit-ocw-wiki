"""
Pure functions for applying fixes to Wikipedia article footers.

Takes wikitext + list of Issues, returns fixed wikitext + list of FixResults.
No API calls, no side effects.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from .analyze import Issue, get_headings, _find_templates, _first_category_line, _last_category_end


@dataclass
class FixResult:
    """Record of a fix that was applied."""
    type: str
    applied: bool
    description: str


# ─── Fix ordering ──────────────────────────────────────────────────────────

# Fixes must be applied in order to avoid conflicts:
FIX_ORDER = [
    "whitespace_cleanup",
    "section_spacing",
    "bullet_after_categories",
    "stub_position",
    "auth_control_position",
    "defaultsort_position",
]


# ─── Individual fix functions ──────────────────────────────────────────────

def fix_whitespace_cleanup(wikitext: str, issues: list[Issue]) -> tuple[str, list[FixResult]]:
    """Collapse 3+ consecutive blank lines to 2. Remove trailing blank lines."""
    results = []
    fixed = wikitext

    # Collapse 3+ blank lines to 2
    new, n = re.subn(r'\n\n\n\n+', '\n\n\n', fixed)
    if n > 0:
        results.append(FixResult(type="whitespace_cleanup", applied=True,
                                 description=f"Collapsed {n} instance(s) of 3+ consecutive blank lines"))
        fixed = new

    # Remove trailing blank lines (keep exactly one trailing newline)
    fixed = fixed.rstrip('\n') + '\n'
    if fixed != wikitext:
        results.append(FixResult(type="whitespace_cleanup", applied=True,
                                 description="Removed trailing blank lines"))

    return fixed, results


def fix_section_spacing(wikitext: str, issues: list[Issue]) -> tuple[str, list[FixResult]]:
    """
    Ensure blank lines between sections.
    For each section spacing issue, insert a blank line between the sections.
    """
    results = []
    fixed = wikitext

    # Process issues in reverse order to avoid position shifts
    spacing_issues = [i for i in issues if i.type == "section_spacing"]
    for issue in reversed(spacing_issues):
        # The issue's position points to the start of the later heading.
        # Walk backwards to find the end of the previous section.
        pos = issue.position
        # Ensure there's a blank line before this heading
        before = fixed[max(0, pos - 3):pos]
        if not before.endswith('\n\n'):
            # Insert a blank line
            if before.endswith('\n'):
                fixed = fixed[:pos] + '\n' + fixed[pos:]
            else:
                fixed = fixed[:pos] + '\n\n' + fixed[pos:]
            results.append(FixResult(type="section_spacing", applied=True,
                                     description=f"Added blank line before \"{issue.details.get('after', '')}\""))

    return fixed, results


def fix_bullets_after_categories(wikitext: str, issues: list[Issue]) -> tuple[str, list[FixResult]]:
    """
    Move * bullets found after the first [[Category:...]] to before categories.
    Also moves them before {{DEFAULTSORT}} and {{Authority control}} if those exist.
    """
    results = []
    fixed = wikitext

    bullet_issues = [i for i in issues if i.type == "bullet_after_categories"]
    if not bullet_issues:
        return fixed, results

    first_cat = _first_category_line(fixed)
    if first_cat is None:
        return fixed, results

    # Collect all * bullets after first category (in reverse order for stable removal)
    bullets = []
    for m in re.finditer(r'^(\s*\*[^\n]*\n?)', fixed[first_cat:], re.MULTILINE):
        bullets.append({
            "start": first_cat + m.start(),
            "end": first_cat + m.end(),
            "text": m.group(1),
        })

    if not bullets:
        return fixed, results

    # Remove bullets from after categories (reverse order)
    for b in reversed(bullets):
        fixed = fixed[:b["start"]] + fixed[b["end"]:]

    # Insert bullets right before the first category, after any DEFAULTSORT/Authority control
    # Find the right insertion point: before first category, after DEFAULTSORT if present
    insert_pos = first_cat

    # Check if DEFAULTSORT is just before categories
    defaultsorts = _find_templates(fixed, "DEFAULTSORT")
    if defaultsorts and defaultsorts[0]["end"] < insert_pos:
        # Insert after DEFAULTSORT's line
        line_end = fixed.find('\n', defaultsorts[0]["end"])
        if line_end > 0:
            insert_pos = line_end + 1

    # Combine bullet texts
    bullet_text = ""
    for b in bullets:
        bullet_text += b["text"].rstrip('\n') + "\n"

    fixed = fixed[:insert_pos] + "\n" + bullet_text + fixed[insert_pos:]

    results.append(FixResult(type="bullet_after_categories", applied=True,
                             description=f"Moved {len(bullets)} * bullet(s) from after categories to before"))

    return fixed, results


def fix_stub_position(wikitext: str, issues: list[Issue]) -> tuple[str, list[FixResult]]:
    """Move stub templates to after the last category."""
    results = []
    fixed = wikitext

    stub_issues = [i for i in issues if i.type == "stub_position"]
    if not stub_issues:
        return fixed, results

    last_cat_end = _last_category_end(fixed)
    if last_cat_end is None:
        return fixed, results

    # Find all stubs (in reverse order)
    stubs = _find_templates(fixed, ".*-stub")
    if not stubs:
        return fixed, results

    # Remove stubs (reverse order)
    stub_texts = []
    for s in reversed(stubs):
        stub_texts.append(s["text"])
        fixed = fixed[:s["start"]] + fixed[s["end"]:]

    # Append stubs after last category
    stub_texts.reverse()
    for stub_text in stub_texts:
        fixed = fixed[:last_cat_end] + "\n" + stub_text + fixed[last_cat_end:]

    results.append(FixResult(type="stub_position", applied=True,
                             description=f"Moved {len(stubs)} stub template(s) to after categories"))
    return fixed, results


def fix_auth_control_position(wikitext: str, issues: list[Issue]) -> tuple[str, list[FixResult]]:
    """Move {{Authority control}} to after navboxes, before categories."""
    results = []
    fixed = wikitext

    ac_issues = [i for i in issues if i.type == "auth_control_position"]
    if not ac_issues:
        return fixed, results

    auth_controls = _find_templates(fixed, "Authority control")
    if not auth_controls:
        return fixed, results

    ac = auth_controls[0]
    first_cat = _first_category_line(fixed)
    if first_cat is None:
        return fixed, results

    # Remove Authority control
    ac_text = ac["text"]
    fixed = fixed[:ac["start"]] + fixed[ac["end"]:]

    # Insert before first category (and after DEFAULTSORT if present)
    insert_pos = first_cat
    defaultsorts = _find_templates(fixed, "DEFAULTSORT")
    if defaultsorts and defaultsorts[0]["end"] < insert_pos:
        line_end = fixed.find('\n', defaultsorts[0]["end"])
        if line_end > 0:
            insert_pos = line_end + 1

    fixed = fixed[:insert_pos] + "\n" + ac_text + "\n" + fixed[insert_pos:]

    results.append(FixResult(type="auth_control_position", applied=True,
                             description="Moved {{Authority control}} to after navboxes, before categories"))
    return fixed, results


def fix_defaultsort_position(wikitext: str, issues: list[Issue]) -> tuple[str, list[FixResult]]:
    """Move {{DEFAULTSORT}} to immediately before the first category."""
    results = []
    fixed = wikitext

    ds_issues = [i for i in issues if i.type == "defaultsort_position"]
    if not ds_issues:
        return fixed, results

    defaultsorts = _find_templates(fixed, "DEFAULTSORT")
    if not defaultsorts:
        return fixed, results

    ds = defaultsorts[0]
    first_cat = _first_category_line(fixed)
    if first_cat is None:
        return fixed, results

    # Already in correct position?
    if ds["end"] + 20 >= first_cat and ds["start"] < first_cat:
        # Close enough — don't move
        return fixed, results

    # Remove DEFAULTSORT
    ds_text = ds["text"]
    fixed = fixed[:ds["start"]] + fixed[ds["end"]:]

    # Insert immediately before first category
    fixed = fixed[:first_cat] + ds_text + "\n" + fixed[first_cat:]

    results.append(FixResult(type="defaultsort_position", applied=True,
                             description="Moved {{DEFAULTSORT}} to before categories"))
    return fixed, results


# ─── Public API ────────────────────────────────────────────────────────────

def apply_fixes(wikitext: str, issues: list[Issue]) -> tuple[str, list[FixResult]]:
    """
    Apply detectable fixes to the article footer in the correct order.

    Args:
        wikitext: The full wikitext of the article.
        issues: List of Issue objects from analyze_footer().

    Returns:
        (fixed_wikitext, list_of_fix_results)
    """
    if not wikitext or not issues:
        return wikitext, []

    fix_map = {
        "whitespace_cleanup": fix_whitespace_cleanup,
        "section_spacing": fix_section_spacing,
        "bullet_after_categories": fix_bullets_after_categories,
        "stub_position": fix_stub_position,
        "auth_control_position": fix_auth_control_position,
        "defaultsort_position": fix_defaultsort_position,
    }

    fixed = wikitext
    all_results = []

    for fix_type in FIX_ORDER:
        fix_fn = fix_map.get(fix_type)
        if not fix_fn:
            continue
        # Only run fix if there's an issue of this type
        type_issues = [i for i in issues if i.type == fix_type]
        if not type_issues:
            continue
        fixed, results = fix_fn(fixed, type_issues)
        all_results.extend(results)

    return fixed, all_results
