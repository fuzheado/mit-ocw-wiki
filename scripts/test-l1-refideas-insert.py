#!/usr/bin/env python3
"""
Test suite for L1 refideas insertion (build_refideas_wikitext + l1_insert_refideas).

All tests are offline — no API calls, no mocking needed. The pure function
build_refideas_wikitext() takes wikitext in, returns wikitext out.

Run:
    python3 scripts/test-l1-refideas-insert.py
    python3 scripts/test-l1-refideas-insert.py -v    # verbose
"""

import sys
import os
import unittest

# Add scripts to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import importlib.util
spec = importlib.util.spec_from_file_location(
    "contribution_protocol",
    os.path.join(os.path.dirname(__file__), "contribution-protocol.py")
)
proto = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proto)


# ─── Helpers ────────────────────────────────────────────────────────────────

def insert(url="https://example.com/ref", label="Test Reference",
           source="Test Source", note=""):
    """Shorthand: call build_refideas_wikitext with defaults."""
    return proto.build_refideas_wikitext


def count_refideas_params(wikitext):
    """Count numbered parameters in the first {{refideas}} template."""
    import mwparserfromhell
    code = mwparserfromhell.parse(wikitext)
    tmpls = code.filter_templates(
        matches=lambda t: str(t.name).lower().strip() == "refideas"
    )
    if not tmpls:
        return 0
    count = 0
    for p in tmpls[0].params:
        try:
            int(str(p.name).strip())
            count += 1
        except ValueError:
            pass
    return count


def has_refideas_block(wikitext):
    """Check if wikitext contains a {{refideas}} template."""
    import mwparserfromhell
    code = mwparserfromhell.parse(wikitext)
    return len(code.filter_templates(
        matches=lambda t: str(t.name).lower().strip() == "refideas"
    )) > 0


def ref_text_in_wikitext(wikitext, text):
    """Check if text appears in a refideas parameter value."""
    return text in wikitext


# ─── Fixtures ───────────────────────────────────────────────────────────────

# Realistic Talk page: banners then headings (most common pattern — ~88%)
TALK_WITH_BANNERS_AND_HEADINGS = """{{Talk header}}
{{WikiProject banner shell|class=B|
{{WikiProject Chemistry|importance=High}}
{{WikiProject Physics|importance=Mid}}
}}
{{User:MiszaBot/config
| algo = old(90d)
| archive = Talk:Electron configuration/Archive %(counter)d
}}

== Aufbau principle ==
The Aufbau principle section needs clarification on energy ordering...

== Multi-electron atoms ==
Should we merge this with the main article?
"""

# Talk page with existing refideas
TALK_WITH_REFIDEAS = """{{Talk header}}
{{WikiProject banner shell|class=C|
{{WikiProject Computing|importance=Top}}
}}
{{refideas
| 1 = [https://example.com/algo-book Introduction to Algorithms], MIT Press
| 2 = [https://example.com/clrs CLRS Textbook], MIT Press
}}

== Pseudocode standards ==
Should we standardize on a particular pseudocode style?
"""

# Talk page with existing refideas, non-sequential params
TALK_WITH_REFIDEAS_GAPPED = """{{Talk header}}
{{refideas
| 1 = [https://example.com/first First Reference], Source A
| 3 = [https://example.com/third Third Reference], Source C
| 5 = [https://example.com/fifth Fifth Reference], Source E
}}

== Discussion ==
Some talk page content here.
"""

# Talk page with no headings — only templates
TALK_NO_HEADINGS = """{{Talk header}}
{{WikiProject banner shell|class=Start|
{{WikiProject History|importance=Low}}
}}
{{User:MiszaBot/config|algo=old(30d)}}
"""

# Empty Talk page
TALK_EMPTY = ""

# Talk page with only headings, no templates
TALK_HEADINGS_ONLY = """== First topic ==
Some discussion.

== Second topic ==
More discussion.
"""

# Talk page with complex headings (special chars)
TALK_COMPLEX_HEADINGS = """{{Talk header}}

== Article title & scope ==
Discussion about scope.

== 3rd party sources ==
Discussion about sources.
"""

# Talk page with Refidea alias (no trailing 's')
TALK_WITH_REFIDEA_ALIAS = """{{Talk header}}
{{refidea
| 1 = [https://example.com/ref Some Reference], Source
}}

== Discussion ==
Some content.
"""

# Talk page with RI alias
TALK_WITH_RI_ALIAS = """{{Talk header}}
{{RI
| 1 = [https://example.com/ref Some Reference], Source
}}

== Discussion ==
Some content.
"""


# ─── Tests: Append to existing ─────────────────────────────────────────────

class TestAppendExisting(unittest.TestCase):
    """Tests where a {{refideas}} block already exists."""

    def test_append_to_existing(self):
        """Should append as next numbered param."""
        result = proto.build_refideas_wikitext(
            TALK_WITH_REFIDEAS,
            url="https://example.com/new-ref",
            label="New Reference",
            source="New Source",
        )
        self.assertEqual(result["action"], "append")
        self.assertIn("#3", result["detail"])
        self.assertEqual(count_refideas_params(result["wikitext"]), 3)
        self.assertIn("New Reference", result["wikitext"])

    def test_append_gapped_params(self):
        """Non-sequential params (1, 3, 5) → append as #6."""
        result = proto.build_refideas_wikitext(
            TALK_WITH_REFIDEAS_GAPPED,
            url="https://example.com/new-ref",
            label="New Reference",
            source="New Source",
        )
        self.assertEqual(result["action"], "append")
        self.assertIn("#6", result["detail"])
        self.assertEqual(count_refideas_params(result["wikitext"]), 4)

    def test_append_preserves_existing_params(self):
        """Existing refideas params should remain untouched."""
        result = proto.build_refideas_wikitext(
            TALK_WITH_REFIDEAS,
            url="https://example.com/new-ref",
            label="New Reference",
            source="New Source",
        )
        self.assertIn("Introduction to Algorithms", result["wikitext"])
        self.assertIn("CLRS Textbook", result["wikitext"])

    def test_append_full_format(self):
        """The appended ref should have [url label], source (note) format."""
        result = proto.build_refideas_wikitext(
            TALK_WITH_REFIDEAS,
            url="https://example.com/ref",
            label="My Label",
            source="My Source",
            note="extra info",
        )
        self.assertIn("[https://example.com/ref My Label]", result["wikitext"])
        self.assertIn("My Source", result["wikitext"])
        self.assertIn("(extra info)", result["wikitext"])

    def test_append_without_source(self):
        """Source is optional — should still work."""
        result = proto.build_refideas_wikitext(
            TALK_WITH_REFIDEAS,
            url="https://example.com/ref",
            label="Bare Label",
        )
        self.assertIn("[https://example.com/ref Bare Label]", result["wikitext"])
        # Should not have a trailing ", " with no source
        self.assertNotIn("Bare Label],", result["wikitext"])


# ─── Tests: Insert new block ───────────────────────────────────────────────

class TestInsertNew(unittest.TestCase):
    """Tests where no {{refideas}} exists — a new block is created."""

    def test_insert_before_first_heading(self):
        """{{refideas}} should be inserted before the first == heading."""
        result = proto.build_refideas_wikitext(
            TALK_WITH_BANNERS_AND_HEADINGS,
            url="https://example.com/ref",
            label="Test Reference",
            source="Test Source",
        )
        self.assertEqual(result["action"], "insert")
        self.assertIn("Aufbau principle", result["detail"])
        self.assertTrue(has_refideas_block(result["wikitext"]))

        # Verify order: refideas appears before first heading
        refideas_pos = result["wikitext"].lower().find("{{refideas")
        heading_pos = result["wikitext"].find("== Aufbau principle")
        self.assertLess(refideas_pos, heading_pos)

    def test_insert_after_banners(self):
        """{{refideas}} should be after the last banner template."""
        result = proto.build_refideas_wikitext(
            TALK_WITH_BANNERS_AND_HEADINGS,
            url="https://example.com/ref",
            label="Test Reference",
            source="Test Source",
        )
        # Talk header should still be before refideas
        talk_header_pos = result["wikitext"].find("{{Talk header}}")
        refideas_pos = result["wikitext"].lower().find("{{refideas")
        self.assertLess(talk_header_pos, refideas_pos)

    def test_insert_headings_only(self):
        """Page with only headings, no templates."""
        result = proto.build_refideas_wikitext(
            TALK_HEADINGS_ONLY,
            url="https://example.com/ref",
            label="Test Reference",
            source="Test Source",
        )
        self.assertEqual(result["action"], "insert")
        self.assertIn("First topic", result["detail"])

    def test_insert_complex_heading(self):
        """Headings with special chars like &."""
        result = proto.build_refideas_wikitext(
            TALK_COMPLEX_HEADINGS,
            url="https://example.com/ref",
            label="Test Reference",
            source="Test Source",
        )
        self.assertEqual(result["action"], "insert")


# ─── Tests: Append at end (no headings) ────────────────────────────────────

class TestAppendEnd(unittest.TestCase):
    """Tests where no headings exist — append at end."""

    def test_append_end_no_headings(self):
        """Page with templates but no headings → append at end."""
        result = proto.build_refideas_wikitext(
            TALK_NO_HEADINGS,
            url="https://example.com/ref",
            label="Test Reference",
            source="Test Source",
        )
        self.assertEqual(result["action"], "append_end")
        self.assertTrue(has_refideas_block(result["wikitext"]))
        # Refideas should be at the very end
        self.assertTrue(result["wikitext"].rstrip().endswith("}}"))

    def test_empty_talk_page(self):
        """Completely empty Talk page → append at end."""
        result = proto.build_refideas_wikitext(
            TALK_EMPTY,
            url="https://example.com/ref",
            label="Test Reference",
            source="Test Source",
        )
        self.assertEqual(result["action"], "append_end")
        self.assertTrue(has_refideas_block(result["wikitext"]))


# ─── Tests: Template aliases ───────────────────────────────────────────────

class TestTemplateAliases(unittest.TestCase):
    """{{refideas}} has many aliases. All should be recognized."""

    def test_alias_refidea(self):
        """{{refidea}} (no trailing 's') should be treated as refideas."""
        result = proto.build_refideas_wikitext(
            TALK_WITH_REFIDEA_ALIAS,
            url="https://example.com/new-ref",
            label="New Reference",
            source="New Source",
        )
        self.assertEqual(result["action"], "append")
        self.assertIn("#2", result["detail"])

    def test_alias_ri(self):
        """{{RI}} shortcut should be treated as refideas."""
        result = proto.build_refideas_wikitext(
            TALK_WITH_RI_ALIAS,
            url="https://example.com/new-ref",
            label="New Reference",
            source="New Source",
        )
        self.assertEqual(result["action"], "append")
        self.assertIn("#2", result["detail"])


# ─── Tests: Idempotency ────────────────────────────────────────────────────

class TestIdempotency(unittest.TestCase):
    """Running the function twice should produce consistent results."""

    def test_idempotent_append(self):
        """Appending twice: second run should add param #N+1."""
        first = proto.build_refideas_wikitext(
            TALK_WITH_REFIDEAS,
            url="https://example.com/ref-a",
            label="Ref A",
            source="Source A",
        )
        second = proto.build_refideas_wikitext(
            first["wikitext"],
            url="https://example.com/ref-b",
            label="Ref B",
            source="Source B",
        )
        self.assertEqual(second["action"], "append")
        self.assertIn("Ref A", second["wikitext"])
        self.assertIn("Ref B", second["wikitext"])
        self.assertEqual(count_refideas_params(second["wikitext"]), 4)

    def test_idempotent_insert(self):
        """Inserting on a page that already got refideas: second run appends."""
        first = proto.build_refideas_wikitext(
            TALK_WITH_BANNERS_AND_HEADINGS,
            url="https://example.com/ref-a",
            label="Ref A",
            source="Source A",
        )
        second = proto.build_refideas_wikitext(
            first["wikitext"],
            url="https://example.com/ref-b",
            label="Ref B",
            source="Source B",
        )
        self.assertEqual(second["action"], "append")
        self.assertIn("Ref A", second["wikitext"])
        self.assertIn("Ref B", second["wikitext"])

    def test_idempotent_same_url(self):
        """Inserting same URL twice: second run adds it again (dedup is in refideas_add, not here)."""
        first = proto.build_refideas_wikitext(
            TALK_WITH_REFIDEAS,
            url="https://example.com/same-ref",
            label="Same Ref",
            source="Same Source",
        )
        second = proto.build_refideas_wikitext(
            first["wikitext"],
            url="https://example.com/same-ref",
            label="Same Ref",
            source="Same Source",
        )
        # build_refideas_wikitext doesn't dedup — that's refideas_add's job
        self.assertEqual(second["action"], "append")


# ─── Tests: OCW wrapper ────────────────────────────────────────────────────

class TestOCWWrapper(unittest.TestCase):
    """l1_insert_refideas() should format OCW args correctly."""

    def test_ocw_format(self):
        """Should produce [url MIT id: title], MIT OpenCourseWare (note)."""
        result = proto.l1_insert_refideas(
            article_title="Algorithm",
            course_id="6.006",
            course_title="Introduction to Algorithms",
            course_url="https://ocw.mit.edu/courses/6-006/",
            note="video lectures",
        )
        self.assertIn("[https://ocw.mit.edu/courses/6-006/ MIT 6.006: Introduction to Algorithms]", result["wikitext"])
        self.assertIn("MIT OpenCourseWare", result["wikitext"])
        self.assertIn("(video lectures)", result["wikitext"])

    def test_ocw_no_note(self):
        """Note is optional."""
        result = proto.l1_insert_refideas(
            article_title="Algorithm",
            course_id="6.006",
            course_title="Introduction to Algorithms",
            course_url="https://ocw.mit.edu/courses/6-006/",
        )
        self.assertIn("MIT OpenCourseWare", result["wikitext"])
        # No dangling parentheses
        self.assertNotIn("()", result["wikitext"])


# ─── Tests: Edge cases ─────────────────────────────────────────────────────

class TestEdgeCases(unittest.TestCase):
    """Special characters, formatting preservation, etc."""

    def test_special_chars_in_label(self):
        """Ampersands, quotes in labels should be preserved."""
        result = proto.build_refideas_wikitext(
            TALK_WITH_REFIDEAS,
            url="https://example.com/ref",
            label="Chemistry & Physics: A \"Deep Dive\"",
            source="Academic Press",
        )
        self.assertIn('Chemistry & Physics: A "Deep Dive"', result["wikitext"])

    def test_heading_not_destroyed(self):
        """The heading we insert before should remain intact."""
        result = proto.build_refideas_wikitext(
            TALK_WITH_BANNERS_AND_HEADINGS,
            url="https://example.com/ref",
            label="Test",
            source="Test",
        )
        self.assertIn("== Aufbau principle ==", result["wikitext"])
        self.assertIn("The Aufbau principle section needs clarification",
                      result["wikitext"])

    def test_preserves_wikiproject_banners(self):
        """WikiProject banners must not be modified."""
        result = proto.build_refideas_wikitext(
            TALK_WITH_BANNERS_AND_HEADINGS,
            url="https://example.com/ref",
            label="Test",
            source="Test",
        )
        self.assertIn("{{WikiProject Chemistry", result["wikitext"])
        self.assertIn("{{WikiProject Physics", result["wikitext"])
        self.assertIn("{{User:MiszaBot/config", result["wikitext"])

    def test_summary_contains_label(self):
        """The edit summary should mention the label."""
        result = proto.build_refideas_wikitext(
            TALK_WITH_BANNERS_AND_HEADINGS,
            url="https://example.com/ref",
            label="My Special Reference",
            source="Test Source",
        )
        self.assertIn("My Special Reference", result["summary"])


if __name__ == "__main__":
    unittest.main()
