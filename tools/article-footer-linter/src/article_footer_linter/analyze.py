"""
Pure functions for detecting structural issues in Wikipedia article footers.

Each function takes wikitext (str) and returns a list of Issue namedtuples.
No API calls, no side effects.
"""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Issue:
    """A single detected issue in the article footer."""
    type: str
    severity: str  # "error", "warning", "info"
    position: int  # Character offset in wikitext
    description: str
    details: dict = field(default_factory=dict)


# ─── Section heading extraction ────────────────────────────────────────────

def _find_headings(wikitext: str) -> list:
    """
    Find all level-2 headings, returning (level, title, start, end, line_number).
    Uses mwparserfromhell for accurate heading detection.
    """
    import mwparserfromhell
    code = mwparserfromhell.parse(wikitext)
    headings = []
    for i, h in enumerate(code.filter_headings()):
        if h.level == 2:
            title = str(h.title).strip()
            # Find byte position in original wikitext
            h_title = str(h.title)
            pattern = rf'(?:^|\n)(={{{h.level}}}\s*{re.escape(title)}\s*={{{h.level}}})'
            m = re.search(pattern, wikitext)
            if m:
                start = m.start(1)
                end = start + len(m.group(1))
                # Count newlines before this position for line number
                line_num = wikitext[:start].count('\n') + 1
                headings.append({
                    "level": h.level,
                    "title": title,
                    "start": start,
                    "end": end,
                    "line": line_num,
                })
    return headings


def _find_headings_raw(wikitext: str) -> list:
    """Fallback: find level-2 headings via regex (if mwparserfromhell unavailable)."""
    headings = []
    for m in re.finditer(r'^==\s*(.+?)\s*==\s*$', wikitext, re.MULTILINE):
        # Only match level-2 (not === or ====)
        headings.append({
            "level": 2,
            "title": m.group(1).strip(),
            "start": m.start(),
            "end": m.end(),
            "line": wikitext[:m.start()].count('\n') + 1,
        })
    return headings


def get_headings(wikitext: str) -> list:
    """Get all level-2 headings with positions. Tries mwparserfromhell first."""
    try:
        return _find_headings(wikitext)
    except ImportError:
        return _find_headings_raw(wikitext)



# ─── Section ordering ────────────────────────────────────────────────────

# WP:LAYOUT recommended order for footer sections:
RECOMMENDED_ORDER = [
    ("see also", 0),
    ("notes", 1),
    ("footnotes", 1),
    ("notes and references", 1),
    ("references", 2),
    ("further reading", 3),
    ("external links", 4),
]
RECOMMENDED_MAP = {name: rank for name, rank in RECOMMENDED_ORDER}
ORDER_NAMES = {rank: [name for name, r in RECOMMENDED_ORDER if r == rank][0]
               for rank in sorted(set(r for _, r in RECOMMENDED_ORDER))}


def detect_section_order(wikitext: str, headings: list) -> list[Issue]:
    """
    Detect footer sections in non-standard order.
    Checks only the footer-appropriate sections (See also through External links).
    Other sections (custom ones) are left in their relative positions.
    """
    # Collect recognized footer sections
    footer_sections = []  # [(title, rank, start)]
    other_sections = []   # [(title, start)]

    for h in headings:
        h_lower = h["title"].lower()
        if h_lower in RECOMMENDED_MAP:
            footer_sections.append((h["title"], RECOMMENDED_MAP[h_lower], h["start"]))
        else:
            other_sections.append((h["title"], h["start"]))

    if len(footer_sections) <= 1:
        return []

    # Check ordering: each footer section should have a higher rank than the previous
    issues = []
    for i in range(1, len(footer_sections)):
        prev_rank = footer_sections[i - 1][1]
        curr_rank = footer_sections[i][1]
        if curr_rank < prev_rank:
            issues.append(Issue(
                type="section_order",
                severity="warning",
                position=footer_sections[i][2],
                description=f'"{footer_sections[i][0]}" appears before "{footer_sections[i - 1][0]}" — expected reverse order per WP:LAYOUT',
                details={
                    "expected_first": ORDER_NAMES.get(prev_rank, footer_sections[i - 1][0]),
                    "expected_second": ORDER_NAMES.get(curr_rank, footer_sections[i][0]),
                    "found_first": footer_sections[i - 1][0],
                    "found_second": footer_sections[i][0],
                    "prev_rank": prev_rank,
                    "curr_rank": curr_rank,
                },
            ))

    return issues
# ─── Detection helpers ─────────────────────────────────────────────────────

def _first_category_line(wikitext: str) -> Optional[int]:
    """Find the byte position of the first [[Category:...]] line."""
    m = re.search(r'^\[\[Category:', wikitext, re.MULTILINE)
    return m.start() if m else None


def _last_category_end(wikitext: str) -> Optional[int]:
    """Find the byte position after the last [[Category:...]] line."""
    matches = list(re.finditer(r'^\[\[Category:[^\]]*\]\]', wikitext, re.MULTILINE))
    if matches:
        return matches[-1].end()
    return None


def _find_bullets_in_region(wikitext: str, start: int, end: int) -> list:
    """Find all * bullet lines in a region."""
    region = wikitext[start:end]
    bullets = []
    for m in re.finditer(r'^\s*\*', region, re.MULTILINE):
        line_start = start + m.start()
        # Find end of this line
        line_end = wikitext.find('\n', line_start)
        if line_end == -1:
            line_end = len(wikitext)
        bullets.append({"start": line_start, "end": line_end, "text": wikitext[line_start:line_end].strip()})
    return bullets


def _find_templates(wikitext: str, *names: str) -> list:
    """Find template invocations by name, returning (start, end, text)."""
    results = []
    for name in names:
        # If name contains wildcards, use it as a raw regex pattern
        if '*' in name or '?' in name or '.' in name:
            pattern = r'\{\{\s*' + name + r'(?:\||:|\s|})'
        else:
            pattern = r'\{\{\s*' + re.escape(name) + r'(?:\||:|\s|})'
        for m in re.finditer(pattern, wikitext, re.IGNORECASE | re.DOTALL):
            start = m.start()
            depth = 0
            i = start
            while i < len(wikitext):
                if wikitext[i:i+2] == '{{':
                    depth += 1
                    i += 2
                elif wikitext[i:i+2] == '}}':
                    depth -= 1
                    if depth == 0:
                        end = i + 2
                        results.append({"start": start, "end": end, "text": wikitext[start:end]})
                        break
                    i += 2
                else:
                    i += 1
    return results


def _find_wikilinks(wikitext: str, prefix: str) -> list:
    """Find wikilinks with a given prefix (e.g., [[Category:...]])."""
    results = []
    for m in re.finditer(r'\[\[' + re.escape(prefix) + r'[^\]]*\]\]', wikitext):
        results.append({"start": m.start(), "end": m.end(), "text": m.group()})
    return results


def _count_consecutive_blanks(text: str, pos: int, max_lookahead: int = 200) -> int:
    """Count consecutive blank lines starting at pos."""
    count = 0
    i = pos
    while i < len(text) and i < pos + max_lookahead:
        if text[i] == '\n':
            # Check if next is also newline (blank line)
            j = i
            while j < len(text) and text[j] == '\n':
                j += 1
            blanks = j - i - 1  # count of blank lines (consecutive \n after first)
            if blanks > 0:
                return blanks + 1  # +1 for the first \n
            i = j
        else:
            i += 1
    return 0


# ─── Issue detectors ────────────────────────────────────────────────────────

def detect_bullets_after_categories(wikitext: str, headings: list) -> list[Issue]:
    """
    Detect `*` bullets that appear after the first [[Category:...]] line.
    """
    first_cat = _first_category_line(wikitext)
    if first_cat is None:
        return []

    # Find all * bullets in the footer region (after External links / last section)
    bullets = _find_bullets_in_region(wikitext, first_cat, len(wikitext))

    if bullets:
        return [Issue(
            type="bullet_after_categories",
            severity="error",
            position=bullets[0]["start"],
            description=f"{len(bullets)} * bullet(s) found after [[Category:...]]",
            details={"count": len(bullets), "bullets": bullets},
        )]
    return []


def detect_defaultsort_position(wikitext: str, headings: list) -> list[Issue]:
    """
    Detect {{DEFAULTSORT:...}} in wrong position.
    Correct: after all navboxes, before first category.
    Wrong: before navboxes, after categories, or before Authority control.
    """
    defaultsorts = _find_templates(wikitext, "DEFAULTSORT")
    if not defaultsorts:
        return []

    ds = defaultsorts[0]
    first_cat = _first_category_line(wikitext)
    issues = []

    # Check: DEFAULTSORT after first category?
    if first_cat and ds["start"] > first_cat:
        issues.append(Issue(
            type="defaultsort_position",
            severity="warning",
            position=ds["start"],
            description="{{DEFAULTSORT}} found after [[Category:...]] — should be before categories",
            details={"template": ds["text"]},
        ))
        return issues

    # Check: DEFAULTSORT before Authority control?
    auth_controls = _find_templates(wikitext, "Authority control")
    if auth_controls and ds["start"] < auth_controls[0]["start"]:
        issues.append(Issue(
            type="defaultsort_position",
            severity="info",
            position=ds["start"],
            description="{{DEFAULTSORT}} found before {{Authority control}}",
            details={"template": ds["text"]},
        ))
        return issues

    # Check: DEFAULTSORT before navboxes? (rough check: before last navbox-like template)
    navboxes = _find_templates(wikitext, "Navbox", "Navbox with collapsible groups", "Navbox subgroup")
    if navboxes and ds["start"] < navboxes[-1]["start"]:
        issues.append(Issue(
            type="defaultsort_position",
            severity="info",
            position=ds["start"],
            description="{{DEFAULTSORT}} found before navboxes",
            details={"template": ds["text"]},
        ))
        return issues

    return issues


def detect_section_spacing(wikitext: str, headings: list) -> list[Issue]:
    """
    Detect missing blank lines between sections.
    Two consecutive headings or a heading immediately followed by content
    with no blank line.
    """
    issues = []
    for i, h in enumerate(headings):
        # Check: blank line between this heading and the next?
        if i + 1 < len(headings):
            gap = wikitext[h["end"]:headings[i + 1]["start"]]
            # Count substantive content lines (non-whitespace, non-newline)
            content_lines = [l for l in gap.split('\n') if l.strip() and not l.strip().startswith('{{')]
            if not content_lines:
                # No substantive content between headings — just whitespace.
                # Count newlines to check if there's a blank line.
                newlines = gap.count('\n')
                if newlines < 2:
                    # Headings are on adjacent lines or one line apart
                    issues.append(Issue(
                        type="section_spacing",
                        severity="info",
                        position=headings[i + 1]["start"],
                        description=f"No blank line between \"{h['title']}\" and \"{headings[i + 1]['title']}\"",
                        details={"before": h["title"], "after": headings[i + 1]["title"]},
                    ))

    # Check: heading immediately followed by content with no blank line
    for h in headings:
        after_heading = wikitext[h["end"]:h["end"] + 100]
        lines = after_heading.split('\n')
        if len(lines) >= 2 and lines[1].strip():
            # Content on the very next line after the heading
            # This is OK for template-based sections but less ideal for text
            pass  # Too many false positives — skip for now

    return issues


def detect_auth_control_position(wikitext: str, headings: list) -> list[Issue]:
    """
    Detect {{Authority control}} not in standard position.
    Correct: after all navboxes, before DEFAULTSORT and categories.
    """
    auth_controls = _find_templates(wikitext, "Authority control")
    if not auth_controls:
        return []

    ac = auth_controls[0]
    first_cat = _first_category_line(wikitext)
    issues = []

    # Check: after first category?
    if first_cat and ac["start"] > first_cat:
        issues.append(Issue(
            type="auth_control_position",
            severity="info",
            position=ac["start"],
            description="{{Authority control}} found after [[Category:...]]",
            details={"template": ac["text"]},
        ))
        return issues

    # Check: before navboxes?
    navboxes = _find_templates(wikitext, "Navbox", "Navbox with collapsible groups", "Navbox subgroup")
    if navboxes and ac["start"] < navboxes[-1]["end"]:
        # Authority control is mixed in with navboxes — that's actually common and acceptable
        pass

    return issues


def detect_stub_position(wikitext: str, headings: list) -> list[Issue]:
    """
    Detect {{...-stub}} templates not at the very end of the article.
    Stubs should be after the last category.
    """
    stubs = _find_templates(wikitext, "[A-Z][a-zA-Z]*-stub")
    if not stubs:
        return []

    last_cat_end = _last_category_end(wikitext)
    issues = []
    for stub in stubs:
        if last_cat_end and stub["start"] < last_cat_end:
            issues.append(Issue(
                type="stub_position",
                severity="info",
                position=stub["start"],
                description=f"Stub template found before last category",
                details={"template": stub["text"]},
            ))
            break  # One issue per article is enough

    return issues


def detect_whitespace_issues(wikitext: str, headings: list) -> list[Issue]:
    """
    Detect 3+ consecutive blank lines and trailing blank lines.
    """
    issues = []

    # Find 3+ consecutive blank lines
    for m in re.finditer(r'\n\n\n\n+', wikitext):
        issues.append(Issue(
            type="whitespace_cleanup",
            severity="info",
            position=m.start(),
            description=f"{len(m.group()) - 1} consecutive blank lines at position {m.start()}",
            details={"count": len(m.group()) - 1},
        ))
        break  # Report once

    # Trailing blank lines
    tail = wikitext.rstrip('\n')
    if len(tail) < len(wikitext) and len(wikitext) - len(tail) > 1:
        issues.append(Issue(
            type="whitespace_cleanup",
            severity="info",
            position=len(tail),
            description=f"{len(wikitext) - len(tail)} trailing blank lines",
            details={"count": len(wikitext) - len(tail)},
        ))

    return issues


# ─── Public API ────────────────────────────────────────────────────────────

def analyze_footer(wikitext: str) -> list[Issue]:
    """
    Analyze the footer region of a Wikipedia article for structural issues.

    Args:
        wikitext: The full wikitext of the article.

    Returns:
        A list of Issue objects, sorted by position.
    """
    if not wikitext or not wikitext.strip():
        return []

    headings = get_headings(wikitext)

    detectors = [
        detect_whitespace_issues,
        detect_section_spacing,
        detect_section_order,
        detect_bullets_after_categories,
        detect_stub_position,
        detect_auth_control_position,
        detect_defaultsort_position,
    ]

    all_issues = []
    for detector in detectors:
        try:
            all_issues.extend(detector(wikitext, headings))
        except Exception as e:
            # Don't let one detector fail the whole analysis
            all_issues.append(Issue(
                type="detector_error",
                severity="info",
                position=0,
                description=f"Detector {detector.__name__} failed: {e}",
            ))

    # Sort by position
    all_issues.sort(key=lambda i: i.position)
    return all_issues
