#!/usr/bin/env python3
"""
Check that docs/L1-REFIDEAS.md and docs/L2-EXTERNAL-LINKS.md are in sync
with their corresponding code files.

Checks:
  1. Test counts in docs match actual test file counts
  2. CLI flags documented in docs exist in the corresponding script
  3. Status lines mention recent dates (warns if >90 days old)

Usage:
    python3 scripts/check-doc-sync.py          # Full check
    python3 scripts/check-doc-sync.py --quiet   # Only show failures
    python3 scripts/check-doc-sync.py --fix     # Auto-fix test counts in docs
"""

import os
import re
import sys
import argparse
from datetime import datetime, timezone

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.abspath(os.path.join(SCRIPTS_DIR, "..", "docs"))


# ─── Helpers ────────────────────────────────────────────────────────────────

def count_tests_in_file(filepath: str) -> int:
    """Count test functions (def test_*) in a Python test file."""
    if not os.path.exists(filepath):
        return 0
    count = 0
    with open(filepath) as f:
        for line in f:
            if re.match(r'\s*def test_', line):
                count += 1
    return count


def extract_cli_flags(filepath: str) -> set:
    """Extract --flag names from a Python CLI script's argument parser."""
    flags = set()
    if not os.path.exists(filepath):
        return flags
    with open(filepath) as f:
        for line in f:
            # Match --flag or --flag-name patterns
            m = re.findall(r"'--([a-z][a-z0-9-]*)'", line)
            flags.update(m)
            m = re.findall(r'"--([a-z][a-z0-9-]*)"', line)
            flags.update(m)
    return flags


def find_test_counts_in_doc(filepath: str) -> list:
    """Find all mentions of test counts in a doc file.
    
    Returns list of ints found in patterns like 'X tests' or 'tests (X)'.
    """
    counts = []
    if not os.path.exists(filepath):
        return counts
    with open(filepath) as f:
        for line in f:
            # Match patterns: "28 tests", "tests (26)", "26 tests", etc.
            for m in re.finditer(r'(\d+)\s*(?:test|test[s])\b', line, re.IGNORECASE):
                counts.append(int(m.group(1)))
            for m in re.finditer(r'test[s]?\s*\((\d+)\)', line, re.IGNORECASE):
                counts.append(int(m.group(1)))
    return counts


def find_cli_flags_in_doc(filepath: str) -> set:
    """Extract --flag mentions from a doc file."""
    flags = set()
    if not os.path.exists(filepath):
        return flags
    with open(filepath) as f:
        for line in f:
            for m in re.finditer(r'--([a-z][a-z0-9-]*)', line):
                flags.add(m.group(1))
    return flags


def find_status_date(filepath: str) -> str:
    """Extract the most recent date from the status line in a doc."""
    if not os.path.exists(filepath):
        return ""
    with open(filepath) as f:
        for line in f:
            # Match YYYY-MM-DD dates
            m = re.search(r'(\d{4}-\d{2}-\d{2})', line)
            if m and ('status' in line.lower() or 'updated' in line.lower()):
                return m.group(1)
    return ""


def update_test_count_in_doc(filepath: str, expected: int, actual: int) -> bool:
    """Fix a stale test count in a doc file. Returns True if changed."""
    if not os.path.exists(filepath):
        return False
    with open(filepath) as f:
        content = f.read()

    old = str(expected)
    new = str(actual)
    if old == new:
        return False

    # Try to replace the specific count
    count = 0
    def replacer(m):
        nonlocal count
        count += 1
        return m.group(0).replace(old, new)

    new_content = re.sub(rf'\b{re.escape(old)}\s*(?:test|tests)\b', replacer, content, flags=re.IGNORECASE)
    if new_content != content:
        with open(filepath, 'w') as f:
            f.write(new_content)
        return True
    return False


# ─── Checks ────────────────────────────────────────────────────────────────

class Result:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.warnings = []

    def ok(self, msg):
        self.passed.append(msg)

    def fail(self, msg):
        self.failed.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)

    def summary(self) -> str:
        parts = []
        if self.failed:
            parts.append(f"{len(self.failed)} FAILED")
        if self.warnings:
            parts.append(f"{len(self.warnings)} warnings")
        if self.passed:
            parts.append(f"{len(self.passed)} passed")
        return ", ".join(parts) if parts else "all checks passed"


CHECKED: list[tuple[str, str, str, str, str]] = [
    # (doc_path, script_paths_for_flags, test_file_path, doc_label, script_label)
    (
        os.path.join(DOCS_DIR, "L1-REFIDEAS.md"),
        [
            os.path.join(SCRIPTS_DIR, "lint-refideas.py"),
            os.path.join(SCRIPTS_DIR, "apply-refideas-fix.py"),
            os.path.join(SCRIPTS_DIR, "refideas-add.py"),
            os.path.join(SCRIPTS_DIR, "apply-l1-refideas.py"),
        ],
        [
            os.path.join(SCRIPTS_DIR, "test-refideas.py"),
            os.path.join(SCRIPTS_DIR, "test-l1-refideas-insert.py"),
        ],
        "L1-REFIDEAS",
        "lint-refideas/apply-refideas-fix/refideas-add/apply-l1-refideas",
    ),
    (
        os.path.join(DOCS_DIR, "L2-EXTERNAL-LINKS.md"),
        [
            os.path.join(SCRIPTS_DIR, "apply-l2-external-links.py"),
        ],
        [
            os.path.join(SCRIPTS_DIR, "test-l2-external-links.py"),
        ],
        "L2-EXTERNAL-LINKS",
        "apply-l2-external-links",
    ),
]


def run_checks(quiet: bool = False) -> Result:
    result = Result()
    now = datetime.now(timezone.utc)

    # ── Count all test files ──
    # L1 test files
    l1_test_files = [
        os.path.join(SCRIPTS_DIR, "test-refideas.py"),
        os.path.join(SCRIPTS_DIR, "test-l1-refideas-insert.py"),
    ]
    l1_total = sum(count_tests_in_file(f) for f in l1_test_files)
    l1_individual = {os.path.basename(f): count_tests_in_file(f) for f in l1_test_files}

    # L2 test files
    l2_test_files = [os.path.join(SCRIPTS_DIR, "test-l2-external-links.py")]
    l2_total = sum(count_tests_in_file(f) for f in l2_test_files)

    for doc_path, script_paths, test_paths, doc_label, script_label in CHECKED:
        doc_short = os.path.basename(doc_path)

        # ── Check 1: Status date freshness ──
        status_date_str = find_status_date(doc_path)
        if status_date_str:
            try:
                status_date = datetime.strptime(status_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                days_old = (now - status_date).days
                if days_old > 90:
                    result.warn(f"[{doc_short}] Status date {status_date_str} is {days_old} days old")
                elif not quiet:
                    result.ok(f"[{doc_short}] Status date {status_date_str} is current ({days_old}d old)")
            except ValueError:
                result.warn(f"[{doc_short}] Could not parse date: {status_date_str}")
        else:
            result.warn(f"[{doc_short}] No status date found")

        # ── Check 2: Test counts match ──
        # Determine expected counts based on which doc
        if "L1" in doc_label:
            expected_count = l1_total
            individual_counts = l1_individual
        else:
            expected_count = l2_total
            individual_counts = {os.path.basename(f): count_tests_in_file(f) for f in l2_test_files}

        doc_counts = find_test_counts_in_doc(doc_path)
        # The doc should mention the total test count somewhere
        if expected_count > 0 and expected_count not in doc_counts:
            result.fail(
                f"[{doc_short}] Doc mentions test counts {doc_counts} "
                f"but actual total is {expected_count} "
                f"(from {individual_counts})"
            )
        elif not quiet:
            result.ok(f"[{doc_short}] Test count {expected_count} found in doc {doc_counts}")

        # ── Check 3: CLI flags documented ──
        for script_path in script_paths:
            script_flags = extract_cli_flags(script_path)
            doc_flags = find_cli_flags_in_doc(doc_path)
            script_short = os.path.basename(script_path)

            # Flags to exclude from check
            skip_flags = {"dry-run", "yes", "y", "help", "batch"}  # --batch is an unimplemented stub

            missing = script_flags - doc_flags - skip_flags
            if missing:
                result.fail(
                    f"[{doc_short}] Flags documented in {script_short} but missing from doc: "
                    f"{', '.join(sorted(missing))}"
                )
            elif not quiet:
                result.ok(f"[{doc_short}] All CLI flags from {script_short} are documented")

    return result


# ─── CLI ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Check doc/code sync for L1 and L2 documentation")
    parser.add_argument("--quiet", action="store_true", help="Only show failures and warnings")
    parser.add_argument("--fix", action="store_true", help="Auto-fix stale test counts in docs")
    args = parser.parse_args()

    if args.fix:
        # L1 fix
        l1_test_files = [
            os.path.join(SCRIPTS_DIR, "test-refideas.py"),
            os.path.join(SCRIPTS_DIR, "test-l1-refideas-insert.py"),
        ]
        l1_doc = os.path.join(DOCS_DIR, "L1-REFIDEAS.md")
        l1_actual = sum(count_tests_in_file(f) for f in l1_test_files)
        for f in l1_test_files:
            f_short = os.path.basename(f)
            f_count = count_tests_in_file(f)
            # Find old count in doc and replace
            doc_counts = find_test_counts_in_doc(l1_doc)
            for old_count in doc_counts:
                if old_count != l1_actual:
                    if update_test_count_in_doc(l1_doc, old_count, l1_actual):
                        print(f"  Fixed test count {old_count} → {l1_actual} in {os.path.basename(l1_doc)}")

        # L2 fix
        l2_test_file = os.path.join(SCRIPTS_DIR, "test-l2-external-links.py")
        l2_doc = os.path.join(DOCS_DIR, "L2-EXTERNAL-LINKS.md")
        l2_actual = count_tests_in_file(l2_test_file)
        doc_counts = find_test_counts_in_doc(l2_doc)
        for old_count in doc_counts:
            if old_count != l2_actual:
                if update_test_count_in_doc(l2_doc, old_count, l2_actual):
                    print(f"  Fixed test count {old_count} → {l2_actual} in {os.path.basename(l2_doc)}")

        print("  Done.")
        return

    result = run_checks(quiet=args.quiet)

    # Print results
    for msg in result.failed:
        print(f"  ❌ {msg}")
    for msg in result.warnings:
        print(f"  ⚠️  {msg}")
    if not args.quiet:
        for msg in result.passed:
            print(f"  ✅ {msg}")

    print(f"\n  {result.summary()}")

    if result.failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
