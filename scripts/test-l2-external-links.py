#!/usr/bin/env python3
"""
Test suite for L2 external links insertion (build_external_link_wikitext).

Full reference: docs/L2-EXTERNAL-LINKS.md - algorithm, architecture, CLI.
Keep that doc in sync when changing this file.

All tests are offline - no API calls, no mocking needed. The pure function
build_external_link_wikitext() takes wikitext in, returns wikitext out.

Run:
    python3 scripts/test-l2-external-links.py
    python3 scripts/test-l2-external-links.py -v    # verbose
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import importlib.util
spec = importlib.util.spec_from_file_location(
    "contribution_protocol",
    os.path.join(os.path.dirname(__file__), "contribution-protocol.py")
)
proto = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proto)


# ─── Helpers ────────────────────────────────────────────────────────────────

def has_external_links_section(wikitext):
    """Check if == External links == section exists."""
    import re
    return bool(re.search(r'==\s*External links\s*==', wikitext, re.IGNORECASE))

def find_section(wikitext, name):
    """Find a section by name in wikitext."""
    import re
    pattern = rf'==\s*{re.escape(name)}\s*=='
    return bool(re.search(pattern, wikitext, re.IGNORECASE))


# ─── Fixtures ───────────────────────────────────────────────────────────────

ARTICLE_WITH_EXT_LINKS = """'''Quantum mechanics''' is a fundamental theory in physics...

== History ==
The history of quantum mechanics began...

== See also ==
* [[Wave function]]
* [[Schrodinger equation]]

== External links ==
{{Commons category|Quantum mechanics}}
* {{cite web |url=https://plato.stanford.edu/entries/qm/ |title=Quantum Mechanics |publisher=Stanford Encyclopedia of Philosophy}}

== References ==
{{Reflist}}

{{Authority control}}
[[Category:Quantum mechanics]]
"""

ARTICLE_WITH_FURTHER_READING = """'''Algorithm''' is a sequence of well-defined instructions...

== Overview ==
Algorithms are fundamental...

== Further reading ==
* {{cite book |title=Introduction to Algorithms |author=CLRS |year=2009}}
* {{cite web |url=https://example.com/algo |title=Algorithms |publisher=Example Press}}

== References ==
{{Reflist}}
"""

ARTICLE_NO_EXT_LINKS_HAS_REFS = """'''Deep learning''' is a subset of machine learning...

== History ==
Deep learning emerged...

== References ==
{{Reflist}}

[[Category:Deep learning]]
"""

ARTICLE_NO_EXT_LINKS_NO_REFS = """'''Artificial intelligence''' is intelligence demonstrated by machines...

== History ==
AI research began...

== Approaches ==
Various approaches include...

[[Category:Artificial intelligence]]
"""

ARTICLE_WITH_SEE_ALSO_NO_REFS = """'''Climate change''' refers to long-term shifts...

== Causes ==
Burning fossil fuels...

== See also ==
* [[Global warming]]
* [[Greenhouse effect]]
"""

ARTICLE_EMPTY = ""

ARTICLE_MINIMAL = """'''Test''' is a test article.

== Overview ==
This is a test.
"""

ARTICLE_EXT_LINKS_AT_END = """'''Test article''' for research purposes.

== Content ==
Some content here.

== External links ==
* {{cite web |url=https://example.com |title=Example Link}}
"""

ARTICLE_EXT_LINKS_LAST_WITH_NAV = """'''Test article''' for navbox/category placement.

== Content ==
Some content here.

== External links ==
* {{cite web |url=https://example.com |title=Existing Link}}

{{Navbox}}
[[Category:Test]]
"""

ARTICLE_EXT_LINKS_MULTIPLE_SECTIONS = """'''Physics''' is the natural science...

== Mechanics ==
Classical mechanics...

== External links ==
* [https://physics.example.com Physics resources]

== Thermodynamics ==
Thermodynamics deals with heat...

== References ==
{{Reflist}}
"""

ARTICLE_WITH_DUPLICATE_URL = """'''Machine learning''' is...

== External links ==
* {{cite web |url=https://ocw.mit.edu/courses/6-006/ |title=MIT 6.006 |publisher=MIT OCW}}

== References ==
{{Reflist}}
"""

ARTICLE_BOTH_SECTIONS = """'''Test article''' with both sections.

== Overview ==
Test.

== Further reading ==
* Existing FR

== External links ==
* Existing EL

== References ==
{{Reflist}}
"""

ARTICLE_WITH_NOTES = """'''Test article.'''

== History ==
Content.

== Notes ==
{{Reflist}}
"""


# ─── Tests: Append to existing ─────────────────────────────────────────────

class TestAppendExisting(unittest.TestCase):
    """Tests where == External links == or == Further reading == exists."""

    def test_append_to_external_links(self):
        """Should append bullet at end of External links section."""
        result = proto.build_external_link_wikitext(
            ARTICLE_WITH_EXT_LINKS,
            url="https://ocw.mit.edu/courses/6-006/",
            title="Introduction to Algorithms",
            publisher="MIT OpenCourseWare",
            description="Full course with video lectures and problem sets.",
        )
        self.assertEqual(result["action"], "append")
        self.assertIn("External links", result["section"])
        self.assertIn("{{cite web |url=https://ocw.mit.edu/courses/6-006/", result["wikitext"])
        self.assertIn("Introduction to Algorithms", result["wikitext"])
        self.assertIn("MIT OpenCourseWare", result["wikitext"])
        self.assertIn("Full course with video lectures and problem sets.", result["wikitext"])

    def test_append_preserves_existing_content(self):
        """Existing external links and Commons category should remain."""
        result = proto.build_external_link_wikitext(
            ARTICLE_WITH_EXT_LINKS,
            url="https://example.com/new",
            title="New Resource",
        )
        self.assertIn("Stanford Encyclopedia of Philosophy", result["wikitext"])
        self.assertIn("{{Commons category|Quantum mechanics}}", result["wikitext"])
        self.assertIn("[[Wave function]]", result["wikitext"])
        self.assertIn("== References ==", result["wikitext"])

    def test_append_to_further_reading(self):
        """Should recognize == Further reading == as a valid target."""
        result = proto.build_external_link_wikitext(
            ARTICLE_WITH_FURTHER_READING,
            url="https://example.com/new",
            title="New Resource",
        )
        self.assertEqual(result["action"], "append")
        self.assertIn("Further reading", result["section"])
        self.assertIn("Introduction to Algorithms", result["wikitext"])

    def test_append_places_before_next_section(self):
        """New bullet should be before the next heading (References)."""
        result = proto.build_external_link_wikitext(
            ARTICLE_WITH_EXT_LINKS,
            url="https://example.com/new",
            title="New Resource",
        )
        new_pos = result["wikitext"].find("New Resource")
        refs_pos = result["wikitext"].find("== References ==")
        self.assertLess(new_pos, refs_pos)

    def test_append_at_end_when_no_next_section(self):
        """When External links is last section, append at end of page."""
        result = proto.build_external_link_wikitext(
            ARTICLE_EXT_LINKS_AT_END,
            url="https://example.com/new",
            title="New Resource",
        )
        self.assertEqual(result["action"], "append")
        self.assertIn("New Resource", result["wikitext"])

    def test_append_before_navboxes_and_categories(self):
        """When External links is last section with trailing navboxes/categories,
        the new bullet should go after the last * but before navboxes/categories."""
        result = proto.build_external_link_wikitext(
            ARTICLE_EXT_LINKS_LAST_WITH_NAV,
            url="https://ocw.mit.edu/courses/6-006/",
            title="Introduction to Algorithms",
            publisher="MIT OpenCourseWare",
            description="Full course.",
        )
        self.assertEqual(result["action"], "append")
        wt = result["wikitext"]
        # The new bullet should appear after the existing bullet
        self.assertGreater(wt.find("Introduction to Algorithms"), wt.find("Existing Link"))
        # The new bullet should appear BEFORE navboxes and categories
        self.assertLess(wt.find("Introduction to Algorithms"), wt.find("{{Navbox"))
        self.assertLess(wt.find("Introduction to Algorithms"), wt.find("[[Category:Test]]"))
        # Existing navbox and category should still be present
        self.assertIn("{{Navbox}}", wt)
        self.assertIn("[[Category:Test]]", wt)

    def test_append_without_description(self):
        """Description is optional."""
        result = proto.build_external_link_wikitext(
            ARTICLE_WITH_EXT_LINKS,
            url="https://example.com/ref",
            title="Just a Title",
        )
        self.assertIn("* {{cite web |url=https://example.com/ref |title=Just a Title}}", result["wikitext"])
        self.assertNotIn(" - ", result["wikitext"].split("\n* {{cite web |url=https://example.com/ref |title=Just a Title}}")[0])

    def test_append_without_publisher(self):
        """Publisher is optional."""
        result = proto.build_external_link_wikitext(
            ARTICLE_WITH_EXT_LINKS,
            url="https://example.com/ref",
            title="No Publisher",
        )
        self.assertIn("* {{cite web |url=https://example.com/ref |title=No Publisher}}", result["wikitext"])


# ─── Tests: Prefers External links over Further reading ────────────────────

class TestPreference(unittest.TestCase):
    """Both sections exist - should prefer External links."""

    def test_prefers_external_links(self):
        """When both sections exist, append to External links."""
        result = proto.build_external_link_wikitext(
            ARTICLE_BOTH_SECTIONS,
            url="https://example.com/new",
            title="New Resource",
        )
        self.assertEqual(result["action"], "append")
        self.assertEqual(result["section"], "External links")


# ─── Tests: Create new section ─────────────────────────────────────────────

class TestCreateNew(unittest.TestCase):
    """Tests where no External links / Further reading exists."""

    def test_create_after_references(self):
        """When References exists, create External links after it (per WP:LAYOUT)."""
        result = proto.build_external_link_wikitext(
            ARTICLE_NO_EXT_LINKS_HAS_REFS,
            url="https://ocw.mit.edu/courses/6-006/",
            title="Introduction to Algorithms",
            publisher="MIT OpenCourseWare",
            description="Full course.",
        )
        self.assertEqual(result["action"], "create")
        self.assertIn("External links", result["section"])
        self.assertIn("References", result["detail"])
        self.assertTrue(has_external_links_section(result["wikitext"]))

        el_pos = result["wikitext"].lower().find("external links")
        ref_pos = result["wikitext"].lower().find("references")
        # External links should come AFTER References per WP:LAYOUT
        self.assertGreater(el_pos, ref_pos)

    def test_create_after_see_also(self):
        """With See also (but no References), create External links after See also."""
        result = proto.build_external_link_wikitext(
            ARTICLE_WITH_SEE_ALSO_NO_REFS,
            url="https://example.com/ref",
            title="Test Resource",
        )
        self.assertEqual(result["action"], "create")
        self.assertIn("See also", result["detail"])

        el_pos = result["wikitext"].lower().find("external links")
        sa_pos = result["wikitext"].lower().find("see also")
        # External links should come AFTER See also (per WP:LAYOUT)
        self.assertGreater(el_pos, sa_pos)

    def test_create_at_end_when_no_refs_or_see_also(self):
        """When neither References nor See also exists, append at end."""
        result = proto.build_external_link_wikitext(
            ARTICLE_NO_EXT_LINKS_NO_REFS,
            url="https://example.com/ref",
            title="Test Resource",
        )
        self.assertEqual(result["action"], "create")
        self.assertIn("appended", result["detail"].lower())
        self.assertTrue(has_external_links_section(result["wikitext"]))

    def test_create_minimal_article(self):
        """Should work on a minimal article."""
        result = proto.build_external_link_wikitext(
            ARTICLE_MINIMAL,
            url="https://example.com/ref",
            title="Test Resource",
        )
        self.assertEqual(result["action"], "create")
        self.assertTrue(has_external_links_section(result["wikitext"]))
        self.assertIn("Test Resource", result["wikitext"])

    def test_create_empty_article(self):
        """Completely empty article - should still create section."""
        result = proto.build_external_link_wikitext(
            ARTICLE_EMPTY,
            url="https://example.com/ref",
            title="Test Resource",
        )
        self.assertEqual(result["action"], "create")
        self.assertTrue(has_external_links_section(result["wikitext"]))

    def test_create_preserves_existing_sections(self):
        """Creating a new section should not modify existing content."""
        result = proto.build_external_link_wikitext(
            ARTICLE_NO_EXT_LINKS_HAS_REFS,
            url="https://example.com/ref",
            title="Test Resource",
            description="A description.",
        )
        self.assertIn("== History ==", result["wikitext"])
        self.assertIn("{{Reflist}}", result["wikitext"])
        self.assertIn("[[Category:Deep learning]]", result["wikitext"])

    def test_notes_treated_as_reference(self):
        """== Notes == should also trigger create-after-references behavior."""
        result = proto.build_external_link_wikitext(
            ARTICLE_WITH_NOTES,
            url="https://example.com/ref",
            title="Test Resource",
        )
        self.assertEqual(result["action"], "create")
        self.assertIn("References", result["detail"])

    def test_create_after_references_with_navboxes(self):
        """External links should appear between References and navboxes."""
        wikitext = """Content.

== See also ==
* [[A]]

== References ==
{{reflist|30em}}

{{Navbox}}
{{Authority control}}

[[Category:Test]]
"""
        result = proto.build_external_link_wikitext(
            wikitext,
            url="https://ocw.mit.edu/courses/test/",
            title="Test Course",
            publisher="MIT OCW",
        )
        wt = result["wikitext"]
        ref_pos = wt.find("== References ==")
        el_pos = wt.find("== External links ==")
        nav_pos = wt.find("{{Navbox}}")
        cat_pos = wt.find("[[Category:Test]]")
        self.assertGreater(el_pos, ref_pos, "External links should be after References")
        self.assertLess(el_pos, nav_pos, "External links should be before navboxes")
        self.assertLess(nav_pos, cat_pos, "Navboxes should be before categories")

    def test_create_only_see_also_no_refs(self):
        """With See also but no References, create after See also."""
        wikitext = """Content.

== See also ==
* [[A]]

[[Category:Test]]
"""
        result = proto.build_external_link_wikitext(
            wikitext,
            url="https://example.com/ref",
            title="Test",
        )
        self.assertEqual(result["action"], "create")
        wt = result["wikitext"]
        sa_pos = wt.find("== See also ==")
        el_pos = wt.find("== External links ==")
        cat_pos = wt.find("[[Category:Test]]")
        self.assertGreater(el_pos, sa_pos, "External links should be after See also")
        self.assertLess(el_pos, cat_pos, "External links should be before categories")

    def test_append_to_further_reading_when_available(self):
        """When Further reading exists, the link is appended there (not a new section)."""
        wikitext = """Content.

== References ==
{{reflist}}

== Further reading ==
* [[Book]]

{{Navbox}}
[[Category:Test]]
"""
        result = proto.build_external_link_wikitext(
            wikitext,
            url="https://example.com/ref",
            title="Test",
        )
        self.assertEqual(result["action"], "append")
        self.assertIn("Further reading", str(result.get("section", "")))
        self.assertIn("Further reading", result.get("detail", ""))

    def test_create_only_references_no_see_also(self):
        """With References but no See also, create after References."""
        wikitext = """Content.

== References ==
{{reflist}}

[[Category:Test]]
"""
        result = proto.build_external_link_wikitext(
            wikitext,
            url="https://example.com/ref",
            title="Test",
        )
        self.assertEqual(result["action"], "create")
        wt = result["wikitext"]
        ref_pos = wt.find("== References ==")
        el_pos = wt.find("== External links ==")
        cat_pos = wt.find("[[Category:Test]]")
        self.assertGreater(el_pos, ref_pos, "External links should be after References")
        self.assertLess(el_pos, cat_pos, "External links should be before categories")

    def test_create_with_subheadings_in_references(self):
        """References with level-3 sub-headings should still work."""
        wikitext = """Content.

== See also ==
* [[A]]

== References ==
=== Primary sources ===
{{reflist}}

=== Secondary sources ===
* Some book

{{Navbox}}
[[Category:Test]]
"""
        result = proto.build_external_link_wikitext(
            wikitext,
            url="https://example.com/ref",
            title="Test",
        )
        self.assertEqual(result["action"], "create")
        wt = result["wikitext"]
        ref_pos = wt.find("== References ==")
        el_pos = wt.find("== External links ==")
        nav_pos = wt.find("{{Navbox}}")
        self.assertGreater(el_pos, ref_pos, "External links should be after References")
        self.assertLess(el_pos, nav_pos, "External links should be before navboxes")


# ─── Tests: Edit summary ───────────────────────────────────────────────────

class TestEditSummary(unittest.TestCase):
    """Edit summaries should follow Wikipedia conventions."""

    def test_append_summary(self):
        result = proto.build_external_link_wikitext(
            ARTICLE_WITH_EXT_LINKS,
            url="https://example.com/ref",
            title="My Resource",
        )
        self.assertIn("External links", result["summary"])
        self.assertIn("My Resource", result["summary"])

    def test_create_summary(self):
        result = proto.build_external_link_wikitext(
            ARTICLE_NO_EXT_LINKS_HAS_REFS,
            url="https://example.com/ref",
            title="My Resource",
        )
        self.assertIn("External links", result["summary"])
        self.assertIn("Wiki MIT", result["summary"])


# ─── Tests: Idempotency ────────────────────────────────────────────────────

class TestIdempotency(unittest.TestCase):
    """Running the function twice should produce consistent results."""

    def test_idempotent_append(self):
        """Appending twice: second run adds another bullet."""
        first = proto.build_external_link_wikitext(
            ARTICLE_WITH_EXT_LINKS,
            url="https://example.com/ref-a",
            title="Ref A",
        )
        second = proto.build_external_link_wikitext(
            first["wikitext"],
            url="https://example.com/ref-b",
            title="Ref B",
        )
        self.assertEqual(second["action"], "append")
        self.assertIn("Ref A", second["wikitext"])
        self.assertIn("Ref B", second["wikitext"])

    def test_idempotent_same_url(self):
        """Inserting same URL twice: second still adds it (dedup is in orchestrator)."""
        first = proto.build_external_link_wikitext(
            ARTICLE_WITH_EXT_LINKS,
            url="https://example.com/same-ref",
            title="Same Ref",
        )
        second = proto.build_external_link_wikitext(
            first["wikitext"],
            url="https://example.com/same-ref",
            title="Same Ref",
        )
        self.assertEqual(second["action"], "append")


# ─── Tests: OCW wrapper ────────────────────────────────────────────────────

class TestOCWFormat(unittest.TestCase):
    """Tests that the OCW formatting matches L2 convention."""

    def test_ocw_format_publisher(self):
        """Should use MIT OpenCourseWare as publisher."""
        result = proto.build_external_link_wikitext(
            ARTICLE_MINIMAL,
            url="https://ocw.mit.edu/courses/6-006/",
            title="Introduction to Algorithms",
            publisher="MIT OpenCourseWare",
            description="Full course with video lectures.",
        )
        self.assertIn("MIT OpenCourseWare", result["wikitext"])
        self.assertIn("Introduction to Algorithms", result["wikitext"])

    def test_cite_web_bullet_format(self):
        """Link should be a bulleted {{cite web}} - standard WP:EL convention."""
        result = proto.build_external_link_wikitext(
            ARTICLE_WITH_EXT_LINKS,
            url="https://example.com/ref",
            title="Standard Format",
            publisher="Standard Press",
            description="A description.",
        )
        self.assertIn("* {{cite web |url=https://example.com/ref |title=Standard Format |publisher=Standard Press}}", result["wikitext"])


# ─── Tests: Edge cases ─────────────────────────────────────────────────────

class TestEdgeCases(unittest.TestCase):
    """Special characters, formatting, weird wikitext."""

    def test_special_chars_in_title(self):
        """Ampersands, quotes in titles should be preserved."""
        result = proto.build_external_link_wikitext(
            ARTICLE_WITH_EXT_LINKS,
            url="https://example.com/ref",
            title='Chemistry & Physics: A "Deep Dive"',
        )
        self.assertIn('Chemistry & Physics: A "Deep Dive"', result["wikitext"])

    def test_does_not_modify_intro(self):
        """Introduction and body sections should remain untouched."""
        result = proto.build_external_link_wikitext(
            ARTICLE_WITH_EXT_LINKS,
            url="https://example.com/new",
            title="New Resource",
        )
        self.assertIn("'''Quantum mechanics''' is a fundamental theory", result["wikitext"])
        self.assertIn("The history of quantum mechanics began", result["wikitext"])

    def test_multiple_sections_after_ext_links(self):
        """External links followed by another content section then References."""
        result = proto.build_external_link_wikitext(
            ARTICLE_EXT_LINKS_MULTIPLE_SECTIONS,
            url="https://example.com/new",
            title="New Resource",
        )
        self.assertEqual(result["action"], "append")
        new_pos = result["wikitext"].find("New Resource")
        thermo_pos = result["wikitext"].find("Thermodynamics")
        self.assertLess(new_pos, thermo_pos)

    def test_refs_with_sub_headings_in_ext_links(self):
        """Article where External links has sub-sections (===)."""
        article = """'''Test article.'''

== Overview ==
Test.

== External links ==
* Link 1

=== Sub section ===
* Link 2
"""
        result = proto.build_external_link_wikitext(
            article,
            url="https://example.com/new",
            title="New Resource",
        )
        # Should still append (at end of page since no next == heading)
        self.assertEqual(result["action"], "append")
        self.assertIn("New Resource", result["wikitext"])


if __name__ == "__main__":
    unittest.main()
