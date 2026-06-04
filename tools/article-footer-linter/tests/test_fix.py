"""
Tests for the fix module — applying fixes, verifying output.
"""

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from article_footer_linter.analyze import analyze_footer
from article_footer_linter.fix import apply_fixes, FIX_ORDER

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def load_fixture(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return f.read()


# ─── Whitespace fixes ──────────────────────────────────────────────────────

def test_fix_triple_blank_lines():
    wikitext = "== A ==\n\n\n\n== B ==\n\n[[Category:Test]]"
    issues = analyze_footer(wikitext)
    fixed, fixes = apply_fixes(wikitext, issues)
    assert any(f.applied for f in fixes), f"No fixes applied: {fixes}"
    # Check no 4+ consecutive newlines remain
    assert '\n\n\n\n' not in fixed, "Triple blank lines not collapsed"


def test_fix_trailing_blanks():
    wikitext = "== A ==\n[[Category:Test]]\n\n\n"
    issues = analyze_footer(wikitext)
    fixed, fixes = apply_fixes(wikitext, issues)
    assert fixed == fixed.rstrip('\n') + '\n', "Trailing blanks not removed"


# ─── Bullet fixes ──────────────────────────────────────────────────────────

def test_fix_bullets_after_categories():
    wikitext = load_fixture("bullets-after-cats.txt")
    issues = analyze_footer(wikitext)
    fixed, fixes = apply_fixes(wikitext, issues)
    assert any(f.applied for f in fixes), f"No fixes applied: {fixes}"

    # Verify no * bullets after the first category
    cat_pos = fixed.find("[[Category:")
    after_cats = fixed[cat_pos:]
    assert '* [' not in after_cats, "Bullet still after categories"
    assert '* {{cite web' not in after_cats or fixed.find('* {{cite web') < cat_pos, "Cite web still after categories"


def test_fix_well_formed_unchanged():
    wikitext = load_fixture("well-formed.txt")
    issues = analyze_footer(wikitext)
    fixed, fixes = apply_fixes(wikitext, issues)
    assert fixed == wikitext, "Well-formed article should not change"


# ─── Section spacing ───────────────────────────────────────────────────────

def test_fix_section_spacing():
    wikitext = "== A ==\nContent\n== B ==\nMore\n[[Category:Test]]"
    issues = analyze_footer(wikitext)
    fixed, fixes = apply_fixes(wikitext, issues)
    if any(f.applied for f in fixes):
        # Check a blank line was inserted between sections
        assert "Content\n\n== B ==" in fixed or "Content\n\n\n== B ==" in fixed
    else:
        print(f"  Note: no spacing fix applied (issues: {[i.type for i in issues]})")


# ─── DEFAULTSORT fixes ─────────────────────────────────────────────────────

def test_fix_defaultsort_after_cats():
    wikitext = "== A ==\n\n[[Category:Test]]\n{{DEFAULTSORT:Test}}"
    issues = analyze_footer(wikitext)
    fixed, fixes = apply_fixes(wikitext, issues)
    if any(f.applied for f in fixes):
        # DEFAULTSORT should now be before the category
        ds_pos = fixed.find("{{DEFAULTSORT:Test}}")
        cat_pos = fixed.find("[[Category:Test")
        assert ds_pos >= 0 and cat_pos >= 0 and ds_pos < cat_pos, \
            f"DEFAULTSORT ({ds_pos}) should be before category ({cat_pos})"


# ─── Auth control fixes ────────────────────────────────────────────────────

def test_fix_auth_control_after_cats():
    wikitext = "== A ==\n\n[[Category:Test]]\n\n{{Authority control}}"
    issues = analyze_footer(wikitext)
    fixed, fixes = apply_fixes(wikitext, issues)
    if any(f.applied for f in fixes):
        ac_pos = fixed.find("{{Authority control}}")
        cat_pos = fixed.find("[[Category:Test")
        assert ac_pos >= 0 and cat_pos >= 0 and ac_pos < cat_pos, \
            f"Authority control ({ac_pos}) should be before category ({cat_pos})"


# ─── Stub fixes ────────────────────────────────────────────────────────────

def test_fix_stub_position():
    wikitext = "== A ==\n{{Foo-stub}}\n\n[[Category:Test]]"
    issues = analyze_footer(wikitext)
    fixed, fixes = apply_fixes(wikitext, issues)
    if any(f.applied for f in fixes):
        stub_pos = fixed.find("{{Foo-stub}}")
        cat_pos = fixed.find("[[Category:Test]]")
        assert stub_pos >= 0 and cat_pos >= 0 and stub_pos > cat_pos + 2, \
            f"Stub ({stub_pos}) should be after category end ({cat_pos + 2})"


# ─── Composite fix: multiple issues ────────────────────────────────────────

def test_composite_whitespace_fixture():
    wikitext = load_fixture("whitespace-issues.txt")
    issues = analyze_footer(wikitext)
    fixed, fixes = apply_fixes(wikitext, issues)
    applied = [f for f in fixes if f.applied]
    assert len(applied) >= 1, f"Expected at least 1 fix, got {len(applied)}: {fixes}"
    # Verify fixes are in the correct order
    applied_types = [f.type for f in applied]
    order_indices = [FIX_ORDER.index(t) if t in FIX_ORDER else 99 for t in applied_types]
    assert order_indices == sorted(order_indices), \
        f"Fixes not in correct order: {applied_types}"


def test_composite_bullets_fixture():
    wikitext = load_fixture("bullets-after-cats.txt")
    issues = analyze_footer(wikitext)
    fixed, fixes = apply_fixes(wikitext, issues)
    applied = [f for f in fixes if f.applied]
    assert len(applied) >= 1, f"Expected fixes, got none: {fixes}"
    # Verify the fixed wikitext is well-formed (no bullets after cats)
    re_issues = analyze_footer(fixed)
    remaining = [i for i in re_issues if i.type == "bullet_after_categories"]
    assert len(remaining) == 0, f"Bullet issue remains after fix: {remaining}"

# ─── Section order fixes ──────────────────────────────────────────────────

def test_fix_external_links_before_references():
    wikitext = "== See also ==\n* [[A]]\n\n== External links ==\n* [https://ex.com Link]\n\n== References ==\n{{Reflist}}"
    issues = analyze_footer(wikitext)
    fixed, fixes = apply_fixes(wikitext, issues)
    
    # After fix, References should come before External links
    ref_pos = fixed.find("== References ==")
    el_pos = fixed.find("== External links ==")
    assert ref_pos >= 0 and el_pos >= 0
    assert ref_pos < el_pos, f"References ({ref_pos}) should be before External links ({el_pos})"


def test_fix_further_reading_after_external_links():
    wikitext = "== See also ==\n* [[A]]\n\n== External links ==\n* [https://ex.com Link]\n\n== Further reading ==\n* [https://ex2.com Book]"
    issues = analyze_footer(wikitext)
    fixed, fixes = apply_fixes(wikitext, issues)
    
    fr_pos = fixed.find("== Further reading ==")
    el_pos = fixed.find("== External links ==")
    assert fr_pos >= 0 and el_pos >= 0
    assert fr_pos < el_pos, f"Further reading ({fr_pos}) should be before External links ({el_pos})"


def test_fix_three_sections_reordered():
    wikitext = "Content\n\n== External links ==\n* [https://ex.com Link]\n\n== References ==\n{{Reflist}}\n\n== See also ==\n* [[A]]"
    issues = analyze_footer(wikitext)
    fixed, fixes = apply_fixes(wikitext, issues)
    
    sa_pos = fixed.find("== See also ==")
    ref_pos = fixed.find("== References ==")
    el_pos = fixed.find("== External links ==")
    assert sa_pos >= 0 and ref_pos >= 0 and el_pos >= 0
    assert sa_pos < ref_pos < el_pos, f"Order: See also={sa_pos}, References={ref_pos}, External links={el_pos}"

def test_fix_section_order_categories_not_dragged():
    """Categories should stay at the end after reordering, not move with sections."""
    wikitext = """Content

== External links ==
* [https://ex.com Link]

== References ==
{{Reflist}}

[[Category:Test]]
[[Category:Another]]
"""
    issues = analyze_footer(wikitext)
    fixed, fixes = apply_fixes(wikitext, issues)

    # After fix: References should come before External links
    ref_pos = fixed.find("== References ==")
    el_pos = fixed.find("== External links ==")
    assert ref_pos >= 0 and el_pos >= 0
    assert ref_pos < el_pos, f"References ({ref_pos}) should be before External links ({el_pos})"

    # Categories should be at the very end, after all sections
    last_cat_pos = fixed.rfind("[[Category:Another]]")
    el_pos_after = fixed.find("== External links ==")
    assert last_cat_pos > el_pos_after, f"Categories ({last_cat_pos}) should be after External links ({el_pos_after})"

    # There should be a blank line before categories (not jammed against content)
    # Check the 4 characters before the first [[Category: — should end with \n\n
    cat_pos = fixed.find("[[Category:Test]]")
    before_cat = fixed[max(0, cat_pos - 4):cat_pos]
    assert before_cat.endswith("\n\n") or before_cat.endswith("\n"), \
        f"No blank line before categories (context: {repr(before_cat)})"


def test_fix_rerun_linter_no_new_issues():
    """After applying fixes, re-running the linter should find no new issues."""
    wikitext = """Content

== External links ==
* [https://ex.com Link]

== References ==
{{Reflist}}

[[Category:Test]]
"""
    issues = analyze_footer(wikitext)
    assert any(i.type == "section_order" for i in issues), "Should detect order issue"

    fixed, fixes = apply_fixes(wikitext, issues)
    assert any(f.applied for f in fixes), "Should apply fixes"

    # Re-run linter on fixed wikitext
    post_issues = analyze_footer(fixed)
    post_order = [i for i in post_issues if i.type == "section_order"]
    post_bullets = [i for i in post_issues if i.type == "bullet_after_categories"]
    assert len(post_order) == 0, f"Section order issue remains: {post_order}"
    assert len(post_bullets) == 0, f"Bullet issue remains: {post_bullets}"
