#!/usr/bin/env python3
"""
Test suite for the Refideas linter and fixer.

Run:
    python3 scripts/test-refideas.py
    python3 scripts/test-refideas.py -v    # verbose
"""

import sys
import os
import unittest

# Add scripts to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import importlib.util
spec = importlib.util.spec_from_file_location(
    "lint_refideas",
    os.path.join(os.path.dirname(__file__), "lint-refideas.py")
)
lint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lint)


# ─── Helpers ────────────────────────────────────────────────────────────────

def lint_and_fix(wikitext, article="Test"):
    """Run lint + generate_fix, return (result, fixed_wikitext, errors)."""
    result = lint.lint_refideas_templates(wikitext, article)
    fixed, errors, summary = lint.generate_fix(wikitext, article)
    return result, fixed, errors


def refs_in_output(wikitext):
    """Count the number of reference lines in a refideas block."""
    idx = wikitext.lower().find('refideas')
    if idx < 0:
        return 0
    # Find matching }} using depth counter
    depth = 0
    for i in range(idx - 2, len(wikitext)):
        if wikitext[i:i+2] == '{{':
            depth += 1
        elif wikitext[i:i+2] == '}}':
            depth -= 1
            if depth == 0:
                block = wikitext[idx-2:i+2]
                break
    else:
        return 0
    # Count lines starting with | that are reference params (not state/comment)
    count = 0
    for line in block.split('\n'):
        stripped = line.strip()
        if stripped.startswith('|'):
            inner = stripped[1:].strip()
            # Skip state=, comment=, small= params (with optional spaces around =)
            param_name = inner.split('=')[0].strip() if '=' in inner else ''
            if param_name in ('state', 'comment', 'small'):
                continue
            count += 1
    return count


def has_numbered_params(wikitext):
    """Check that output preserves |1=, |2= numbering."""
    import re
    return bool(re.search(r'\|(\d+)=', wikitext))


# ─── Test Cases ─────────────────────────────────────────────────────────────

class TestMultiBullet(unittest.TestCase):
    """Splitting multiple bullet references into separate params."""

    def test_five_bullets(self):
        wikitext = """{{WikiProject Video games}}
{{refideas|
* {{cite journal|title=One}}
* {{cite book|title=Two}}
* {{cite web|url=Three}}
* {{cite journal|title=Four}}
* {{cite book|title=Five}}
}}
== Discussion ==
Some talk text."""
        result, fixed, errors = lint_and_fix(wikitext)
        self.assertTrue(result.has_actionable_errors)
        self.assertEqual(len(errors), 1)
        self.assertIn("multi_bullet", errors[0].type)
        self.assertEqual(refs_in_output(fixed), 5)
        self.assertIn("|{{cite journal|title=One}}", fixed)
        self.assertIn("|{{cite book|title=Two}}", fixed)
        self.assertIn("|{{cite web|url=Three}}", fixed)
        self.assertNotIn("* {{cite journal", fixed)

    def test_two_bullets(self):
        wikitext = """{{WikiProject banner shell|1=
{{WikiProject Film}}
}}
{{refideas|
* [https://example.com Article One], Example.com
* [https://example.org Article Two], Example.org
}}
== Talk ==
Hello."""
        result, fixed, errors = lint_and_fix(wikitext)
        self.assertTrue(result.has_actionable_errors)
        self.assertEqual(refs_in_output(fixed), 2)
        self.assertIn("|[https://example.com Article One]", fixed)
        self.assertNotIn("* [https://example.com", fixed)


class TestSingleBullet(unittest.TestCase):
    """Stripping * from single-reference bullet syntax."""

    def test_single_bullet(self):
        wikitext = """{{WikiProject Video games|class=Stub}}
{{Refideas|
* GA Strategy, ''Interview'' [https://web.archive.org/web/test]
}}
== Discussion ==
Some text."""
        result, fixed, errors = lint_and_fix(wikitext)
        self.assertTrue(result.has_actionable_errors)
        self.assertNotIn("* GA Strategy", fixed)
        self.assertIn("|1=GA Strategy", fixed)

    def test_single_bullet_cite(self):
        wikitext = """{{WikiProject banner shell}}
{{refideas|
* {{cite journal |last=Murphy |title=Test}}
}}
== Talk ==
Text."""
        result, fixed, errors = lint_and_fix(wikitext)
        self.assertTrue(result.has_actionable_errors)
        self.assertNotIn("* {{cite journal", fixed)
        self.assertIn("|1={{cite journal", fixed)


class TestDuplicateURL(unittest.TestCase):
    """Removing duplicate URL references."""

    def test_simple_duplicate(self):
        wikitext = """{{WikiProject banner shell}}
{{refideas
|1=https://example.com/article
|2=https://other.com/stuff
|3=https://example.com/article
}}
== Talk ==
Text."""
        result, fixed, errors = lint_and_fix(wikitext)
        self.assertTrue(result.has_actionable_errors)
        # Should have 2 refs after dedup (removed param 3)
        self.assertEqual(refs_in_output(fixed), 2)
        # Only one instance of the duplicate URL
        count = fixed.count("https://example.com/article")
        self.assertEqual(count, 1)

    def test_no_duplicate(self):
        wikitext = """{{WikiProject banner shell}}
{{refideas
|1=https://example.com/a
|2=https://example.com/b
}}
== Talk ==
Text."""
        result, fixed, errors = lint_and_fix(wikitext)
        self.assertFalse(result.has_actionable_errors)

    def test_duplicate_with_numbered_params(self):
        wikitext = """{{refideas
|1=https://a.com
|2=https://b.com
|3=https://c.com
|4=https://a.com
|5=https://d.com
}}
== Talk ==
Text."""
        result, fixed, errors = lint_and_fix(wikitext)
        self.assertTrue(result.has_actionable_errors)
        self.assertEqual(refs_in_output(fixed), 4)


class TestNumberingPreserved(unittest.TestCase):
    """Numbered params (|1=, |2=) should survive reformatting."""

    def test_duplicate_preserves_numbering(self):
        wikitext = """{{refideas
|1=https://a.com
|2=https://b.com
|3=https://a.com
}}
== Talk ==
Text."""
        result, fixed, errors = lint_and_fix(wikitext)
        self.assertTrue(has_numbered_params(fixed))

    def test_single_bullet_numbered(self):
        wikitext = """{{refideas|
* 64 Power / big.N / N Games (Aug, 2004)
}}
== Talk ==
Text."""
        result, fixed, errors = lint_and_fix(wikitext)
        self.assertIn("|1=64 Power", fixed)
        self.assertNotIn("* 64 Power", fixed)

    def test_multi_line_format(self):
        """Output should use multi-line format, not single-line."""
        wikitext = """{{refideas|
* [https://a.com Article A]
}}
== Talk ==
Text."""
        result, fixed, errors = lint_and_fix(wikitext)
        # Should contain newlines in the refideas block
        import re
        m = re.search(r'\{\{refideas\n', fixed)
        self.assertIsNotNone(m, "refideas block should use multi-line format")
        self.assertIn("\n}}", fixed)


class TestCleanPage(unittest.TestCase):
    """Pages with no errors should pass through cleanly."""

    def test_well_formed(self):
        wikitext = """{{WikiProject banner shell}}
{{refideas
|1=[https://ocw.mit.edu/courses/test MIT Course], MIT OpenCourseWare
|2=[https://example.com/article News Article], Example.com
}}
== Talk ==
Text."""
        result, fixed, errors = lint_and_fix(wikitext)
        self.assertFalse(result.has_actionable_errors)
        self.assertEqual(fixed, wikitext)

    def test_bare_urls_only(self):
        """Bare URLs are info-level, not actionable."""
        wikitext = """{{WikiProject banner shell}}
{{refideas
|https://abcnews.go.com/article
|https://www.axios.com/stuff
}}
== Talk ==
Text."""
        result, fixed, errors = lint_and_fix(wikitext)
        self.assertFalse(result.has_actionable_errors)


class TestBareURL(unittest.TestCase):
    """Bare URLs are detected but not auto-fixed."""

    def test_bare_url_detected(self):
        wikitext = """{{WikiProject banner shell}}
{{Refideas
| 1 = https://abcnews.go.com/article
| 2 = https://www.axios.com/stuff
}}
== Talk ==
Text."""
        result, fixed, errors = lint_and_fix(wikitext)
        self.assertTrue(result.has_errors)
        self.assertFalse(result.has_actionable_errors)
        self.assertEqual(fixed, wikitext)  # No changes made

    def test_bare_url_not_in_errors(self):
        wikitext = """{{Refideas
| 1 = https://example.com
}}
== Talk ==
Text."""
        result, fixed, errors = lint_and_fix(wikitext)
        self.assertEqual(fixed, wikitext)  # No fix applied to bare URLs


class TestTemplateAliases(unittest.TestCase):
    """All 11 template aliases should be recognized."""

    def test_lowercase_refideas(self):
        wikitext = """{{refideas
| 1 = https://example.com
}}
== Talk ==
Text."""
        result, fixed, errors = lint_and_fix(wikitext)
        self.assertEqual(result.template_count, 1)
        self.assertEqual(result.template_alias_used.lower(), "refideas")

    def test_shortcut_ri(self):
        wikitext = """{{WikiProject banner shell}}
{{ri|1=https://example.com}}
== Talk ==
Text."""
        result, fixed, errors = lint_and_fix(wikitext)
        self.assertEqual(result.template_count, 1)
        self.assertIn(result.template_alias_used.lower(), lint.REFIDEAS_ALIASES)

    def test_suggested_sources(self):
        wikitext = """{{suggested sources
| 1 = https://example.com
}}
== Talk ==
Text."""
        result, fixed, errors = lint_and_fix(wikitext)
        self.assertEqual(result.template_count, 1)


class TestCommentAndState(unittest.TestCase):
    """Comment and state params should be preserved, not treated as refs."""

    def test_comment_param(self):
        wikitext = """{{refideas
| 1 = https://example.com
| comment = These are useful
}}
== Talk ==
Text."""
        result, fixed, errors = lint_and_fix(wikitext)
        self.assertIn("comment", fixed.lower())

    def test_state_param(self):
        wikitext = """{{refideas
| state = collapsed
| 1 = https://example.com
}}
== Talk ==
Text."""
        # Just verify it doesn't crash or misidentify
        result, fixed, errors = lint_and_fix(wikitext)
        self.assertEqual(refs_in_output(fixed), 1)


class TestRoundTrip(unittest.TestCase):
    """Idempotency: fixing an already-fixed page should produce no changes."""

    def test_idempotent_multi_bullet(self):
        wikitext = """{{refideas|
* {{cite journal|title=A}}
* {{cite web|url=B}}
}}
== Talk ==
Text."""
        # First fix
        _, fixed1, _ = lint_and_fix(wikitext)
        # Second fix
        result2, fixed2, _ = lint_and_fix(fixed1)
        self.assertFalse(result2.has_actionable_errors)
        self.assertEqual(fixed2, fixed1)

    def test_idempotent_single_bullet(self):
        wikitext = """{{Refideas|
* [https://a.com Article A]
}}
== Talk ==
Text."""
        _, fixed1, _ = lint_and_fix(wikitext)
        result2, fixed2, _ = lint_and_fix(fixed1)
        self.assertFalse(result2.has_actionable_errors)

    def test_idempotent_duplicate(self):
        wikitext = """{{refideas
|1=https://a.com
|2=https://a.com
}}
== Talk ==
Text."""
        _, fixed1, _ = lint_and_fix(wikitext)
        result2, fixed2, _ = lint_and_fix(fixed1)
        self.assertFalse(result2.has_actionable_errors)


class TestStateCommentPreserved(unittest.TestCase):
    """state=, comment= params must survive reformatting."""

    def test_state_collapsed_preserved(self):
        wikitext = """{{refideas
|state=collapsed
|1=https://a.com
|2=https://a.com
}}
== Talk ==
Text."""
        _, fixed, _ = lint_and_fix(wikitext)
        self.assertIn("state=collapsed", fixed)
        self.assertEqual(fixed.count("https://a.com"), 1)

    def test_comment_preserved(self):
        wikitext = """{{refideas
|comment=These are useful sources
|1=https://example.com
}}
== Talk ==
Text."""
        _, fixed, _ = lint_and_fix(wikitext)
        self.assertIn("comment=These are useful sources", fixed)


class TestPikminRegression(unittest.TestCase):
    """Regression tests for bugs found in production."""

    def test_duplicate_strips_numbering(self):
        """Bug: duplicate fix stripped |1=, |2= numbering."""
        wikitext = """{{refideas
|1=http://nintendojo.com/a
|2=https://destructoid.com/b
|3=https://metacritic.com/c
|4=https://web.archive.org/d
|12=https://metacritic.com/c
}}
== Talk ==
Text."""
        _, fixed, _ = lint_and_fix(wikitext)
        self.assertTrue(has_numbered_params(fixed))
        self.assertIn("|1=http://nintendojo.com/a", fixed)
        self.assertIn("|2=https://destructoid.com/b", fixed)

    def test_str_tmpl_capture_timing(self):
        """Bug: str(tmpl) captured after param removal, couldn't replace."""
        wikitext = """{{refideas
|1=https://a.com
|2=https://a.com
}}
== Talk ==
Text."""
        _, fixed, _ = lint_and_fix(wikitext)
        # The fix should have actually changed the wikitext
        self.assertNotEqual(fixed, wikitext)
        self.assertEqual(fixed.count("https://a.com"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2 if "-v" in sys.argv else 1)
