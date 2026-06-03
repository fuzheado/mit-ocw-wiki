#!/usr/bin/env python3
"""
Ad-hoc match: find the best Wikipedia articles for any MIT OCW course.

Full reference:
  docs/AD-HOC-MATCH.md — full algorithm: match sources, filter layers, scoring formula, page type detection
  docs/L1-REFIDEAS.md — L1 refideas algorithm
  docs/L2-EXTERNAL-LINKS.md — L2 external links algorithm
  docs/CONTRIBUTION-LEVELS.md — L1-L5 contribution levels

Filters out low-quality matches:
  - Glossary/list/outline/disambiguation pages (detected via API + title heuristics)
  - Overly broad single-field articles ("Computer science", "Mathematics", "Physics")
  - Named entities (schools, universities, companies) on weak matches
  - Topic-only matches with no course-title word overlap

Usage:
    # Find matches, show ranked list (stdout)
    python3 scripts/ad-hoc-match.py "6-s897-machine-learning-for-healthcare-spring-2019"
    python3 scripts/ad-hoc-match.py "https://ocw.mit.edu/courses/6-s897-.../"
    python3 scripts/ad-hoc-match.py "6.S897"

    # Limit results
    python3 scripts/ad-hoc-match.py 6.S897 --top 5

    # L2 mode + interactive diff/posting
    python3 scripts/ad-hoc-match.py 6.S897 --mode L2 --interactive

    # Dry-run interactive (preview only, no posting)
    python3 scripts/ad-hoc-match.py 6.S897 --mode L1 --interactive --dry-run

    # Select matching strategy (pluggable providers)
    python3 scripts/ad-hoc-match.py 6.S897 --provider corpus         # pre-computed only
    python3 scripts/ad-hoc-match.py 6.S897 --provider wikipedia      # Wikipedia search only
    python3 scripts/ad-hoc-match.py 6.S897 --provider "corpus,wikipedia"  # custom combo

Available providers:
  corpus      Pre-computed matches from live-matches.json (220 courses, 157 articles)
  wikipedia   Wikipedia Search API by course title
  acronym     Expands MIT→Massachusetts Institute of Technology, searches again
  simplified  Strips qualifiers ("for Healthcare" → "Machine Learning"), fallback only

Default: --provider corpus,wikipedia,acronym,simplified
"""

import sys
import os
import json
import re
import urllib.request
import urllib.parse
import importlib.util

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
WIKI_COURSES_DIR = os.path.abspath(os.path.join(SCRIPTS_DIR, "..", "wiki", "courses"))
CACHE_DIR = os.path.abspath(os.path.join(SCRIPTS_DIR, "..", ".wiki_cache"))
LIVE_MATCHES_PATH = os.path.join(CACHE_DIR, "live-matches.json")

sys.path.insert(0, SCRIPTS_DIR)

# Import shared utilities
_add_spec = importlib.util.spec_from_file_location(
    "refideas_add_cli",
    os.path.join(SCRIPTS_DIR, "refideas-add.py")
)
_add = importlib.util.module_from_spec(_add_spec)
_add_spec.loader.exec_module(_add)

_proto_spec = importlib.util.spec_from_file_location(
    "contribution_protocol",
    os.path.join(SCRIPTS_DIR, "contribution-protocol.py")
)
_proto = importlib.util.module_from_spec(_proto_spec)
_proto_spec.loader.exec_module(_proto)

UA = _add.UA
WIKIPEDIA_API = _add.WIKIPEDIA_API
colorize = _add.colorize
Color = _add.Color


# ══════════════════════════════════════════════════════════════════════════════
# FILTERS: Exclude low-quality matches
# ══════════════════════════════════════════════════════════════════════════════

# Broad single-field articles that are too generic to be useful targets
BROAD_FIELD_ARTICLES = {
    "computer science", "mathematics", "physics", "chemistry", "biology",
    "engineering", "science", "technology", "history", "literature",
    "philosophy", "economics", "psychology", "sociology", "political science",
    "anthropology", "linguistics", "geography", "art", "music", "law",
    "medicine", "public health", "business", "management", "education",
    "materials science", "earth science", "environmental science",
    "data science", "artificial intelligence", "machine learning",
}

# Title patterns that mark glossary, list, outline, or index pages
JUNK_TITLE_PREFIXES = (
    "glossary of", "list of", "outline of", "index of", "timeline of",
    "table of", "bibliography of", "classification of",
)

# Known acronyms and their expansions, used to bridge semantic gaps
# between course titles and Wikipedia article titles.
# e.g., "The History of MIT" → also search "The History of Massachusetts Institute of Technology"
ACRONYM_MAP = {
    "mit": "massachusetts institute of technology",
    "ocw": "opencourseware",
}

# Generic category words that don't contribute to specificity scoring.
# These describe the scope/type of a course rather than its subject matter.
# Examples: "History of France" vs "Libertarianism in History" — both share "History"
# but are about completely different things.
GENERIC_CATEGORY_WORDS = {
    'history', 'introduction', 'principles', 'fundamentals',
    'foundations', 'basics', 'overview', 'survey',
    'topics', 'concepts', 'applications', 'theory',
    'methods', 'techniques', 'analysis', 'dynamics',
    'systems', 'processes', 'design', 'modeling',
}

# Geo-locale articles: "Mass media in Cambodia", "Solar power in the United Kingdom" —
# a general MIT course isn't uniquely useful for country-specific articles unless the
# course itself is about that location (checked via course title overlap).
GEO_LOCALES = [
    # Countries
    "in the united kingdom", "in the united states", "in the republic of", "in the netherlands",
    "in the philippines", "in the united arab", "in the dominican republic", "in the czech republic",
    "in india", "in china", "in japan", "in germany", "in france", "in canada", "in australia",
    "in brazil", "in russia", "in italy", "in spain", "in mexico", "in south korea",
    "in south africa", "in argentina", "in indonesia", "in turkey", "in saudi arabia",
    "in nigeria", "in egypt", "in poland", "in thailand", "in vietnam", "in iran",
    "in sweden", "in norway", "in denmark", "in finland", "in ireland", "in portugal",
    "in israel", "in switzerland", "in singapore", "in malaysia", "in pakistan",
    "in bangladesh", "in kenya", "in ghana", "in cambodia", "in nepal",
    # US states
    "in california", "in texas", "in new york", "in florida", "in massachusetts",
    "in illinois", "in pennsylvania", "in ohio", "in michigan", "in georgia",
    "in north carolina", "in washington", "in arizona", "in colorado",
    # Major cities
    "in london", "in paris", "in tokyo", "in berlin", "in rome", "in moscow",
    "in beijing", "in shanghai", "in dubai", "in hong kong", "in singapore",
    # Regions
    "in scotland", "in wales", "in england", "in catalonia", "in quebec",
    "in scandinavia", "in southeast asia", "in latin america", "in sub-saharan africa",
    " in europe", " in asia", " in africa",
    # Generic
    " by country",
    # Also catch "of <country>" patterns (Culture of Cambodia, History of France, etc.)
    # These are filtered unless the course title contains the country name
    "of cambodia", "of thailand", "of vietnam", "of myanmar", "of kenya", "of ghana",
    "of nigeria", "of egypt", "of morocco", "of algeria", "of chile", "of peru",
]


def is_geo_limited_article(title: str, course_title: str) -> bool:
    """Check if article is a "Topic in Location" pattern where the course
    isn't specifically about that location.
    
    Returns True if the article should be filtered out.
    Example: "Mass media in Cambodia" for course "Machine Learning for Healthcare"
    → filtered (no "Cambodia" in course). But for a course "Cambodian History" → kept.
    """
    lower_title = title.lower()
    lower_course = course_title.lower()

    for loc in GEO_LOCALES:
        if loc in lower_title:
            # Extract the location name from the pattern
            # "in cambodia" → check if "cambodia" appears in course title
            location_word = loc.replace("in the ", "").replace("in ", "").replace(" by country", "")
            # Check if any significant word from the location appears in the course title
            loc_words = set(location_word.split())
            course_words = set(lower_course.split())
            if not (loc_words & course_words):
                return True
            # If the course DOES mention the location, keep the article
            break

    return False


# Named entity indicators — if a title contains these AND is not a pre-computed match,
# it's likely an organization/school rather than a relevant topic
NAMED_ENTITY_KEYWORDS = (
    "academy", "university", "college", "school", "institute",
    "corporation", "inc.", "ltd.", "company", "laboratories",
    "foundation", "association", "society", "organization",
)


def is_junk_page(title: str) -> bool:
    """Check if a Wikipedia page is unlikely to be a useful match target."""
    lower = title.lower().strip()

    # Glossary/list/outline/index pages
    if lower.startswith(JUNK_TITLE_PREFIXES):
        return True

    # Overly broad single-field articles
    if lower in BROAD_FIELD_ARTICLES:
        return True

    return False


def is_named_entity(title: str) -> bool:
    """Check if a title looks like a named entity (school, company, etc.)."""
    lower = title.lower()
    return any(kw in lower for kw in NAMED_ENTITY_KEYWORDS)


def significant_words(title: str) -> tuple[set, set]:
    """Extract meaningful words from a title.
    
    Returns (all_words, content_words) where content_words excludes
    generic category words like 'history' and 'introduction'.
    """
    # Remove parenthetical disambiguation
    clean = re.sub(r'\s*\(.*?\)\s*', '', title).strip()
    words = set(re.findall(r'[a-zA-Z][a-zA-Z0-9]+', clean))
    stopwords = {
        'the', 'a', 'an', 'of', 'in', 'for', 'to', 'and', 'or', 'by',
        'with', 'on', 'at', 'from', 'as', 'is', 'it', 'its', 'their',
        'this', 'that', 'are', 'was', 'were', 'be', 'been', 'has', 'have',
        'had', 'do', 'does', 'did', 'will', 'would', 'can', 'could',
        'may', 'might', 'shall', 'should', 'about', 'into', 'through',
        'during', 'before', 'after', 'above', 'below', 'between',
        'under', 'over', 'out', 'off', 'up', 'down', 'than', 'also',
        'very', 'just', 'not', 'no', 'but', 'so', 'if', 'all', 'each',
        'every', 'both', 'few', 'more', 'most', 'other', 'some', 'such',
        'only', 'own', 'same', 'too',
    }
    # Normalize to lowercase BEFORE removing stopwords (case-sensitive comparison)
    all_words = {w.lower() for w in words}
    all_words = all_words - stopwords
    # Content words exclude both generic category words AND acronyms
    # (acronyms are handled separately via expansion searches)
    acronyms = set(ACRONYM_MAP.keys())
    content_words = {w for w in all_words if w not in GENERIC_CATEGORY_WORDS and w not in acronyms}
    return all_words, content_words


# ══════════════════════════════════════════════════════════════════════════════
# COURSE RESOLUTION
# ══════════════════════════════════════════════════════════════════════════════

def _parse_frontmatter(filepath: str) -> dict:
    """Parse YAML frontmatter from a markdown file."""
    with open(filepath, encoding="utf-8") as f:
        content = f.read()
    if not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    frontmatter = {}
    for line in parts[1].strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                val = val[1:-1]
            frontmatter[key] = val
    return frontmatter


def resolve_course(input_str: str) -> dict:
    """Resolve course slug, URL, or ID to course metadata dict."""
    slug = input_str.rstrip("/")
    if slug.startswith("https://ocw.mit.edu/courses/"):
        path = urllib.parse.urlparse(slug).path.rstrip("/")
        if path.startswith("/courses/"):
            slug = path[len("/courses/"):]
    slug = slug.rstrip("/")

    wiki_path = os.path.join(WIKI_COURSES_DIR, f"{slug}.md")
    if os.path.exists(wiki_path):
        return _format_course_meta(_parse_frontmatter(wiki_path), slug, wiki_path)

    for fname in os.listdir(WIKI_COURSES_DIR):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(WIKI_COURSES_DIR, fname)
        with open(fpath, encoding="utf-8") as f:
            content = f.read()
        if f'course_id: "{input_str}"' in content or f"course_id: '{input_str}'" in content:
            return _format_course_meta(_parse_frontmatter(fpath), fname[:-3], fpath)

    print(colorize(f"  ❌ Course not found: {input_str}", Color.RED), file=sys.stderr)
    sys.exit(1)


def _format_course_meta(fm: dict, slug: str, path: str) -> dict:
    topics_raw = fm.get("topics", "")
    if topics_raw.startswith("["):
        topics = [t.strip().strip('"').strip("'") for t in topics_raw.strip("[]").split(",")]
    else:
        topics = [topics_raw] if topics_raw else []

    instructors_raw = fm.get("instructors", "")
    if instructors_raw.startswith("["):
        instructors = [t.strip().strip('"').strip("'") for t in instructors_raw.strip("[]").split(",")]
    else:
        instructors = [instructors_raw] if instructors_raw else []

    # Extract course description from the first paragraph of the page body
    desc = ""
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            body = parts[2].strip()
            for line in body.split("\n"):
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("[") and not line.startswith("{"):
                    desc = line[:250]
                    break
    except Exception:
        pass

    # Fallback: fetch description from OCW / MIT Learn API
    if not desc:
        try:
            api_id = fm.get("api_id", "")
            if api_id:
                api_url = f"https://api.learn.mit.edu/api/v1/courses/{api_id}/"
                req = urllib.request.Request(api_url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    api_data = json.loads(resp.read())
                api_desc = api_data.get("description", "") or ""
                if api_desc:
                    desc = api_desc[:250]
        except Exception:
            pass

    return {
        "course_id": fm.get("course_id", ""),
        "title": fm.get("title", ""),
        "url": fm.get("url", ""),
        "slug": slug,
        "topics": topics,
        "department": fm.get("department", ""),
        "instructors": instructors,
        "description": desc,
    }


# ══════════════════════════════════════════════════════════════════════════════
# MATCH CORPUS (pre-computed)
# ══════════════════════════════════════════════════════════════════════════════

def build_course_article_index() -> dict:
    """Build inverse index: course_id → list of article matches from live-matches.json."""
    if not os.path.exists(LIVE_MATCHES_PATH):
        return {}
    with open(LIVE_MATCHES_PATH) as f:
        data = json.load(f)
    index = {}
    for project, pdata in data.items():
        for article in pdata.get("articles", []):
            for match in article.get("ocw_matches", []):
                cid = match["course"]
                if cid not in index:
                    index[cid] = []
                index[cid].append({
                    "title": article["title"],
                    "wikiproject": project,
                    "templates": article.get("templates", []),
                    "quality": article.get("quality", "?"),
                    "views": article.get("views", 0),
                    "match_source": "pre-computed corpus",
                })
    return index


# ══════════════════════════════════════════════════════════════════════════════
# WIKIPEDIA API HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _api_call(params: dict) -> dict:
    """Make a Wikipedia API call with proper UA and error handling."""
    url = f"{WIKIPEDIA_API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception:
        return {}


def search_wikipedia(query: str, limit: int = 15) -> list[dict]:
    """Search Wikipedia by title/keywords. Returns deduplicated results."""
    data = _api_call({
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": limit,
        "srprop": "snippet|titlesnippet",
        "format": "json",
        "formatversion": "2",
    })
    results = []
    seen = set()
    for hit in data.get("query", {}).get("search", []):
        title = hit["title"]
        lower = title.lower()
        if lower not in seen:
            seen.add(lower)
            results.append({
                "title": title,
                "snippet": hit.get("snippet", ""),
                "match_source": "Wikipedia search",
            })
    return results


def batch_fetch_assessments(titles: list[str]) -> dict[str, tuple[str, int, str]]:
    """Batch-fetch quality and pageviews for a list of article titles.
    
    Uses prop=pageassessments for quality (1 API call) and
    prop=pageviews for monthly views (1 API call).
    
    Returns dict of title -> (best_quality_class, monthly_views, short_description)
    Quality classes ranked: FA > GA > B > C > Start > Stub > ?
    """
    if not titles:
        return {}

    QUALITY_RANK = {"FA": 6, "GA": 5, "B": 4, "C": 3, "Start": 2, "Stub": 1}
    result = {}

    # Fetch in batches of 50
    for i in range(0, len(titles), 50):
        batch = titles[i:i + 50]
        data = _api_call({
            "action": "query",
            "titles": "|".join(batch),
            "prop": "pageassessments|pageviews|description",
            "format": "json",
            "formatversion": "2",
        })
        for page in data.get("query", {}).get("pages", []):
            title = page.get("title", "")
            if not title:
                continue

            # Quality: pick the best class across all WikiProjects
            assessments = page.get("pageassessments", {})
            best_class = "?"
            best_rank = 0
            for wp, info in assessments.items():
                cls = info.get("class", "")
                rank = QUALITY_RANK.get(cls, 0)
                if rank > best_rank:
                    best_rank = rank
                    best_class = cls

            # Pageviews: sum last 30 days for a monthly estimate
            pvs = page.get("pageviews", {})
            monthly_views = 0
            if pvs:
                sorted_days = sorted(pvs.keys(), reverse=True)[:30]
                monthly_views = sum(pvs[d] for d in sorted_days if pvs[d] is not None)

            # Short description from Wikidata
            short_desc = page.get("description", "") or ""

            result[title] = (best_class, monthly_views, short_desc)

    return result


def check_page_type(titles: list[str]) -> dict[str, str]:
    """Batch-check page types: returns dict of title → 'normal'/'dab'/'glossary'/'list'.
    
    Uses categories and pageprops to detect disambiguation, glossary, and list pages.
    """
    if not titles:
        return {}

    # Batch in groups of 50
    result = {}
    for i in range(0, len(titles), 50):
        batch = titles[i:i + 50]
        data = _api_call({
            "action": "query",
            "titles": "|".join(batch),
            "prop": "pageprops|categories",
            "ppprop": "disambiguation",
            "cllimit": 10,
            "format": "json",
            "formatversion": "2",
        })
        for page in data.get("query", {}).get("pages", []):
            title = page.get("title", "")
            if not title:
                continue

            lower_title = title.lower()

            # Glossary pages
            if lower_title.startswith("glossary of"):
                result[title] = "glossary"
                continue

            # List pages
            if lower_title.startswith(("list of", "lists of")):
                result[title] = "list"
                continue

            # Disambiguation pages
            props = page.get("pageprops", {})
            if "disambiguation" in props or "disambiguation" in str(props):
                result[title] = "dab"
                continue

            # Check categories for disambiguation
            for cat in page.get("categories", []):
                cat_title = cat.get("title", "")
                if "disambiguation" in cat_title.lower():
                    result[title] = "dab"
                    break
                if "glossary" in cat_title.lower():
                    result[title] = "glossary"
                    break

            if title not in result:
                result[title] = "normal"

    return result


# ══════════════════════════════════════════════════════════════════════════════
# MATCH SCORING
# ══════════════════════════════════════════════════════════════════════════════

def compute_score(course: dict, article: dict) -> tuple[float, list[str]]:
    """Compute match score 0-100 for an article against a course.
    
    Scoring components:
      - Corpus match (40): pre-validated by the match pipeline
      - Title specificity (0-35): significant words from course title appearing in article title
      - Maintenance templates (0-15): community need signal
      - Pageviews (0-10): public interest signal (log-scaled)
    """
    score = 0.0
    reasons = []

    course_all, course_content = significant_words(course["title"])
    article_all, article_content = significant_words(article["title"])

    # 1. Pre-computed match bonus (25-40) — reduced if only generic overlap
    if article.get("match_source") == "pre-computed corpus":
        has_content_overlap = bool(course_content & article_content)
        if has_content_overlap:
            score += 40
            reasons.append("pre-computed match (+40)")
        else:
            score += 25
            reasons.append("pre-computed (generic) (+25)")

    # 2. Title specificity (0-35): uses CONTENT words only
    #    (skips generic words like 'history', 'introduction')
    overlap = course_content & article_content
    if overlap:
        specificity = len(overlap) / max(len(course_content), 1)
        specificity_score = min(specificity * 35, 35)
        score += specificity_score
        if specificity_score >= 20:
            reasons.append(f"strong title overlap: {', '.join(sorted(overlap))} (+{specificity_score:.0f})")
        elif specificity_score >= 5:
            reasons.append(f"partial title overlap (+{specificity_score:.0f})")
    else:
        # No content overlap — try expanded acronyms to bridge semantic gaps
        # e.g., "The History of MIT" doesn't overlap "History of Massachusetts Institute..."
        # but expanded "The History of Massachusetts Institute of Technology" does.
        expanded_title = course["title"].lower()
        for acronym, expansion in ACRONYM_MAP.items():
            expanded_title = re.sub(rf'\b{re.escape(acronym)}\b', expansion, expanded_title)
        if expanded_title != course["title"].lower():
            _exp_all, exp_content = significant_words(expanded_title)
            exp_overlap = exp_content & article_content
            if exp_overlap:
                specificity = len(exp_overlap) / max(len(exp_content), 1)
                # Cap at 20 (lower than direct title overlap) since it's an indirect match
                specificity_score = min(specificity * 20, 20)
                score += specificity_score
                reasons.append(f"expanded acronym overlap: {', '.join(sorted(exp_overlap))} (+{specificity_score:.0f})")
            else:
                generic_overlap = bool(course_all & article_all)
                if generic_overlap:
                    reasons.append("generic overlap only (weak specificity)")
                elif not article.get("match_source") == "pre-computed corpus":
                    reasons.append("no title overlap (weak match)")
        else:
            generic_overlap = bool(course_all & article_all)
            if generic_overlap:
                reasons.append("generic overlap only (weak specificity)")
            elif not article.get("match_source") == "pre-computed corpus":
                reasons.append("no title overlap (weak match)")

    # 3. Maintenance templates (0-15): community need signal
    templates = article.get("templates", [])
    template_boost = min(len(templates) * 5, 15)
    if template_boost > 0:
        score += template_boost
        reasons.append(f"{len(templates)} maintenance template(s) (+{template_boost})")

    # 4. Pageviews (0-10): public interest signal (log-scaled)
    views = article.get("views", 0)
    if views > 0:
        view_score = min(10 * (views / 100000) ** 0.3, 10)
        score += view_score

    return min(score, 100), reasons


# ══════════════════════════════════════════════════════════════════════════════
# MATCH PROVIDER INTERFACE
# ══════════════════════════════════════════════════════════════════════════════

from abc import ABC, abstractmethod


class MatchProvider(ABC):
    """Interface for a match-finding algorithm.
    
    Each provider implements find_candidates() which returns candidate
    articles from its matching strategy. The pipeline orchestrator handles
    deduplication, enrichment, filtering, scoring, and ranking.
    
    To add a new matching strategy:
      1. Subclass MatchProvider
      2. Implement name() and find_candidates()
      3. Register it in PROVIDER_REGISTRY or pass via --provider
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for this provider (used in --provider flag)."""

    @abstractmethod
    def find_candidates(self, course: dict) -> list[dict]:
        """Return candidate articles for this course.
        
        Each candidate dict must have at minimum:
          - title: str  (Wikipedia article title)
        
        Optional fields:
          - templates: list[str]  (maintenance templates like ['cn', 'refimprove'])
          - quality: str
          - views: int
          - wikiproject: str
          - match_source: str  (shown as "Source" in output)
        """


class CorpusProvider(MatchProvider):
    """Matches from pre-computed corpus (live-matches.json)."""

    @property
    def name(self) -> str:
        return "corpus"

    def find_candidates(self, course: dict) -> list[dict]:
        corpus = build_course_article_index()
        course_id = course["course_id"]
        if course_id not in corpus:
            return []
        candidates = []
        for entry in corpus[course_id]:
            if is_junk_page(entry["title"]):
                continue
            candidates.append({
                "title": entry["title"],
                "templates": entry.get("templates", []),
                "quality": entry.get("quality", "?"),
                "views": entry.get("views", 0),
                "match_source": "pre-computed corpus",
                "wikiproject": entry.get("wikiproject", ""),
            })
        return candidates


class WikipediaSearchProvider(MatchProvider):
    """Matches from Wikipedia search by course title."""

    @property
    def name(self) -> str:
        return "wikipedia"

    def find_candidates(self, course: dict) -> list[dict]:
        candidates = []
        for r in search_wikipedia(course["title"], limit=30):
            if is_junk_page(r["title"]):
                continue
            candidates.append({
                "title": r["title"],
                "templates": [],
                "quality": "?",
                "views": 0,
                "match_source": "Wikipedia search",
                "wikiproject": "",
            })
        return candidates


class AcronymExpansionProvider(MatchProvider):
    """Matches from expanded acronym search.
    
    Replaces known acronyms (MIT→Massachusetts Institute of Technology)
    in the course title and searches again.
    """

    @property
    def name(self) -> str:
        return "acronym"

    def find_candidates(self, course: dict) -> list[dict]:
        expanded = course["title"].lower()
        for acronym, expansion in ACRONYM_MAP.items():
            expanded = re.sub(rf'\b{re.escape(acronym)}\b', expansion, expanded)
        if expanded == course["title"].lower():
            return []
        candidates = []
        for r in search_wikipedia(expanded, limit=15):
            if is_junk_page(r["title"]):
                continue
            candidates.append({
                "title": r["title"],
                "templates": [],
                "quality": "?",
                "views": 0,
                "match_source": f"expanded: {expanded}",
                "wikiproject": "",
            })
        return candidates


class SimplifiedSearchProvider(MatchProvider):
    """Fallback search with simplified title (removes trailing qualifiers).
    
    Strips phrases like "for Healthcare" → searches "Machine Learning".
    Only activated when pipeline has < 5 candidates.
    """

    @property
    def name(self) -> str:
        return "simplified"

    def find_candidates(self, course: dict) -> list[dict]:
        simplified = re.sub(r'\s+(for|in|of|and|with|through)\s+.*$', '', course["title"], count=1)
        if simplified == course["title"]:
            return []
        candidates = []
        for r in search_wikipedia(simplified, limit=15):
            if is_junk_page(r["title"]):
                continue
            candidates.append({
                "title": r["title"],
                "templates": [],
                "quality": "?",
                "views": 0,
                "match_source": f"simplified: {simplified}",
                "wikiproject": "",
            })
        return candidates


# Registry — add new providers here
PROVIDER_REGISTRY: dict[str, type[MatchProvider]] = {
    "corpus": CorpusProvider,
    "wikipedia": WikipediaSearchProvider,
    "acronym": AcronymExpansionProvider,
    "simplified": SimplifiedSearchProvider,
}

DEFAULT_PROVIDERS = ["corpus", "wikipedia", "acronym", "simplified"]


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════════════════

def run_pipeline(course: dict, provider_names: list[str], top_n: int = 10) -> list[dict]:
    """Orchestrate providers: collect, dedup, enrich, filter, score, rank."""
    course_title = course["title"]

    # 1-2: Collect candidates from each provider, deduplicate
    seen = set()
    all_candidates = []
    for pname in provider_names:
        cls = PROVIDER_REGISTRY.get(pname)
        if not cls:
            continue
        for c in cls().find_candidates(course):
            lower = c["title"].lower()
            if lower not in seen:
                seen.add(lower)
                all_candidates.append(c)

    # Simplified is a fallback — only activate if sparse
    if "simplified" in provider_names and len(all_candidates) < 5:
        for c in SimplifiedSearchProvider().find_candidates(course):
            lower = c["title"].lower()
            if lower not in seen:
                seen.add(lower)
                all_candidates.append(c)

    if not all_candidates:
        return []

    # 3: Batch-fetch quality, views, descriptions
    fetch_titles = list({c["title"] for c in all_candidates})
    live_data = batch_fetch_assessments(fetch_titles) if fetch_titles else {}
    for c in all_candidates:
        if c["title"] in live_data:
            quality, views, short_desc = live_data[c["title"]]
            if quality != "?":
                c["quality"] = quality
            if views > 0:
                c["views"] = views
            if short_desc:
                c["description"] = short_desc

    # 4: Batch-check page types
    page_types = check_page_type([c["title"] for c in all_candidates])

    # 5-6: Filter and score
    course_all, _ = significant_words(course_title)
    scored = []
    for c in all_candidates:
        title = c["title"]
        ptype = page_types.get(title, "normal")
        if ptype in ("dab", "glossary", "list"):
            continue

        # Exclude geo-locale articles ("Mass media in Cambodia") unless the
        # course is specifically about that location
        if is_geo_limited_article(title, course["title"]):
            continue

        # Exclude named entities on weak (non-corpus) matches
        if not c.get("match_source", "").startswith("pre-computed"):
            article_all, _ = significant_words(title)
            if not (course_all & article_all):
                if is_named_entity(title):
                    continue
                if not c.get("templates"):
                    continue

        s, reasons = compute_score(course, c)
        c["score"] = round(s, 1)
        c["reasons"] = reasons
        c["_page_type"] = ptype
        scored.append(c)

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_n]


# ══════════════════════════════════════════════════════════════════════════════
# STATUS ENRICHMENT (show current state of each article)
# ══════════════════════════════════════════════════════════════════════════════

_REFIDEAS_ALIASES_LOOKUP = {
    "refideas", "refidea", "ri", "ref ideas", "suggested sources",
    "suggested refs", "source ideas", "potential sources", "possible sources",
    "refideas-nonotice", "refsuggestion",
}


def enrich_l1_status(matches: list[dict]):
    """Batch-check which article Talk pages already have {{refideas}}.
    
    Uses prop=templates to check for refideas template aliases.
    Adds 'l1_status' field to each match:
      - 'present' if refideas exists
      - 'absent' if not
    """
    if not matches:
        return

    # Batch-fetch templates for all Talk pages
    talk_titles = [f"Talk:{m['title'].replace(' ', '_')}" for m in matches]
    data = {}
    for i in range(0, len(talk_titles), 50):
        batch = talk_titles[i:i + 50]
        resp = _api_call({
            "action": "query",
            "titles": "|".join(batch),
            "prop": "templates",
            "tlnamespace": "10",
            "format": "json",
            "formatversion": "2",
        })
        for page in resp.get("query", {}).get("pages", []):
            t = page.get("title", "")
            if t:
                data[t] = page.get("templates", [])

    for m in matches:
        talk_key = f"Talk:{m['title'].replace(' ', '_')}"
        templates = data.get(talk_key, [])
        has_refideas = any(
            t.get("title", "").lower().replace("template:", "").strip()
            in _REFIDEAS_ALIASES_LOOKUP
            for t in templates
        )
        m["l1_status"] = "present" if has_refideas else "absent"


def enrich_l2_status(matches: list[dict]):
    """Check which articles have an == External links == section.
    
    Uses action=parse&prop=sections for each article (individually, not batchable).
    Adds 'l2_status' field to each match:
      - 'present' with count if section exists
      - 'absent' if not
    """
    for m in matches:
        title = m["title"]
        encoded = urllib.parse.quote(title.replace(" ", "_"), safe="")
        resp = _api_call({
            "action": "parse",
            "page": encoded,
            "prop": "sections",
            "format": "json",
            "formatversion": "2",
        })
        sections = resp.get("parse", {}).get("sections", [])
        ext_links_sections = [
            s for s in sections
            if s.get("line", "").lower() == "external links"
            and s.get("level") == "2"
        ]
        if ext_links_sections:
            # Count bullets in the section by fetching wikitext snippet
            # For now, just mark as present
            m["l2_status"] = "present"
        else:
            m["l2_status"] = "absent"


# ══════════════════════════════════════════════════════════════════════════════
# DISPLAY
# ══════════════════════════════════════════════════════════════════════════════

def format_quality(q: str) -> str:
    colors = {"FA": Color.GREEN, "GA": Color.GREEN, "B": Color.CYAN,
              "C": Color.YELLOW, "Start": Color.YELLOW, "Stub": Color.RED}
    return colorize(q, colors.get(q, Color.WHITE))


def display_matches(course: dict, matches: list[dict]):
    """Print ranked match list to stdout."""
    desc = course.get("description", "")
    print(f"\n  {colorize('Course:', Color.BOLD)} {course['course_id']} — {course['title']}")
    if desc:
        print(f"  {colorize('Description:', Color.BOLD)} {desc}")
    if course["topics"]:
        print(f"  {colorize('Topics:', Color.BOLD)} {', '.join(course['topics'][:6])}")
    print(f"  {colorize('URL:', Color.BOLD)} {course['url']}")
    print(f"\n  {colorize(f'Top {len(matches)} matches:', Color.BOLD)}")

    for i, m in enumerate(matches, 1):
        q = m.get("quality", "?")
        views = m.get("views", 0)
        templates = m.get("templates", [])
        article_desc = m.get("description", "")
        quality_str = format_quality(q)
        views_str = f"{views:,}" if views > 0 else "?"
        template_str = f", ⚡ {len(templates)} maintenance" if templates else ""
        title_clean = m['title'].replace('"', "'")
        slug_clean = course['slug'].replace('"', "'")
        l1_cmd = f'python3 scripts/apply-l1-refideas.py "{title_clean}" --course "{slug_clean}"'
        l2_cmd = f'python3 scripts/apply-l2-external-links.py "{title_clean}" --course "{slug_clean}"'
        score_str = f"{m['score']:.0f}/100"
        reasons_str = "; ".join(m['reasons'][:3])

        status_str = ""
        if "l1_status" in m:
            s = m["l1_status"]
            tag = "HAS" if s == "present" else "no"
            status_str = f" | {{{{refideas}}}}: {tag}"
        elif "l2_status" in m:
            s = m["l2_status"]
            tag = "HAS" if s == "present" else "no"
            status_str = f" | Ext links: {tag}"

        print(f"  {colorize(f'{i}.', Color.CYAN)} {colorize(m['title'], Color.BOLD)} [Quality: {quality_str} | Views: {views_str}{template_str}{status_str}]")
        if article_desc:
            print(f"     {article_desc[:120]}")
        print(f"     Score: {colorize(score_str, Color.GREEN)} — {reasons_str}")
        print(f"     Source: {m.get('match_source', '')}")
        print(f"     → L1: {colorize(l1_cmd, Color.YELLOW)}")
        print(f"     → L2: {colorize(l2_cmd, Color.YELLOW)}")


# ══════════════════════════════════════════════════════════════════════════════
# INTERACTIVE MODE
# ══════════════════════════════════════════════════════════════════════════════

def interactive_edit(course: dict, matches: list[dict], level: str, dry_run: bool):
    """Interactive: select match, preview diff, confirm, post."""
    if not matches:
        print(colorize("\n  No matches found.", Color.RED))
        return

    desc = course.get("description", "")

    while True:
        print(f"\n  {colorize('Course:', Color.BOLD)} {course['course_id']} — {course['title']}")
        if desc:
            print(f"  {colorize('Description:', Color.BOLD)} {desc}")
        print()
        print(f"  {colorize(f'Top {len(matches)} matches:', Color.BOLD)}")
        for i, m in enumerate(matches, 1):
            q = m.get("quality", "?")
            views = m.get("views", 0)
            v = f"{views:,}" if views > 0 else "?"
            article_desc = m.get("description", "")
            templates = m.get("templates", [])
            template_str = f", ⚡ {len(templates)} maintenance" if templates else ""
            score_str = f"{m['score']:.0f}/100"
            reasons_str = "; ".join(m['reasons'][:2])

            status_str = ""
            if "l1_status" in m:
                s = m["l1_status"]
                tag = "HAS" if s == "present" else "no"
                status_str = f" | {{{{refideas}}}}: {tag}"
            elif "l2_status" in m:
                s = m["l2_status"]
                tag = "HAS" if s == "present" else "no"
                status_str = f" | Ext links: {tag}"

            print(f"  {colorize(f'{i}.', Color.CYAN)} {colorize(m['title'], Color.BOLD)} [Quality: {q} | Views: {v}{template_str}{status_str}]")
            if article_desc:
                print(f"     {article_desc[:120]}")
            print(f"     Score: {colorize(score_str, Color.GREEN)} — {reasons_str}")
        print(f"  {colorize('  q.', Color.RED)} Quit")

        try:
            choice = input(f"\n  {colorize(f'Select match [1-{len(matches)}, q]: ', Color.BOLD)}").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if choice in ("q", "quit", ""):
            break

        try:
            idx = int(choice) - 1
            if idx < 0 or idx >= len(matches):
                continue
        except ValueError:
            continue

        article = matches[idx]["title"]
        print(f"\n  Selected: {colorize(article, Color.BOLD)}")

        if level == "L1":
            _do_l1_insert(course, article, dry_run)
        else:
            _do_l2_insert(course, article, dry_run)

        print()
        try:
            again = input(colorize("  Find another match for this course? [Y/n] ", Color.BOLD)).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if again in ("n", "no"):
            break


def _do_l1_insert(course: dict, article: str, dry_run: bool):
    """Insert L1 refideas on the Talk page."""
    result = _proto.l1_insert_refideas(
        article_title=article,
        course_id=course["course_id"],
        course_title=course["title"],
        course_url=course["url"],
        note="suggested via Wiki MIT ad-hoc match",
    )

    if result.get("skipped"):
        print(colorize(f"\n  ⏭  {result['detail']}", Color.YELLOW))
        return

    new_wikitext = result["wikitext"]
    action = result["action"]
    detail = result["detail"]
    summary = result["summary"]

    print(f"\n  Action: {colorize(action, Color.CYAN)}")
    print(f"  Detail: {detail}")
    print(f"  Summary: {colorize(summary, Color.GREEN)}")

    # Fetch original Talk page for diff
    encoded = urllib.parse.quote(f"Talk:{article.replace(' ', '_')}", safe="")
    api_url = f"{WIKIPEDIA_API}?action=parse&page={encoded}&prop=wikitext&format=json&formatversion=2"
    req = urllib.request.Request(api_url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            current_wt = data.get("parse", {}).get("wikitext", "")
    except Exception as e:
        print(f"  Error fetching Talk page: {e}")
        return

    if new_wikitext == current_wt:
        print(colorize("\n  ⚠️  No change.", Color.YELLOW))
        return

    diff = _add.side_by_side_diff(current_wt, new_wikitext, f"Talk:{article}")
    print(diff)

    if dry_run:
        print(colorize("\n  Dry run — no edit was made.", Color.YELLOW))
        return

    opener = _add.get_auth()
    if not opener:
        print(colorize("\n  ⚠️  No Wikipedia credentials.", Color.YELLOW))
        return

    try:
        response = input(colorize("  Post to Wikipedia Talk page? [y/N] ", Color.BOLD))
    except (EOFError, KeyboardInterrupt):
        print("\n  Cancelled.")
        return

    if response.lower() not in ("y", "yes"):
        print(colorize("  Cancelled.", Color.YELLOW))
        return

    print(colorize("  Posting...", Color.CYAN))
    # apply_edit prepends Talk: itself — pass bare article title
    edit_result = _add.apply_edit(article, new_wikitext, summary, opener)

    if "error" in edit_result:
        print(colorize(f"\n  ❌ Edit failed: {edit_result['error'].get('code', 'unknown')}", Color.RED))
    elif edit_result.get("edit", {}).get("result") == "Success":
        rev_id = edit_result["edit"].get("newrevid", "?")
        print(colorize(f"\n  ✅ Refideas added! Revision: {rev_id}", Color.GREEN))
    else:
        print(colorize(f"\n  ⚠️  Unexpected response.", Color.YELLOW))


def _extract_section(wikitext: str, section_name: str) -> str:
    """Extract a section's content from wikitext by heading name.
    
    Returns the section content (excluding the heading line) or empty string.
    """
    import re
    pattern = rf'^==\s*{re.escape(section_name)}\s*==\s*$'
    lines = wikitext.split("\n")
    in_section = False
    result = []
    for line in lines:
        if re.match(pattern, line, re.IGNORECASE):
            in_section = True
            continue
        if in_section:
            if re.match(r'^==\s*', line):
                break
            result.append(line)
    return "\n".join(result).strip()


def _do_l2_insert(course: dict, article: str, dry_run: bool):
    """Insert L2 external link on the article."""
    result = _proto.l2_insert_external_link(
        article_title=article,
        course_id=course["course_id"],
        course_title=course["title"],
        course_url=course["url"],
        description="",
    )

    if result.get("skipped"):
        print(colorize(f"\n  ⏭  {result['detail']}", Color.YELLOW))
        return

    new_wikitext = result["wikitext"]
    action = result["action"]
    detail = result["detail"]
    section = result.get("section", "")
    summary = result["summary"]

    print(f"\n  Action: {colorize(action, Color.CYAN)}")
    if section:
        print(f"  Section: {colorize(section, Color.CYAN)}")
    print(f"  Detail: {detail}")
    print(f"  Summary: {colorize(summary, Color.GREEN)}")

    encoded = urllib.parse.quote(article.replace(" ", "_"), safe="")
    api_url = f"{WIKIPEDIA_API}?action=parse&page={encoded}&prop=wikitext&format=json&formatversion=2"
    req = urllib.request.Request(api_url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            current_wt = data.get("parse", {}).get("wikitext", "")
    except Exception as e:
        print(f"  Error fetching article: {e}")
        return

    # Show existing External links section for context
    ext_section = _extract_section(current_wt, "External links")
    if ext_section:
        print(f"\n  {colorize('Current External links section:', Color.BOLD)}")
        for line in ext_section.strip().split("\n"):
            print(f"    {line}")
        print()
    else:
        # Try Further reading
        fr_section = _extract_section(current_wt, "Further reading")
        if fr_section:
            print(f"\n  {colorize('Current Further reading section:', Color.BOLD)}")
            for line in fr_section.strip().split("\n"):
                print(f"    {line}")
            print()
        else:
            print(f"\n  {colorize('No External links section exists — will create one.', Color.YELLOW)}")

    if new_wikitext == current_wt:
        print(colorize("\n  ⚠️  No change.", Color.YELLOW))
        return

    diff = _add.side_by_side_diff(current_wt, new_wikitext, article)
    print(diff)

    if dry_run:
        print(colorize("\n  Dry run — no edit was made.", Color.YELLOW))
        return

    opener = _add.get_auth()
    if not opener:
        print(colorize("\n  ⚠️  No Wikipedia credentials.", Color.YELLOW))
        return

    try:
        response = input(colorize("  Post to Wikipedia article? [y/N] ", Color.BOLD))
    except (EOFError, KeyboardInterrupt):
        print("\n  Cancelled.")
        return

    if response.lower() not in ("y", "yes"):
        print(colorize("  Cancelled.", Color.YELLOW))
        return

    # Import post_article_edit from apply-l2-external-links.py
    _l2_spec = importlib.util.spec_from_file_location(
        "apply_l2_cli",
        os.path.join(SCRIPTS_DIR, "apply-l2-external-links.py")
    )
    _l2_mod = importlib.util.module_from_spec(_l2_spec)
    _l2_spec.loader.exec_module(_l2_mod)

    print(colorize("  Posting...", Color.CYAN))
    edit_result = _l2_mod.post_article_edit(article, new_wikitext, summary, opener)

    if "error" in edit_result:
        print(colorize(f"\n  ❌ Edit failed: {edit_result['error'].get('code', 'unknown')}", Color.RED))
    elif edit_result.get("edit", {}).get("result") == "Success":
        rev_id = edit_result["edit"].get("newrevid", "?")
        print(colorize(f"\n  ✅ External link added! Revision: {rev_id}", Color.GREEN))
    else:
        print(colorize(f"\n  ⚠️  Unexpected response.", Color.YELLOW))


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    course_input = None
    mode = "L1"
    top_n = 10
    interactive = False
    dry_run = False
    provider_names = list(DEFAULT_PROVIDERS)

    i = 0
    while i < len(args):
        if args[i] == "--mode":
            i += 1
            if i < len(args):
                mode = args[i].upper()
                i += 1
        elif args[i] == "--top":
            i += 1
            if i < len(args):
                try:
                    top_n = int(args[i])
                    i += 1
                except ValueError:
                    i += 1
        elif args[i] == "--interactive":
            interactive = True
            i += 1
        elif args[i] == "--dry-run":
            dry_run = True
            i += 1
        elif args[i] == "--provider":
            i += 1
            if i < len(args):
                provider_names = [p.strip() for p in args[i].split(",")]
                i += 1
        elif not args[i].startswith("--"):
            course_input = args[i]
            i += 1
        else:
            i += 1

    if not course_input:
        print(colorize("  ❌ No course specified.", Color.RED), file=sys.stderr)
        print(__doc__)
        sys.exit(1)

    course = resolve_course(course_input)

    print(f"\n  {colorize('🔍 Finding matches...', Color.BOLD)}", file=sys.stderr)
    matches = run_pipeline(course, provider_names=provider_names, top_n=top_n)

    if not matches:
        print(colorize("\n  No strong matches found.", Color.YELLOW))
        print("  Try a different course or use --interactive to browse candidates.", file=sys.stderr)
        sys.exit(0)

    # Enrich with current article status (L1: refideas?, L2: External links?)
    if mode == "L1":
        enrich_l1_status(matches)
    else:
        enrich_l2_status(matches)

    if interactive:
        interactive_edit(course, matches, mode, dry_run)
    else:
        display_matches(course, matches)


if __name__ == "__main__":
    main()
