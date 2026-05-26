#!/usr/bin/env python3
"""
Parallel batch scanner for OCW course assets.

Scans all unscanned courses using scan-assets.py --hybrid in parallel threads.
Skips courses that already have asset_counts in their frontmatter.

Usage:
    python3 scripts/scan-batch-parallel.py              # Scan all unscanned
    python3 scripts/scan-batch-parallel.py --workers 5  # Use 5 parallel workers
    python3 scripts/scan-batch-parallel.py --limit 50   # Scan only 50 courses
    python3 scripts/scan-batch-parallel.py --dry-run    # Show what would be scanned
"""

import os
import sys
import time
import subprocess
import concurrent.futures
from datetime import datetime

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
COURSES_DIR = os.path.join(os.path.dirname(SCRIPTS_DIR), "wiki", "courses")
SCAN_SCRIPT = os.path.join(SCRIPTS_DIR, "scan-assets.py")


def find_unscanned():
    """Find all course slugs that haven't been scanned yet."""
    slugs = []
    for fname in sorted(os.listdir(COURSES_DIR)):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(COURSES_DIR, fname)
        try:
            with open(fpath) as f:
                content = f.read(4096)  # Only need frontmatter
            if "asset_counts" not in content:
                slugs.append(fname.replace(".md", ""))
        except Exception:
            continue
    return slugs


def scan_one(slug: str) -> dict:
    """Scan a single course. Returns {slug, ok, elapsed, assets}."""
    start = time.time()
    try:
        result = subprocess.run(
            [sys.executable, SCAN_SCRIPT, "--hybrid", slug],
            capture_output=True, text=True, timeout=60
        )
        elapsed = time.time() - start

        # Count assets from output
        output = result.stdout + result.stderr
        assets = 0
        for line in output.splitlines():
            if "Merged:" in line:
                try:
                    assets = int(line.split("Merged:")[1].split()[0])
                except ValueError:
                    pass

        ok = result.returncode == 0
        return {"slug": slug, "ok": ok, "elapsed": elapsed, "assets": assets}
    except subprocess.TimeoutExpired:
        return {"slug": slug, "ok": False, "elapsed": 60, "assets": 0}
    except Exception as e:
        return {"slug": slug, "ok": False, "elapsed": time.time() - start, "assets": 0}


def main():
    workers = 8
    limit = None
    dry_run = False

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--workers":
            i += 1
            if i < len(args):
                workers = int(args[i])
        elif args[i] == "--limit":
            i += 1
            if i < len(args):
                limit = int(args[i])
        elif args[i] == "--dry-run":
            dry_run = True
        i += 1

    slugs = find_unscanned()
    total = len(slugs)

    if limit:
        slugs = slugs[:limit]
        print(f"  Found {total} unscanned courses, limiting to {len(slugs)}")
    else:
        print(f"  Found {total} unscanned courses")

    if dry_run:
        print(f"  Would scan {len(slugs)} courses with {workers} workers")
        print(f"  Estimated time: ~{len(slugs) * 2.5 / workers:.0f}s")
        print(f"\n  First 10 courses:")
        for s in slugs[:10]:
            print(f"    {s}")
        return

    print(f"  Scanning with {workers} parallel workers")
    print(f"  Estimated time: ~{len(slugs) * 2.5 / workers:.0f}s\n")

    start_time = time.time()
    completed = 0
    ok_count = 0
    fail_count = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(scan_one, slug): slug for slug in slugs}

        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            completed += 1

            if result["ok"]:
                ok_count += 1
                icon = "✅"
            else:
                fail_count += 1
                icon = "❌"

            elapsed = time.time() - start_time
            rate = completed / elapsed if elapsed > 0 else 0
            remaining = (len(slugs) - completed) / rate if rate > 0 else 0

            print(
                f"  [{completed:>4}/{len(slugs)}] {icon} "
                f"{result['slug'][:55]:<55} "
                f"{result['assets']:>3} assets "
                f"{result['elapsed']:>4.1f}s  "
                f"({rate:.1f}/s, ~{remaining:.0f}s left)"
            )

    total_time = time.time() - start_time
    print(f"\n{'='*65}")
    print(f"  Done: {ok_count} ok, {fail_count} failed in {total_time:.0f}s")
    print(f"  Rate: {completed / total_time:.1f} courses/second")
    print(f"  Scanned now: {ok_count}, previously scanned: {total - len(slugs)}")
    print(f"  Total with asset data: ~{ok_count + (total - len(slugs))}")


if __name__ == "__main__":
    main()
