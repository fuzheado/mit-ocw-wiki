"""
Tests for the analyze module — detection logic only, no fixes.
"""

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from article_footer_linter.analyze import (
    analyze_footer,
    detect_bullets_after_categories,
    detect_defaultsort_position,
    detect_section_spacing,
    detect_section_order,
    detect_auth_control_position,
    detect_stub_position,
    detect_whitespace_issues,
    get_headings,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def load_fixture(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return f.read()


# ─── Whitespace ────────────────────────────────────────────────────────────

def test_no_whitespace_issues_on_clean():
    wikitext = load_fixture("well-formed.txt")
    headings = get_headings(wikitext)
    issues = detect_whitespace_issues(wikitext, headings)
    assert len(issues) == 0, f"Expected 0 issues, got {len(issues)}: {issues}"


def test_whitespace_detects_triple_blank_lines():
    wikitext = "== A ==\n\n\n\n== B ==\n\n[[Category:Test]]"
    headings = get_headings(wikitext)
    issues = detect_whitespace_issues(wikitext, headings)
    assert any(i.type == "whitespace_cleanup" for i in issues)


def test_whitespace_detects_trailing_blanks():
    wikitext = "== A ==\nContent\n\n[[Category:Test]]\n\n\n"
    headings = get_headings(wikitext)
    issues = detect_whitespace_issues(wikitext, headings)
    assert any(i.type == "whitespace_cleanup" for i in issues)


# ─── Bullets after categories ──────────────────────────────────────────────

def test_no_bullets_after_cats_on_clean():
    wikitext = load_fixture("well-formed.txt")
    headings = get_headings(wikitext)
    issues = detect_bullets_after_categories(wikitext, headings)
    assert len(issues) == 0, f"Expected 0 issues, got {len(issues)}"


def test_detects_bullets_after_cats():
    wikitext = load_fixture("bullets-after-cats.txt")
    headings = get_headings(wikitext)
    issues = detect_bullets_after_categories(wikitext, headings)
    assert len(issues) == 1
    assert issues[0].type == "bullet_after_categories"
    assert issues[0].details["count"] == 2


def test_no_false_positive_bullet_in_section():
    wikitext = "== External links ==\n* [https://example.com Link]\n\n[[Category:Test]]"
    headings = get_headings(wikitext)
    issues = detect_bullets_after_categories(wikitext, headings)
    assert len(issues) == 0


# ─── DEFAULTSORT position ──────────────────────────────────────────────────

def test_no_defaultsort_issue_when_absent():
    wikitext = "== A ==\n\n[[Category:Test]]"
    headings = get_headings(wikitext)
    issues = detect_defaultsort_position(wikitext, headings)
    assert len(issues) == 0


def test_defaultsort_after_categories():
    wikitext = "== A ==\n\n[[Category:Test]]\n{{DEFAULTSORT:Test}}"
    headings = get_headings(wikitext)
    issues = detect_defaultsort_position(wikitext, headings)
    assert len(issues) == 1
    assert issues[0].type == "defaultsort_position"


def test_defaultsort_before_auth_control():
    wikitext = "== A ==\n{{DEFAULTSORT:Test}}\n{{Authority control}}\n\n[[Category:Test]]"
    headings = get_headings(wikitext)
    issues = detect_defaultsort_position(wikitext, headings)
    assert len(issues) >= 1
    assert any(i.type == "defaultsort_position" for i in issues)


# ─── Section spacing ───────────────────────────────────────────────────────

def test_no_spacing_issues_on_clean():
    wikitext = load_fixture("well-formed.txt")
    headings = get_headings(wikitext)
    issues = detect_section_spacing(wikitext, headings)
    assert len(issues) == 0, f"Expected 0 issues, got {len(issues)}"


def test_detects_missing_blank_between_sections():
    # Two headings stacked with no content and no blank line between them
    wikitext = "== A ==\n== B ==\n\n[[Category:Test]]"
    headings = get_headings(wikitext)
    issues = detect_section_spacing(wikitext, headings)
    assert len(issues) >= 1
    assert any(i.type == "section_spacing" for i in issues)


def test_no_false_positive_content_between_sections():
    # Sections with content between them are fine
    wikitext = "== A ==\nContent\n== B ==\nMore"
    headings = get_headings(wikitext)
    issues = detect_section_spacing(wikitext, headings)
    assert len([i for i in issues if i.type == "section_spacing"]) == 0


# ─── Authority control position ────────────────────────────────────────────

def test_auth_control_after_categories():
    wikitext = "== A ==\n\n[[Category:Test]]\n\n{{Authority control}}"
    headings = get_headings(wikitext)
    issues = detect_auth_control_position(wikitext, headings)
    assert len(issues) == 1
    assert issues[0].type == "auth_control_position"


def test_auth_control_in_correct_place():
    wikitext = "== A ==\n{{Navbox}}\n{{Authority control}}\n\n[[Category:Test]]"
    headings = get_headings(wikitext)
    issues = detect_auth_control_position(wikitext, headings)
    assert len(issues) == 0


# ─── Stub position ─────────────────────────────────────────────────────────

def test_stub_not_at_end():
    wikitext = "== A ==\n{{Foo-stub}}\n\n[[Category:Test]]"
    headings = get_headings(wikitext)
    issues = detect_stub_position(wikitext, headings)
    assert len(issues) == 1
    assert issues[0].type == "stub_position"


def test_stub_at_end_is_fine():
    wikitext = "== A ==\n\n[[Category:Test]]\n{{Foo-stub}}"
    headings = get_headings(wikitext)
    issues = detect_stub_position(wikitext, headings)
    assert len(issues) == 0


# ─── Smoke test: full analysis ─────────────────────────────────────────────

def test_full_analysis_well_formed():
    wikitext = load_fixture("well-formed.txt")
    issues = analyze_footer(wikitext)
    assert len(issues) == 0, f"Expected 0 issues for well-formed, got {len(issues)}: {issues}"


def test_full_analysis_bullets_after_cats():
    wikitext = load_fixture("bullets-after-cats.txt")
    issues = analyze_footer(wikitext)
    assert len(issues) >= 1
    types = [i.type for i in issues]
    assert "bullet_after_categories" in types


def test_full_analysis_whitespace():
    wikitext = load_fixture("whitespace-issues.txt")
    issues = analyze_footer(wikitext)
    assert len(issues) >= 1
    types = [i.type for i in issues]
    assert "whitespace_cleanup" in types or "section_spacing" in types


# ─── Section order ────────────────────────────────────────────────────────

def test_no_order_issue_when_correct():
    wikitext = "== See also ==\n* [[A]]\n\n== References ==\n{{Reflist}}\n\n== External links ==\n* [https://ex.com Link]"
    headings = get_headings(wikitext)
    issues = detect_section_order(wikitext, headings)
    assert len([i for i in issues if i.type == "section_order"]) == 0


def test_detects_external_links_before_references():
    wikitext = "== See also ==\n* [[A]]\n\n== External links ==\n* [https://ex.com Link]\n\n== References ==\n{{Reflist}}"
    headings = get_headings(wikitext)
    issues = detect_section_order(wikitext, headings)
    order_issues = [i for i in issues if i.type == "section_order"]
    assert len(order_issues) >= 1


def test_detects_further_reading_after_external_links():
    wikitext = "== See also ==\n* [[A]]\n\n== External links ==\n* [https://ex.com Link]\n\n== Further reading ==\n* [https://ex2.com Book]"
    headings = get_headings(wikitext)
    issues = detect_section_order(wikitext, headings)
    order_issues = [i for i in issues if i.type == "section_order"]
    assert len(order_issues) >= 1


def test_non_footer_sections_ignored():
    wikitext = "== See also ==\n* [[A]]\n\n== Custom section ==\nContent\n\n== External links ==\n* [https://ex.com Link]"
    headings = get_headings(wikitext)
    issues = detect_section_order(wikitext, headings)
    order_issues = [i for i in issues if i.type == "section_order"]
    # Custom section should not cause an order issue since it's not a footer section
    assert len(order_issues) == 0


def test_order_notes_references_external():
    wikitext = "== Notes ==\n{{Reflist}}\n\n== References ==\n{{Reflist}}\n\n== External links ==\n* [https://ex.com Link]"
    headings = get_headings(wikitext)
    issues = detect_section_order(wikitext, headings)
    order_issues = [i for i in issues if i.type == "section_order"]
    assert len(order_issues) == 0

# ─── Section order: comprehensive cases ────────────────────────────────────

def test_order_external_links_before_references():
    wikitext = "== External links ==\n* [https://ex.com Link]\n\n== References ==\n{{Reflist}}"
    headings = get_headings(wikitext)
    issues = detect_section_order(wikitext, headings)
    assert len([i for i in issues if i.type == "section_order"]) >= 1


def test_order_further_reading_after_external_links():
    wikitext = "== See also ==\n* [[A]]\n\n== External links ==\n* [https://ex.com Link]\n\n== Further reading ==\n* [https://ex2.com Book]"
    headings = get_headings(wikitext)
    issues = detect_section_order(wikitext, headings)
    order_issues = [i for i in issues if i.type == "section_order"]
    assert len(order_issues) >= 1


def test_order_correct_sequence_no_issues():
    wikitext = "== See also ==\n* [[A]]\n\n== References ==\n{{Reflist}}\n\n== Further reading ==\n* [https://ex.com Book]\n\n== External links ==\n* [https://ex.com Link]"
    headings = get_headings(wikitext)
    issues = detect_section_order(wikitext, headings)
    order_issues = [i for i in issues if i.type == "section_order"]
    assert len(order_issues) == 0


def test_order_see_also_after_references():
    wikitext = "== References ==\n{{Reflist}}\n\n== See also ==\n* [[A]]"
    headings = get_headings(wikitext)
    issues = detect_section_order(wikitext, headings)
    order_issues = [i for i in issues if i.type == "section_order"]
    assert len(order_issues) >= 1


def test_order_all_three_wrong():
    wikitext = "== External links ==\n* [https://ex.com A]\n\n== References ==\n{{Reflist}}\n\n== See also ==\n* [[A]]"
    headings = get_headings(wikitext)
    issues = detect_section_order(wikitext, headings)
    order_issues = [i for i in issues if i.type == "section_order"]
    assert len(order_issues) >= 2  # Two pairs out of order


def test_order_notes_and_references():
    wikitext = "== Notes ==\n{{Reflist}}\n\n== External links ==\n* [https://ex.com Link]\n\n== References ==\n{{Reflist}}"
    headings = get_headings(wikitext)
    issues = detect_section_order(wikitext, headings)
    order_issues = [i for i in issues if i.type == "section_order"]
    assert len(order_issues) >= 1


def test_order_custom_sections_ignored():
    wikitext = "== See also ==\n* [[A]]\n\n== Bibliography ==\n* [https://ex.com Book]\n\n== External links ==\n* [https://ex.com Link]"
    headings = get_headings(wikitext)
    issues = detect_section_order(wikitext, headings)
    order_issues = [i for i in issues if i.type == "section_order"]
    # Bibliography is not a recognized footer section, so no ordering issue
    assert len(order_issues) == 0


def test_order_only_one_footer_section():
    wikitext = "== References ==\n{{Reflist}}"
    headings = get_headings(wikitext)
    issues = detect_section_order(wikitext, headings)
    order_issues = [i for i in issues if i.type == "section_order"]
    assert len(order_issues) == 0


def test_order_correct_with_subheadings():
    wikitext = "== See also ==\n* [[A]]\n\n== References ==\n=== Primary ===\n{{Reflist}}\n\n== External links ==\n* [https://ex.com Link]"
    headings = get_headings(wikitext)
    issues = detect_section_order(wikitext, headings)
    order_issues = [i for i in issues if i.type == "section_order"]
    assert len(order_issues) == 0, f"Sub-headings should not trigger false positives: {order_issues}"
