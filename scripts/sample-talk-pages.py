#!/usr/bin/env python3
"""
Sample Talk pages from our crossref-matched articles to understand
the structural patterns we need to handle for inserting {{refideas}}.

Usage:
    python3 scripts/sample-talk-pages.py --sample       # Fetch and analyze Talk pages
    python3 scripts/sample-talk-pages.py --classify     # Classify the results
    python3 scripts/sample-talk-pages.py --full         # Sample + classify + dry-run insertion
"""

import json
import re
import sys
import time
import urllib.request
import urllib.parse
from collections import Counter

# Known crossref-matched articles from our data
ARTICLE_SAMPLE = [
    # From crossref-summary.md (top matches + representative samples)
    ("Nuclear weapon", "Environment"),
    ("Algorithm", "Computer Science"),
    ("Machine learning", "Computer Science"),
    ("Finance", "Business"),
    ("Probability", "Mathematics"),
    ("Hearing", "Biology"),
    ("Linguistics", "Linguistics & Philosophy"),
    ("Electron configuration", "Chemistry"),
    ("Earth Day", "Environment"),
    ("Deepwater Horizon oil spill", "Environment"),
    ("Carbon dioxide", "Environment"),
    ("Extinction", "Biology"),
    ("Petroleum", "Environment"),
    ("Cancer", "Medicine"),
    ("Chemical bond", "Chemistry"),
    ("VSEPR theory", "Chemistry"),
    ("Thermodynamics", "Physics"),
    ("Hybrid vehicle", "Technology"),
    ("Supply chain", "Business"),
    ("Renewable energy", "Environment"),
    # Additional articles from the Impact Matrix with templates
    ("Earthrise", "Environment"),
    ("Asbestos", "Environment"),
    ("Biochemistry", "Chemistry"),
    ("Bromide", "Chemistry"),
    ("Kindness", "Biology"),
]

UA_STRING = "MIT OCW Bot/1.0 (https://meta.wikimedia.org/wiki/Wiki_MIT; andrew.lih@gmail.com) ContentGapResearch"


def fetch_talk_page(article_title):
    """Fetch Talk page wikitext for a Wikipedia article."""
    encoded = urllib.parse.quote(article_title.replace(" ", "_"))
    url = (
        f"https://en.wikipedia.org/w/api.php"
        f"?action=parse&page=Talk:{encoded}"
        f"&prop=wikitext&format=json&formatversion=2"
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA_STRING})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            wikitext = data.get("parse", {}).get("wikitext", "")
            return wikitext
    except Exception as e:
        return f"__ERROR__: {e}"


def classify_talk_page(wikitext):
    """
    Classify a Talk page into one of these structural patterns:
    
    A:  Only templates at top (no == sections yet) — bare page
    B:  Templates then == sections — standard pattern
    C:  WikiProject banner shell wrapping multiple projects — grouped banners
    D:  No templates, just == sections — raw discussion
    E:  Has existing {{refideas}} — already tagged
    F:  Complex — banners, templates, tables, todo lists
    G:  Empty — nothing on the page
    """
    if not wikitext or wikitext.startswith("__ERROR__"):
        return "G", "Empty or error"

    # Check for existing Refideas
    if re.search(r'\{\{[Rr]efideas', wikitext):
        return "E", "Has existing Refideas"

    # Count templates at the top (before first == )
    has_sections = bool(re.search(r'\n==', wikitext))
    has_banner_shell = "{{WikiProject banner shell" in wikitext
    has_templates = bool(re.search(r'^\{\{', wikitext, re.MULTILINE))
    
    # Check for complex structures
    has_tables = "{|" in wikitext
    has_todo = "to do" in wikitext.lower() or "To do" in wikitext
    has_miszabot = "MiszaBot" in wikitext
    has_article_history = "article history" in wikitext.lower()
    has_press = "{{press" in wikitext.lower()
    has_GA_review = "good article" in wikitext.lower() or "GA" in wikitext.split("==")[0] if has_sections else False
    
    complex_flags = sum([has_tables, has_todo, has_article_history, has_press, has_GA_review])
    
    if not has_sections and not has_templates:
        return "G", "Empty"
    elif not has_sections and has_templates:
        return "A", "Templates only (no sections)"
    elif has_sections and not has_templates:
        return "D", "Sections only (no templates)"
    elif has_banner_shell:
        # Banner shell = we have WikiProject grouping
        if complex_flags >= 3:
            return "F", "Complex (banner shell + multiple extras)"
        return "C", "Banner shell pattern"
    elif complex_flags >= 3:
        return "F", "Complex (no banner shell, but many extras)"
    else:
        return "B", "Templates then sections (standard)"


def analyze_before_first_section(wikitext):
    """Analyze what's between page start and the first == heading."""
    if not wikitext:
        return {"has_sections": False, "templates_before_section": []}
    
    # Split at first == on its own line
    parts = re.split(r'\n==', wikitext, maxsplit=1)
    preamble = parts[0]
    has_sections = len(parts) > 1
    
    # Count templates in preamble
    templates = re.findall(r'\{\{([A-Za-z][^{}|]*)', preamble)
    template_names = [t.split("|")[0].split("/")[0].strip() for t in templates]
    
    # Find the last closing template bracket before sections
    # This is tricky with nested templates, so we approximate
    last_template_end = 0
    depth = 0
    for i, ch in enumerate(preamble):
        if ch == '{' and i+1 < len(preamble) and preamble[i+1] == '{':
            depth += 1
        elif ch == '}' and i+1 < len(preamble) and preamble[i+1] == '}':
            if depth > 0:
                depth -= 1
                if depth == 0:
                    last_template_end = i + 2
    
    return {
        "has_sections": has_sections,
        "template_count": len(template_names),
        "templates": template_names[:10],
        "preamble_length": len(preamble),
        "last_template_end": last_template_end,
    }


def dry_run_insertion(wikitext, refideas_block="\n{{refideas\n| 1 = [url Label], Source (note)\n}}\n"):
    """
    Simulate inserting {{refideas}} at the right insertion point.
    Returns (strategy, result_wikitext) or (strategy, None) if can't determine.
    """
    if not wikitext or wikitext.startswith("__ERROR__"):
        return "skip_error", None
    
    # Strategy: find the last }} before the first == section and insert after it
    parts = re.split(r'\n==', wikitext, maxsplit=1)
    if len(parts) < 2:
        # No sections — append at end
        return "append_end", wikitext + refideas_block
    
    preamble, rest = parts[0], "==" + parts[1]
    
    # Find the position of the last template closing }} in the preamble
    # by counting nesting depth from the end backward
    depth = 0
    insert_pos = len(preamble)
    end_found = False
    
    for i in range(len(preamble) - 1, -1, -1):
        ch = preamble[i]
        if ch == '}' and i > 0 and preamble[i-1] == '}':
            depth += 1
        elif ch == '{' and i > 0 and preamble[i-1] == '{':
            depth -= 1
            if depth == 0:
                insert_pos = i + 2  # insert after this closing }}
                end_found = True
                break
    
    if not end_found:
        # No template to insert after — insert right before first ==
        insert_pos = len(preamble)
    
    inserted = preamble[:insert_pos] + refideas_block + preamble[insert_pos:]
    result = inserted + "\n" + rest
    
    return "before_sections", result


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "--sample"
    results = []
    
    if cmd in ("--sample", "--full"):
        print(f"Fetching Talk pages for {len(ARTICLE_SAMPLE)} articles...")
        print(f"{'Article':<35} {'Pattern':<5} {'Classification':<45} {'Details'}")
        print("-" * 110)
        
        for article, wikiproject in ARTICLE_SAMPLE:
            print(f"{article:<35} ", end="", flush=True)
            wikitext = fetch_talk_page(article)
            category, desc = classify_talk_page(wikitext)
            analysis = analyze_before_first_section(wikitext)
            
            print(f"{category:<5} {desc:<45} ", end="")
            if analysis["has_sections"]:
                print(f"templates={analysis['template_count']}, preamble={analysis['preamble_length']}b")
            else:
                print(f"no sections, templates={analysis['template_count']}")
            
            results.append({
                "article": article,
                "wikiproject": wikiproject,
                "category": category,
                "description": desc,
                "analysis": analysis,
            })
            
            time.sleep(0.3)  # Be polite to the API
        
        with open("wiki/talk-page-sample-results.json", "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nSaved {len(results)} results to wiki/talk-page-sample-results.json")
    
    if cmd in ("--classify", "--full"):
        if not results:
            with open("wiki/talk-page-sample-results.json") as f:
                results = json.load(f)
        
        # Count patterns
        categories = Counter(r["category"] for r in results)
        print("\n=== Talk Page Pattern Distribution ===")
        for cat in ["A", "B", "C", "D", "E", "F", "G"]:
            count = categories.get(cat, 0)
            pct = count / len(results) * 100 if results else 0
            bar = "█" * int(pct / 2)
            desc_map = {
                "A": "Templates only (no sections)",
                "B": "Templates then sections (standard)",
                "C": "Banner shell pattern",
                "D": "Sections only (no templates)",
                "E": "Has existing Refideas",
                "F": "Complex (many extras)",
                "G": "Empty / error",
            }
            print(f"  {cat} ({desc_map.get(cat, '?'):<35}): {count:>3}  ({pct:>5.1f}%)  {bar}")
        
        # Test dry-run insertion on a few
        if cmd == "--full":
            print("\n=== Dry-run insertion tests ===")
            for r in results[:5]:
                wikitext = fetch_talk_page(r["article"])
                strategy, result = dry_run_insertion(wikitext)
                if result:
                    # Check that {{refideas}} appears in the right place
                    ref_pos = result.find("{{refideas")
                    first_section = result.find("\n==")
                    print(f"\n--- {r['article']} ({strategy}) ---")
                    print(f"  Refideas position: {ref_pos}")
                    print(f"  First == position: {first_section}")
                    print(f"  Inserted before sections: {ref_pos < first_section if first_section > -1 else 'no sections'}")
                    # Show the insertion area
                    start = max(0, ref_pos - 100)
                    end = min(len(result), first_section + 50) if first_section > -1 else min(len(result), ref_pos + 300)
                    print(f"  Context: ...{result[start:end]}...")
                else:
                    print(f"\n--- {r['article']} ({strategy}) — SKIPPED ---")
                time.sleep(0.3)


if __name__ == "__main__":
    main()
