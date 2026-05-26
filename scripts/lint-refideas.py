#!/usr/bin/env python3
"""
Refideas Linter — detect and fix common formatting errors in {{refideas}} templates.

Based on analysis of ~380 randomly sampled Refideas templates on English Wikipedia:
  https://meta.wikimedia.org/wiki/Wiki_MIT/RefIdeas

Handles all 11 template aliases: Refideas, Refidea, RI, Ref ideas, Suggested sources,
Suggested refs, Source ideas, Potential sources, Possible sources, Refideas-nonotice,
Refsuggestion

Usage:
    python3 scripts/lint-refideas.py --fetch "Article title"     # Lint one Talk page
    python3 scripts/lint-refideas.py --fix "Article title"       # Show fix diff (dry run)
    python3 scripts/lint-refideas.py --sample 50                 # Lint random sample (cached)
    python3 scripts/lint-refideas.py --classify "Article"        # Classify ref types on one page
    python3 scripts/lint-refideas.py --classify 30               # Classify across random sample

First --sample or --classify run paginates ~29K pages (~30s) and caches to
.wiki_cache/. Subsequent runs load from cache instantly.

Error types detected:
    multi_bullet  🔴 Multiple references crammed into one param with bullet syntax
    bullet_syntax 🔴 Parameter uses |* url or has * as parameter name
    duplicate_url 🟡 Same URL appears in multiple parameters
    unnumbered    🟡 Positional parameter that should be numbered
    param_spacing 🟡 Extra whitespace in parameter names
    bare_url      ℹ️  URL without [url Label] format — valid but less readable
"""

import sys
import json
import os
import re
import random
import time
import urllib.request
import urllib.parse
from collections import Counter
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

try:
    import mwparserfromhell
    HAS_MWPARSER = True
except ImportError:
    HAS_MWPARSER = False

UA = "MIT OCW Bot/1.0 (https://meta.wikimedia.org/wiki/Wiki_MIT; andrew.lih@gmail.com) ContentGapResearch"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"


# ─── All known Refideas template aliases ───────────────────────────────────

REFIDEAS_ALIASES = [
    "refideas",           # canonical (case-insensitive)
    "refidea",            # singular
    "ri",                 # shortcut
    "ref ideas",          # spaced
    "suggested sources",  # redirect
    "suggested refs",     # redirect
    "source ideas",       # redirect
    "potential sources",  # redirect
    "possible sources",   # redirect
    "refideas-nonotice",  # redirect (suppresses editnotice)
    "refsuggestion",      # redirect
]


# ─── Domain classification sets (from refideas_analyzer.py) ──────────────

ACADEMIC_DOMAINS = {
    "jstor.org", "pubmed.ncbi.nlm.nih.gov", "arxiv.org", "doi.org",
    "springer.com", "elsevier.com", "wiley.com", "nature.com",
    "sciencedirect.com", "sagepub.com", "tandfonline.com",
    "researchgate.net", "academia.edu", "scholar.google.com",
    "ncbi.nlm.nih.gov", "pubmed.gov", "ieee.org", "acm.org",
    "frontiersin.org", "plos.org", "mdpi.com", "hindawi.com",
    "cambridge.org", "oxfordjournals.org", "emerald.com",
    "taylorfrancis.com", "scielo.org", "bmj.com",
    "ocw.mit.edu", "mit.edu",
}

NEWS_DOMAINS = {
    "nytimes.com", "washingtonpost.com", "bbc.com", "reuters.com",
    "apnews.com", "theguardian.com", "cnn.com", "foxnews.com",
    "npr.org", "abcnews.go.com", "nbcnews.com", "cbsnews.com",
    "msnbc.com", "latimes.com", "chicagotribune.com",
    "independent.co.uk", "telegraph.co.uk", "usatoday.com",
    "wsj.com", "bloomberg.com", "politico.com", "huffpost.com",
    "newsweek.com", "time.com", "theatlantic.com", "voanews.com",
    "aljazeera.com", "dw.com", "france24.com", "news.google.com",
}

ARCHIVE_DOMAINS = {
    "archive.org", "web.archive.org", "loc.gov", "archives.gov",
    "digital.library.upenn.edu", "library.of.congress.gov",
    "bl.uk", "gallica.bnf.fr", "europeana.eu", "digitale-sammlungen.de",
}

GOVERNMENT_DOMAINS = {
    ".gov", ".mil", "gov.uk", "gc.ca", "gov.au", "govt.nz",
    "parliament.uk", "senate.gov", "house.gov", "whitehouse.gov",
}

DATABASE_DOMAINS = {
    "imdb.com", "discogs.com", "musicbrainz.org", "wikidata.org",
    "project-gutenberg.org", "openlibrary.org", "goodreads.com",
    "isbnsearch.org", "biblegateway.com", "ctan.org",
    "npmjs.com", "pypi.org", "github.com", "sourceforge.net",
}

SOCIAL_MEDIA_DOMAINS = {
    "twitter.com", "x.com", "youtube.com", "facebook.com",
    "instagram.com", "reddit.com", "tiktok.com", "linkedin.com",
    "flickr.com", "vimeo.com", "soundcloud.com", "spotify.com",
}

ENCYCLOPEDIA_DOMAINS = {"britannica.com", "worldcat.org", "encyclopedia.com"}


# ─── Error types ───────────────────────────────────────────────────────────

@dataclass
class LintError:
    type: str           # error category
    severity: str       # "warning" or "error"
    message: str        # human description
    param_num: Optional[int] = None
    original: str = ""  # the problematic text
    fixed: str = ""     # the corrected text

@dataclass
class LintResult:
    article: str
    talk_page: str
    template_count: int       # how many refideas templates found
    template_alias_used: str  # which alias was used
    param_count: int          # total parameters across all templates
    errors: List[LintError] = field(default_factory=list)
    
    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0
    
    @property
    def has_actionable_errors(self) -> bool:
        """True if there are error or warning level issues (not just info)."""
        return any(e.severity in ("error", "warning") for e in self.errors)
    
    @property
    def actionable_count(self) -> int:
        """Count of error + warning level issues."""
        return sum(1 for e in self.errors if e.severity in ("error", "warning"))
    
    @property
    def info_count(self) -> int:
        """Count of info-level notices."""
        return sum(1 for e in self.errors if e.severity == "info")
    
    @property
    def error_count(self) -> int:
        return len(self.errors)
    
    @property
    def fixable_count(self) -> int:
        return sum(1 for e in self.errors if e.fixed)


# ─── Linter logic ──────────────────────────────────────────────────────────

def find_refideas_templates(code) -> List:
    """Find all Refideas template nodes (any alias)."""
    return code.filter_templates(
        matches=lambda t: str(t.name).lower().strip() in REFIDEAS_ALIASES
    )

def get_refideas_alias_used(code) -> Optional[str]:
    """Return which alias is used, or None if no Refideas found."""
    templates = find_refideas_templates(code)
    if not templates:
        return None
    return str(templates[0].name).strip()

def lint_refideas_templates(wikitext: str, article_title: str) -> LintResult:
    """Lint all Refideas templates on a Talk page."""
    if not HAS_MWPARSER:
        return LintResult(article_title, "", 0, "", 0, 
                         [LintError("setup", "error", "mwparserfromhell not installed")])
    
    code = mwparserfromhell.parse(wikitext)
    templates = find_refideas_templates(code)
    
    if not templates:
        return LintResult(article_title, f"Talk:{article_title}", 0, "", 0)
    
    alias = get_refideas_alias_used(code)
    result = LintResult(
        article=article_title,
        talk_page=f"Talk:{article_title}",
        template_count=len(templates),
        template_alias_used=alias or "",
        param_count=sum(len(t.params) for t in templates),
    )
    
    for tmpl in templates:
        _lint_bullet_syntax(tmpl, result)
        _lint_bare_urls(tmpl, result)
        _lint_unnumbered_params(tmpl, result)
        _lint_duplicate_urls(tmpl, result)
        _lint_param_name_spacing(tmpl, result)
    
    return result


def _lint_bullet_syntax(tmpl, result: LintResult):
    """Detect parameters using bullet syntax: |* url, | * url, or multi-bullet values."""
    for param in tmpl.params:
        value = str(param.value).strip()
        name = str(param.name).strip()
        
        # Case: parameter name IS * (e.g., |* = https://...)
        if name == "*":
            result.errors.append(LintError(
                type="bullet_syntax",
                severity="error",
                message="Parameter name is '*' instead of a number",
                original=f"|*={value[:80]}",
                fixed=_suggest_numbered_param(tmpl, value),
            ))
        # Case: value starts with * — could be single or multi-bullet
        elif value.startswith("* "):
            # Check if there are MULTIPLE bullet items in the same value
            bullets = re.split(r'\n\s*\*\s+', value)
            if bullets[0].startswith("* "):
                bullets[0] = bullets[0][2:]
            if len(bullets) > 1:
                # Multi-bullet: multiple references crammed into one parameter
                result.errors.append(LintError(
                    type="multi_bullet",
                    severity="error",
                    message=f"{len(bullets)} references crammed into param '{name}' using bullet syntax — should be separate numbered params",
                    original=f"|{name}=* {bullets[0][:60]}... (+{len(bullets)-1} more)",
                    fixed=_suggest_split_bullets(tmpl, name, bullets),
                ))
            else:
                # Single bullet: just a leading * to strip
                result.errors.append(LintError(
                    type="bullet_syntax",
                    severity="error",
                    message=f"Bullet syntax in param '{name}': value starts with '* '",
                    original=f"|{name}=* {value[2:80]}",
                    fixed=f"|{name}={value[2:].strip()}",
                ))


def _lint_bare_urls(tmpl, result: LintResult):
    """Detect bare URLs without a label: |1=https://example.com (no [url Label] format)"""
    for param in tmpl.params:
        value = str(param.value).strip()
        name = str(param.name).strip()
        
        # Check if value is a bare URL (starts with http but not in [url Label] format)
        if value.startswith(("http://", "https://")) and not value.startswith("[http"):
            result.errors.append(LintError(
                type="bare_url",
                severity="info",
                message=f"Bare URL in param '{name}' — should use [url Label] format for readability",
                original=f"|{name}={value[:80]}{'...' if len(value) > 80 else ''}",
                fixed="",  # No auto-fix: need meaningful label from page
            ))


def _lint_unnumbered_params(tmpl, result: LintResult):
    """Detect positional params (no = sign) and unnumbered params."""
    for param in tmpl.params:
        name = str(param.name).strip()
        value = str(param.value).strip()
        
        # Positional params: value is a URL or text but has no name
        # In mwparserfromhell, positional params have name as their position number (as string)
        # We check for params that look like they should be numbered
        if name.isdigit():
            continue  # Already properly numbered
        
        if name in ("comment", "state", "small"):
            continue  # These are valid named params
        
        if not name:
            # Empty param name — likely positional
            result.errors.append(LintError(
                type="unnumbered_param",
                severity="warning",
                message=f"Positional/unnamed parameter: value starts with '{value[:40]}...'",
                original=f"|{value[:60]}...",
                fixed=_suggest_numbered_param(tmpl, value),
            ))


def _lint_duplicate_urls(tmpl, result: LintResult):
    """Detect the same URL appearing in multiple parameters."""
    seen_urls = {}
    for param in tmpl.params:
        value = str(param.value).strip()
        name = str(param.name).strip()
        
        # Extract URL from the value.
        # Note: } is NOT in the exclusion set — URLs may contain wiki
        # variables like {{CURRENTYEAR}}. Instead, strip trailing }}
        # (wiki template close braces) after matching.
        url_match = re.search(r'(https?://[^\s|\]<>]+)', value)
        if url_match:
            url = url_match.group(1)
            while url.endswith('}}'):
                url = url[:-2]
            url = url.rstrip('.,;:')
            if url in seen_urls:
                result.errors.append(LintError(
                    type="duplicate_url",
                    severity="warning",
                    message=f"Duplicate URL in param '{name}': also appears in param '{seen_urls[url]}'",
                    original=url,
                    fixed=f"Remove duplicate of param '{seen_urls[url]}'",
                ))
            else:
                seen_urls[url] = name


def _lint_param_name_spacing(tmpl, result: LintResult):
    """Detect inconsistent spacing in parameter names."""
    for param in tmpl.params:
        name = str(param.name)
        if name.isdigit() and name != name.strip():
            result.errors.append(LintError(
                type="param_spacing",
                severity="warning",
                message=f"Extra whitespace in param name: '{name}' should be '{name.strip()}'",
                original=f"|{name}=",
                fixed=f"|{name.strip()}=",
            ))


def _suggest_numbered_param(tmpl, value: str) -> str:
    """Suggest a numbered parameter format for a bare value."""
    max_num = 0
    for p in tmpl.params:
        try:
            n = int(str(p.name).strip())
            max_num = max(max_num, n)
        except ValueError:
            pass
    new_num = max_num + 1
    return f"|{new_num}={value}"


def _suggest_split_bullets(tmpl, original_name: str, bullets: list) -> str:
    """Suggest splitting a multi-bullet parameter into separate numbered params."""
    max_num = 0
    for p in tmpl.params:
        try:
            n = int(str(p.name).strip())
            max_num = max(max_num, n)
        except ValueError:
            pass
    
    lines = []
    for i, bullet in enumerate(bullets):
        num = max_num + i + 1
        lines.append(f"|{num}={bullet.strip()}")
    return "\n".join(lines)


# ─── Fix generation ────────────────────────────────────────────────────────

def generate_fix(wikitext: str, article_title: str) -> Tuple[str, List[LintError], str]:
    """
    Generate a fixed version of the wikitext.
    Returns (fixed_wikitext, errors, diff_summary).
    """
    if not HAS_MWPARSER:
        return wikitext, [], "mwparserfromhell not installed"
    
    code = mwparserfromhell.parse(wikitext)
    templates = find_refideas_templates(code)
    
    if not templates:
        return wikitext, [], "No Refideas templates found"
    
    errors = []
    fixes_applied = 0
    
    for tmpl in templates:
        # Capture original template text BEFORE any modifications
        old_tmpl_text = str(tmpl)
        
        # First pass: deduplicate URLs (keep first, remove rest)
        seen_urls = {}
        for param in list(tmpl.params):
            pval = str(param.value).strip()
            pmatch = re.search(r'(https?://[^\s|\]<>]+)', pval)
            if pmatch:
                url = pmatch.group(1)
                while url.endswith('}}'):
                    url = url[:-2]
                url = url.rstrip('.,;:')
                if url in seen_urls:
                    tmpl.remove(param)
                    errors.append(LintError(
                        type="duplicate_url", severity="warning",
                        message=f"Removed duplicate of param '{seen_urls[url]}'",
                        original=str(pval)[:80],
                        fixed="(removed)",
                    ))
                    fixes_applied += 1
                else:
                    seen_urls[url] = str(param.name).strip()
        
        # If we removed params, serialize with preserved numbering
        if fixes_applied > 0 and not any(
            str(p.value).strip().startswith("* ") for p in tmpl.params
        ):
            all_vals = []
            for p in tmpl.params:
                v = str(p.value).strip()
                n = str(p.name).strip()
                # Preserve non-reference params (state, comment, small)
                if n in ("comment", "state", "small"):
                    all_vals.append(f"{n}={v}")
                elif n.isdigit():
                    all_vals.append(f"{n}={v}")
            ref_lines = ["{{refideas"]
            for v in all_vals:
                ref_lines.append(f"|{v}")
            ref_lines.append("}}")
            new_block = "\n".join(ref_lines)
            result_wikitext = wikitext.replace(old_tmpl_text, new_block)
            return result_wikitext, errors, f"{fixes_applied} fix(es) applied"
        
        # Second pass: fix bullet syntax and multi-bullet
        for param in list(tmpl.params):
            value = str(param.value).strip()
            name = str(param.name).strip()
            
            if name == "*":
                # Rename * param to next numbered param
                max_num = max(
                    (int(str(p.name).strip()) for p in tmpl.params 
                     if str(p.name).strip().isdigit()),
                    default=0
                )
                new_name = str(max_num + 1)
                param.name = new_name
                errors.append(LintError(
                    type="bullet_syntax", severity="error",
                    message=f"Fixed: renamed '*' parameter to '{new_name}'",
                    original=f"|*={value[:60]}",
                    fixed=f"|{new_name}={value[:60]}",
                ))
                fixes_applied += 1
            
            elif value.startswith("* "):
                bullets = re.split(r'\n\s*\*\s+', value)
                # Strip leading * from first bullet too
                if bullets[0].startswith("* "):
                    bullets[0] = bullets[0][2:]
                if len(bullets) > 1:
                    # Multi-bullet: remove this param, add separate numbered params
                    # Build a clean, readable refideas block
                    ref_lines = ["{{refideas"]
                    for i, bullet in enumerate(bullets):
                        ref_lines.append(f"|{bullet.strip()}")
                    ref_lines.append("}}")
                    new_block = "\n".join(ref_lines)
                    result_wikitext = wikitext.replace(old_tmpl_text, new_block)
                    
                    errors.append(LintError(
                        type="multi_bullet", severity="error",
                        message=f"Fixed: split {len(bullets)} bullet items into separate lines",
                        original=f"|{name}=* {bullets[0][:40]}... (+{len(bullets)-1} more)",
                        fixed=f"→ {len(bullets)} separate params",
                    ))
                    fixes_applied += 1
                    return result_wikitext, errors, f"{fixes_applied} fix(es) applied"
                else:
                    # Single bullet: reformat the entire template with proper newlines
                    # Get all current param values
                    all_vals = []
                    for p in list(tmpl.params):
                        v = str(p.value).strip()
                        n = str(p.name).strip()
                        if n in ("comment", "state", "small"):
                            continue
                        # Strip leading * from this param
                        if v.startswith("* "):
                            v = v[2:]
                        # Preserve numbering: |1=value vs |value
                        if n.isdigit():
                            all_vals.append(f"{n}={v}")
                        elif n in ("comment", "state", "small"):
                            all_vals.append(f"{n}={v}")
                        else:
                            all_vals.append(v)
                    
                    # Build clean multi-line refideas block
                    ref_lines = ["{{refideas"]
                    for v in all_vals:
                        ref_lines.append(f"|{v}")
                    ref_lines.append("}}")
                    new_block = "\n".join(ref_lines)
                    result_wikitext = wikitext.replace(old_tmpl_text, new_block)
                    
                    errors.append(LintError(
                        type="bullet_syntax", severity="error",
                        message=f"Fixed: reformatted template with proper newlines",
                        original=f"|{name}=* {value[2:60]}",
                        fixed=f"multi-line refideas block",
                    ))
                    fixes_applied += 1
                    return result_wikitext, errors, f"{fixes_applied} fix(es) applied"
            
            elif value.startswith(("http://", "https://")) and not value.startswith("[http"):
                # Bare URL: skip auto-fix (no meaningful label without scraping)
                pass
    
    fixed_wikitext = str(code)
    diff_summary = f"{fixes_applied} fix(es) applied, {len(errors)} issue(s) found"
    
    return fixed_wikitext, errors, diff_summary


# ─── Display ────────────────────────────────────────────────────────────────

def print_lint_report(result: LintResult):
    """Print a human-readable lint report."""
    print(f"\n{'='*70}")
    print(f"  Refideas Lint Report: {result.article}")
    print(f"  Talk page: {result.talk_page}")
    print(f"{'='*70}")
    
    if result.template_count == 0:
        print("  No Refideas templates found on this page.")
        return
    
    print(f"  Templates found: {result.template_count}")
    alias = result.template_alias_used or "(none)"
    print(f"  Alias used: {{{alias}}}")
    print(f"  Total parameters: {result.param_count}")
    
    if not result.has_errors:
        print(f"\n  ✅ No issues found. Template looks well-formed.")
        return
    
    if result.has_actionable_errors:
        print(f"\n  ❌ {result.actionable_count} actionable issue(s) found", end="")
        if result.info_count:
            print(f" (+{result.info_count} info notices)", end="")
        print(f" — {result.fixable_count} fixable:\n")
    else:
        print(f"\n  ℹ️  {result.info_count} info notice(s) — no actionable issues:\n")
    
    for i, e in enumerate(result.errors, 1):
        icon = "🔴" if e.severity == "error" else ("🟡" if e.severity == "warning" else "ℹ️ ")
        print(f"  {icon} [{e.type}] {e.message}")
        if e.original and e.fixed:
            print(f"     Before: {e.original[:90]}")
            print(f"     After:  {e.fixed[:90]}")
        print()


def print_fix_diff(original: str, fixed: str, article: str):
    """Print a side-by-side diff of the fix."""
    import difflib
    
    orig_lines = original.splitlines()
    fixed_lines = fixed.splitlines()
    
    differ = difflib.unified_diff(
        orig_lines, fixed_lines,
        fromfile=f"Talk:{article} (original)",
        tofile=f"Talk:{article} (fixed)",
        lineterm="",
    )
    
    print(f"\n{'='*70}")
    print(f"  Proposed Fix: {article}")
    print(f"{'='*70}\n")
    
    diff_lines = list(differ)
    if diff_lines:
        for line in diff_lines:
            print(line)
    else:
        print("  No changes needed.")


# ─── Page fetching ────────────────────────────────────────────────────────

def get_pages_using_template(template_title: str, use_cache: bool = True) -> list:
    """
    Fetch ALL pages transcluding a template using embeddedin API.
    Paginates through all results, caches to disk for reuse.
    """
    cache_file = f".wiki_cache/{template_title.replace(':', '_').replace(' ', '_')}_pages.json"
    os.makedirs(".wiki_cache", exist_ok=True)
    
    if use_cache and os.path.exists(cache_file):
        with open(cache_file) as f:
            cached = json.load(f)
        # Empty list is a valid cache result (no pages found)
        if isinstance(cached, list):
            print(f"  Cache hit: {template_title} ({len(cached)} pages)", file=sys.stderr)
            return cached
    
    print(f"  Fetching: {template_title}...", file=sys.stderr)
    all_pages = []
    params = {
        "action": "query",
        "list": "embeddedin",
        "eititle": template_title,
        "einamespace": "1",
        "eilimit": "500",
        "format": "json",
        "formatversion": "2",
    }
    
    page_count = 0
    while True:
        url = WIKIPEDIA_API + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            print(f"    Error: {e}", file=sys.stderr)
            break
        
        pages = data.get("query", {}).get("embeddedin", [])
        for p in pages:
            title = p["title"]
            if title.startswith("Talk:"):
                all_pages.append(title[5:])
        page_count += len(pages)
        
        if "continue" in data:
            params["eicontinue"] = data["continue"]["eicontinue"]
            if page_count % 1000 == 0:
                print(f"    {page_count} pages...", file=sys.stderr)
            time.sleep(0.3)
        else:
            break
    
    print(f"    Done: {len(all_pages)} pages", file=sys.stderr)
    
    # Always cache the result, even if empty
    with open(cache_file, "w") as f:
        json.dump(all_pages, f)
    
    return all_pages


def fetch_all_refideas_pages() -> list:
    """
    Fetch all pages using the canonical Refideas template.
    Only fetches the main template (not aliases) since redirects don't
    appear in embeddedin results — they all resolve to Template:Refideas.
    """
    pages = get_pages_using_template("Template:Refideas")
    return pages


def fetch_random_refideas_sample(count: int = 50) -> List[str]:
    """
    Fetch a genuinely random sample of articles using Refideas.
    Loads the full population from cache, then random.sample().
    First run paginates ~29K pages (~30s); subsequent runs are instant.
    """
    t0 = time.time()
    all_pages = fetch_all_refideas_pages()
    t1 = time.time()
    print(f"  Population: {len(all_pages)} pages (loaded in {t1 - t0:.1f}s)", file=sys.stderr)
    if len(all_pages) <= count:
        return all_pages
    return random.sample(all_pages, count)


# ─── Fetch a single page's wikitext ───────────────────────────────────────

def fetch_talk_wikitext(article_title: str) -> str:
    """Fetch Talk page wikitext for a Wikipedia article."""
    # URL-decode first to handle already-encoded titles from API cache
    decoded = urllib.parse.unquote(article_title)
    encoded = urllib.parse.quote(decoded.replace(" ", "_"), safe="")
    url = (
        f"{WIKIPEDIA_API}"
        f"?action=parse&page=Talk:{encoded}"
        f"&prop=wikitext&format=json&formatversion=2"
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            return data.get("parse", {}).get("wikitext", "")
    except Exception as e:
        return f"__ERROR__: {e}"


# ─── Reference classification ──────────────────────────────────────────────

def extract_domains(ref_text: str) -> list:
    """Extract unique domains from URLs in reference text."""
    urls = re.findall(r'https?://[^\s\]\|>]+', ref_text, re.IGNORECASE)
    domains = []
    for url in urls:
        try:
            parsed = urllib.parse.urlparse(url)
            if parsed.netloc:
                domains.append(parsed.netloc.lower())
        except Exception:
            pass
    return domains


def classify_reference(ref_text: str) -> str:
    """
    Classify a single Refideas reference entry by type.
    Returns one of: citation_template, archive, government, academic_journal,
    news_organization, database, social_media, encyclopedia, book,
    wiki_article, url, other, empty
    """
    ref_clean = ref_text.strip()
    if not ref_clean:
        return "empty"
    
    has_url = bool(re.search(r'https?://[^\s\]\|>]+', ref_clean, re.IGNORECASE))
    has_wikilink = bool(re.search(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', ref_clean))
    has_cite_template = bool(re.search(r'\{\{\s*cite[^{]*\{?', ref_clean, re.IGNORECASE))
    
    if has_cite_template:
        return "citation_template"
    
    if has_url:
        domains = extract_domains(ref_clean)
        for domain in domains:
            if "archive.org" in domain or "web.archive.org" in domain:
                return "archive"
            for domain_set, category in [
                (GOVERNMENT_DOMAINS, "government"),
                (ACADEMIC_DOMAINS, "academic_journal"),
                (NEWS_DOMAINS, "news_organization"),
                (DATABASE_DOMAINS, "database"),
                (SOCIAL_MEDIA_DOMAINS, "social_media"),
                (ENCYCLOPEDIA_DOMAINS, "encyclopedia"),
            ]:
                if any(domain.endswith(d) or d in domain for d in domain_set):
                    return category
        return "url"
    
    if has_wikilink and not has_url:
        return "wiki_article"
    
    return "other"


def classify_refideas_page(wikitext: str) -> Dict[str, int]:
    """Classify all references on a page and return type counts."""
    if not HAS_MWPARSER:
        return {}
    
    code = mwparserfromhell.parse(wikitext)
    templates = find_refideas_templates(code)
    
    ref_types = []
    for tmpl in templates:
        for param in tmpl.params:
            value = str(param.value).strip()
            name = str(param.name).strip()
            # Skip non-reference params like comment, state, small
            if name in ("comment", "state", "small"):
                continue
            if value:
                ref_types.append(classify_reference(value))
    
    return dict(Counter(ref_types))


# ─── CLI ────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    
    cmd = sys.argv[1]
    
    if cmd == "--fetch":
        article = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "Boeing"
        print(f"Fetching Talk:{article}...")
        wikitext = fetch_talk_wikitext(article)
        if wikitext.startswith("__ERROR__"):
            print(f"Error: {wikitext}")
            return
        result = lint_refideas_templates(wikitext, article)
        print_lint_report(result)
    
    elif cmd == "--fix":
        article = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "Boeing"
        print(f"Fetching Talk:{article}...")
        wikitext = fetch_talk_wikitext(article)
        if wikitext.startswith("__ERROR__"):
            print(f"Error: {wikitext}")
            return
        
        result = lint_refideas_templates(wikitext, article)
        print_lint_report(result)
        
        if result.has_errors and result.fixable_count > 0:
            fixed, errors, summary = generate_fix(wikitext, article)
            print_fix_diff(wikitext, fixed, article)
    
    elif cmd == "--sample":
        count = int(sys.argv[2]) if len(sys.argv) > 2 else 50
        print(f"Fetching {count} random Refideas Talk pages (paginating all, cached)...", file=sys.stderr)
        articles = fetch_random_refideas_sample(count)
        
        print(f"\nLinting {len(articles)} pages...")
        total = 0
        clean = 0
        with_errors = 0
        error_types = {}
        
        for i, article in enumerate(articles):
            if (i + 1) % 10 == 0:
                print(f"  {i+1}/{len(articles)}...", file=sys.stderr)
            wikitext = fetch_talk_wikitext(article)
            if wikitext.startswith("__ERROR__"):
                continue
            result = lint_refideas_templates(wikitext, article)
            total += 1
            if result.has_actionable_errors:
                with_errors += 1
                for e in result.errors:
                    if e.severity in ("error", "warning"):
                        error_types[e.type] = error_types.get(e.type, 0) + 1
                print(f"  ❌ {article}: {result.actionable_count} issue(s){f' (+{result.info_count} notices)' if result.info_count else ''} — {result.template_alias_used}")
                for e in result.errors:
                    if e.severity in ("error", "warning"):
                        print(f"     [{e.type}] {e.message[:80]}")
            elif result.has_errors:
                # Info-level notices only — show each one compactly
                print(f"  ℹ️  {article}: {result.info_count} notice(s) — {result.template_alias_used}")
                for e in result.errors:
                    print(f"     {e.message}")
            else:
                clean += 1
                print(f"  ✅ {article}: OK — {result.template_alias_used}")
        
        print(f"\n{'='*70}")
        print(f"  Sample Results: {clean} clean, {with_errors} with issues, {total - clean - with_errors} with notices")
        if error_types:
            print(f"  Error breakdown:")
            for etype, count in sorted(error_types.items(), key=lambda x: -x[1]):
                print(f"    {etype}: {count}")
    
    elif cmd == "--classify":
        article = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else None
        if article:
            # Single page
            wikitext = fetch_talk_wikitext(article)
            if wikitext.startswith("__ERROR__"):
                print(f"Error: {wikitext}")
                return
            counts = classify_refideas_page(wikitext)
            total = sum(counts.values())
            print(f"\n=== Reference Type Classification: {article} ===")
            print(f"Total references: {total}\n")
            for ref_type, count in sorted(counts.items(), key=lambda x: -x[1]):
                pct = count / total * 100 if total else 0
                bar = "█" * int(pct / 2)
                print(f"  {ref_type:25s}: {count:3d} ({pct:5.1f}%) {bar}")
        else:
            # Sample mode
            count = int(sys.argv[3]) if len(sys.argv) > 3 else 30
            print(f"Classifying references on {count} random Refideas pages...", file=sys.stderr)
            articles = fetch_random_refideas_sample(count)
            all_counts = Counter()
            for article in articles:
                wikitext = fetch_talk_wikitext(article)
                if wikitext.startswith("__ERROR__"):
                    continue
                counts = classify_refideas_page(wikitext)
                all_counts.update(counts)
                time.sleep(0.3)
            
            total = sum(all_counts.values())
            print(f"\n=== Reference Type Distribution ({len(articles)} pages, {total} references) ===\n")
            for ref_type, count in all_counts.most_common():
                pct = count / total * 100 if total else 0
                bar = "█" * int(pct / 2)
                print(f"  {ref_type:25s}: {count:5d} ({pct:5.1f}%) {bar}")
    
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
