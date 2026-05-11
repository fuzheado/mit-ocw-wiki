#!/usr/bin/env python3
"""
Wikipedia cross-reference tool for OCW courses.

Two modes:
  --report --demo    Generate demo reports from hardcoded WikiProject data
  --report           Generate reports from live SQL (requires SSH tunnel + credentials)
  --apply            Apply approved matches to individual course pages

Usage:
    python3 scripts/crossref-wikipedia.py --report --demo
    python3 scripts/crossref-wikipedia.py --report --demo --top 50
    python3 scripts/crossref-wikipedia.py --report --project Chemistry
    python3 scripts/crossref-wikipedia.py --apply --project Chemistry
"""

import json, re, sys, os
from datetime import datetime
from pathlib import Path

WIKI_DIR = Path(__file__).resolve().parent.parent / "wiki"
REPORT_DIR = WIKI_DIR / "reports"
CROSSREF_DIR = WIKI_DIR / "crossrefs"

# Department code to name lookup
DEPT_NAMES = {
    "1": "Civil & Env. Eng.", "2": "Mechanical Eng.", "3": "Materials Sci.",
    "4": "Architecture", "5": "Chemistry", "6": "EECS",
    "7": "Biology", "8": "Physics", "9": "Brain & Cog. Sci.",
    "10": "Chemical Eng.", "11": "Urban Studies", "12": "Earth, Atmos. & Planetary Sci.",
    "14": "Economics", "15": "Management", "16": "Aero/Astro",
    "17": "Political Sci.", "18": "Mathematics", "20": "Biological Eng.",
    "21H": "History", "21L": "Literature", "21M": "Music",
    "22": "Nuclear Sci. & Eng.", "24": "Linguistics & Philosophy",
    "STS": "STS", "HST": "Health Sci. & Tech.", "CC": "Concourse",
    "ES": "Experimental Study", "CMS": "CMS", "WGS": "Women's Studies",
    "EC": "Edgerton Center", "MAS": "Media Arts & Sci.",
    "IDS": "Data, Systems & Society", "PE": "Athletics",
    "RES": "Supplemental Resources", "ESD": "Eng. Systems Division",
    "SP": "Special Programs",
}

# WikiProject name → OCW departments that align with it
WIKIPROJECT_DEPT_MAP = {
    "Environment": ["1", "2", "5", "7", "10", "11", "12", "22", "STS", "EC", "ESD"],
    "Chemistry": ["5", "3", "7", "10", "20"],
    "Physics": ["8", "6", "22"],
    "Biology": ["7", "20", "9", "HST"],
    "History": ["21H", "21L", "STS", "17"],
    "Nuclear technology": ["22", "STS"],
    "Energy": ["2", "22", "10", "5", "ESD", "IDS"],
    "Architecture": ["4", "11"],
    "Music": ["21M"],
    "Earth Science": ["12", "1", "ESD"],
    "Computer science": ["6", "18"],
    "Business": ["15", "14"],
    "Aviation": ["16"],
    "Aerospace": ["16"],
    "Anthropology": ["21A", "STS"],
    "Philosophy": ["24", "STS"],
    "Education": ["CC", "ES"],
    "Media": ["CMS-W", "MAS", "21A"],
    "Gender studies": ["WGS", "21A", "STS", "21H", "21L"],
    "Linguistics": ["21G", "24"],
    "Engineering": ["2", "3", "6", "10", "16", "22", "ES", "IDS"],
    "Mathematics": ["18"],
    "Economics": ["14", "EC", "15"],
    "Political science": ["17", "STS", "EC"],
    "Medicine": ["HST", "9", "20", "7"],
}
# Source: Wikipedia WikiProject Environment Popular pages (April 2026)
# OCW course data from hybrid scans

# Wikipedia WikiProject metadata for clickable headers and hover descriptions
WIKIPROJECT_INFO = {
    "Environment": {"url": "https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Environment", "desc": "Ecology, climate, conservation, and environmental science"},
    "Chemistry": {"url": "https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Chemistry", "desc": "Chemical compounds, reactions, periodic table, and chemical principles"},
    "Physics": {"url": "https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Physics", "desc": "Fundamental physics, mechanics, quantum theory, and physical laws"},
    "Biology": {"url": "https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Biology", "desc": "Living organisms, genetics, evolution, and biological systems"},
    "History": {"url": "https://en.wikipedia.org/wiki/Wikipedia:WikiProject_History", "desc": "World history, historical events, periods, and historiography"},
    "Nuclear technology": {"url": "https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Nuclear_technology", "desc": "Nuclear energy, weapons, safety, and radioactive materials"},
    "Energy": {"url": "https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Energy", "desc": "Energy production, renewable sources, power generation, and policy"},
    "Architecture": {"url": "https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Architecture", "desc": "Buildings, structures, architectural styles, and urban design"},
    "Music": {"url": "https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Music", "desc": "Musical genres, artists, compositions, and music theory"},
    "Earth Science": {"url": "https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Earth_science", "desc": "Geology, oceanography, meteorology, and geophysics"},
    "Computer science": {"url": "https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Computer_science", "desc": "Algorithms, programming, computing theory, and software"},
    "Business": {"url": "https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Business", "desc": "Management, marketing, entrepreneurship, and business topics"},
    "Aviation": {"url": "https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Aviation", "desc": "Aircraft, airlines, aviation history, and aerospace engineering"},
    "Aerospace": {"url": "https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Aerospace", "desc": "Spacecraft, satellites, rocketry, and space exploration"},
    "Anthropology": {"url": "https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Anthropology", "desc": "Human cultures, archaeology, linguistics, and social evolution"},
    "Philosophy": {"url": "https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Philosophy", "desc": "Ethics, metaphysics, epistemology, logic, and philosophical traditions"},
    "Education": {"url": "https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Education", "desc": "Education methods, institutions, pedagogy, and learning theory"},
    "Media": {"url": "https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Media", "desc": "Mass media, journalism, broadcasting, and digital media studies"},
    "Gender studies": {"url": "https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Gender_studies", "desc": "Gender identity, feminism, masculinity, and queer theory"},
    "Linguistics": {"url": "https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Linguistics", "desc": "Language structure, syntax, phonology, and language acquisition"},
    "Engineering": {"url": "https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Engineering", "desc": "Engineering disciplines, methods, and technologies across all fields"},
    "Mathematics": {"url": "https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Mathematics", "desc": "Algebra, geometry, calculus, number theory, and analysis"},
    "Economics": {"url": "https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Economics", "desc": "Economic theory, markets, finance, and policy analysis"},
    "Political science": {"url": "https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Political_science", "desc": "Government, policy, international relations, and political theory"},
    "Medicine": {"url": "https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Medicine", "desc": "Diseases, treatments, anatomy, pharmacology, and clinical practice"},
}

# OCW department → MIT school for row grouping
DEPT_SCHOOL = {
    "1": "Engineering", "2": "Engineering", "3": "Engineering",
    "6": "Engineering", "10": "Engineering", "16": "Engineering",
    "20": "Engineering", "22": "Engineering",
    "ES": "Engineering", "ESD": "Engineering", "IDS": "Engineering",
    "5": "Science", "7": "Science", "8": "Science", "9": "Science",
    "12": "Science", "18": "Science",
    "14": "Humanities, Arts & Social Sciences", "15": "Humanities, Arts & Social Sciences",
    "17": "Humanities, Arts & Social Sciences", "21A": "Humanities, Arts & Social Sciences",
    "21G": "Humanities, Arts & Social Sciences", "21H": "Humanities, Arts & Social Sciences",
    "21L": "Humanities, Arts & Social Sciences", "21M": "Humanities, Arts & Social Sciences",
    "24": "Humanities, Arts & Social Sciences",
    "CMS": "Humanities, Arts & Social Sciences", "CMS-W": "Humanities, Arts & Social Sciences",
    "STS": "Humanities, Arts & Social Sciences", "WGS": "Humanities, Arts & Social Sciences",
    "4": "Architecture & Planning", "11": "Architecture & Planning",
    "MAS": "Architecture & Planning",
    "HST": "Health Sciences & Technology",
    "CC": "Other", "EC": "Other", "PE": "Other", "SP": "Other",
}

DEMO_DATA = {
    "Environment": {
        "articles": [
            {
                "title": "Earth Day",
                "views": 291552,
                "quality": "C",
                "importance": "High",
                "templates": ["More citations needed"],
                "ocw_matches": [
                    {"course": "11.165", "title": "Infrastructure and Energy Technology Challenges", "lecture": "Energy policy discussions", "assets": "reading-list"},
                    {"course": "11.941", "title": "Urban Climate Adaptation", "lecture": "Climate adaptation policy", "assets": "lecture-notes"},
                ]
            },
            {
                "title": "Nuclear weapon",
                "views": 95651,
                "quality": "C",
                "importance": "High",
                "templates": ["Citation needed", "More citations needed"],
                "ocw_matches": [
                    {"course": "22.01", "title": "Introduction to Nuclear Engineering", "lecture": "Nuclear weapons overview", "assets": "video+transcript"},
                    {"course": "22.033", "title": "Nuclear Systems Design Project", "lecture": "Nuclear fuel cycle", "assets": "lecture-notes"},
                    {"course": "STS.038", "title": "Energy and Environment in American History", "lecture": "Manhattan Project history", "assets": "reading-list"},
                ]
            },
            {
                "title": "Petroleum",
                "views": 75490,
                "quality": "C",
                "importance": "High",
                "templates": ["Refimprove"],
                "ocw_matches": [
                    {"course": "22.081J", "title": "Introduction to Sustainable Energy", "lecture": "Fossil fuels", "assets": "video+transcript"},
                    {"course": "2.61", "title": "Internal Combustion Engines", "lecture": "Petroleum fuels", "assets": "lecture-notes"},
                    {"course": "12.340", "title": "Global Warming Science", "lecture": "Carbon cycle", "assets": "video+transcript"},
                ]
            },
            {
                "title": "El Niño–Southern Oscillation",
                "views": 74966,
                "quality": "C",
                "importance": "High",
                "templates": ["Missing information"],
                "ocw_matches": [
                    {"course": "12.800", "title": "Fluid Dynamics of the Atmosphere and Ocean", "lecture": "ENSO dynamics", "assets": "lecture-notes"},
                    {"course": "12.307", "title": "Weather and Climate Laboratory", "lecture": "Climate oscillations", "assets": "video+transcript"},
                ]
            },
            {
                "title": "Deepwater Horizon oil spill",
                "views": 65507,
                "quality": "C",
                "importance": "High",
                "templates": ["Missing information"],
                "ocw_matches": [
                    {"course": "1.74", "title": "Land, Water, Food, and Climate", "lecture": "Environmental disasters", "assets": "lecture-notes"},
                    {"course": "1.85", "title": "Water and Wastewater Treatment Engineering", "lecture": "Water contamination", "assets": "lecture-notes"},
                ]
            },
            {
                "title": "Carbon dioxide",
                "views": 37300,
                "quality": "C",
                "importance": "High",
                "templates": ["Refimprove"],
                "ocw_matches": [
                    {"course": "5.111SC", "title": "Principles of Chemical Science", "lecture": "Greenhouse gases", "assets": "video+transcript"},
                    {"course": "12.340", "title": "Global Warming Science", "lecture": "CO2 and climate", "assets": "video+transcript"},
                    {"course": "1.74", "title": "Land, Water, Food, and Climate", "lecture": "Carbon cycle", "assets": "lecture-notes"},
                ]
            },
            {
                "title": "Breeder reactor",
                "views": 36482,
                "quality": "C",
                "importance": "Low",
                "templates": ["Refimprove"],
                "ocw_matches": [
                    {"course": "22.01", "title": "Introduction to Nuclear Engineering", "lecture": "Reactor types", "assets": "video+transcript"},
                    {"course": "22.033", "title": "Nuclear Systems Design Project", "lecture": "Advanced reactors", "assets": "lecture-notes"},
                ]
            },
            {
                "title": "Chernobyl exclusion zone",
                "views": 48144,
                "quality": "C",
                "importance": "High",
                "templates": ["Citation needed"],
                "ocw_matches": [
                    {"course": "22.091", "title": "Nuclear Reactor Safety", "lecture": "Chernobyl case study", "assets": "video+transcript"},
                    {"course": "22.033", "title": "Nuclear Systems Design Project", "lecture": "Containment", "assets": "lecture-notes"},
                ]
            },
            {
                "title": "Extinction",
                "views": 39794,
                "quality": "C",
                "importance": "High",
                "templates": ["Refimprove"],
                "ocw_matches": [
                    {"course": "1.018J", "title": "Ecology I: The Earth System", "lecture": "Biodiversity", "assets": "lecture-notes"},
                    {"course": "7.016", "title": "Introductory Biology", "lecture": "Evolution", "assets": "video+transcript"},
                ]
            },
            {
                "title": "Prisoner's dilemma",
                "views": 39225,
                "quality": "C",
                "importance": "High",
                "templates": ["Refimprove"],
                "ocw_matches": [
                    {"course": "14.12", "title": "Economic Applications of Game Theory", "lecture": "Prisoner's dilemma", "assets": "video+transcript"},
                ]
            },
            {
                "title": "Atmosphere of Earth",
                "views": 58418,
                "quality": "B",
                "importance": "High",
                "templates": [],
                "ocw_matches": [
                    {"course": "12.810", "title": "Dynamics of the Atmosphere", "lecture": "Atmospheric structure", "assets": "video+transcript"},
                ]
            },
            {
                "title": "Climate change",
                "views": 70965,
                "quality": "FA",
                "importance": "Top",
                "templates": [],
                "ocw_matches": []
            },
        ],
        "total_views": 21793841,
        "period": "2026-04-01 to 2026-04-30"
    },
    "Chemistry": {
        "articles": [
            {
                "title": "Chemical bond",
                "views": 85000,
                "quality": "C",
                "importance": "High",
                "templates": ["Refimprove"],
                "ocw_matches": [
                    {"course": "5.111SC", "title": "Principles of Chemical Science", "lecture": "Chemical bonding overview", "assets": "video+transcript"},
                    {"course": "5.112", "title": "Principles of Chemical Science", "lecture": "Ionic and covalent bonds", "assets": "lecture-notes"},
                ]
            },
            {
                "title": "Electron configuration",
                "views": 42000,
                "quality": "Start",
                "importance": "High",
                "templates": ["Missing information"],
                "ocw_matches": [
                    {"course": "5.111SC", "title": "Principles of Chemical Science", "lecture": "Electron configurations", "assets": "video+transcript"},
                ]
            },
            {
                "title": "VSEPR theory",
                "views": 32000,
                "quality": "C",
                "importance": "Mid",
                "templates": ["Image requested"],
                "ocw_matches": [
                    {"course": "5.111SC", "title": "Principles of Chemical Science", "lecture": "Molecular shapes", "assets": "video+transcript"},
                ]
            },
        ],
        "total_views": 2100000,
        "period": "2026-04-01 to 2026-04-30"
    },
    "Biology": {
        "articles": [
            {
                "title": "Evolution",
                "views": 120000,
                "quality": "GA",
                "importance": "Top",
                "templates": [],
                "ocw_matches": []
            },
            {
                "title": "Cell (biology)",
                "views": 95000,
                "quality": "C",
                "importance": "High",
                "templates": ["Refimprove"],
                "ocw_matches": [
                    {"course": "7.016", "title": "Introductory Biology", "lecture": "Cell structure", "assets": "video+transcript"},
                    {"course": "7.012", "title": "Introductory Biology", "lecture": "Cell biology", "assets": "lecture-notes"},
                ]
            },
            {
                "title": "DNA replication",
                "views": 55000,
                "quality": "B",
                "importance": "High",
                "templates": ["Refimprove"],
                "ocw_matches": [
                    {"course": "7.016", "title": "Introductory Biology", "lecture": "DNA replication", "assets": "video+transcript"},
                ]
            },
        ],
        "total_views": 8700000,
        "period": "2026-04-01 to 2026-04-30"
    },
    "Computer science": {
        "articles": [
            {
                "title": "Algorithm",
                "views": 180000,
                "quality": "C",
                "importance": "Top",
                "templates": ["Refimprove"],
                "ocw_matches": [
                    {"course": "6.006", "title": "Introduction to Algorithms", "lecture": "Algorithm analysis", "assets": "video+transcript"},
                    {"course": "6.046J", "title": "Introduction to Algorithms", "lecture": "Advanced algorithms", "assets": "video+transcript"},
                ]
            },
            {
                "title": "Machine learning",
                "views": 250000,
                "quality": "C",
                "importance": "Top",
                "templates": ["Citation needed"],
                "ocw_matches": [
                    {"course": "6.867", "title": "Machine Learning", "lecture": "Supervised learning", "assets": "video+transcript"},
                    {"course": "6.7960", "title": "Deep Learning", "lecture": "Neural networks", "assets": "video+transcript"},
                ]
            },
            {
                "title": "Artificial neural network",
                "views": 95000,
                "quality": "B",
                "importance": "High",
                "templates": ["Refimprove"],
                "ocw_matches": [
                    {"course": "6.7960", "title": "Deep Learning", "lecture": "Neural network architectures", "assets": "video+transcript"},
                ]
            },
            {
                "title": "Computational complexity theory",
                "views": 35000,
                "quality": "C",
                "importance": "High",
                "templates": ["Citation needed"],
                "ocw_matches": [
                    {"course": "6.045J", "title": "Automata, Computability, and Complexity", "lecture": "Complexity classes", "assets": "video+transcript"},
                ]
            },
        ],
        "total_views": 12000000,
        "period": "2026-04-01 to 2026-04-30"
    },
    "Business": {
        "articles": [
            {
                "title": "Entrepreneurship",
                "views": 85000,
                "quality": "C",
                "importance": "High",
                "templates": ["Refimprove"],
                "ocw_matches": [
                    {"course": "15.390", "title": "New Enterprises", "lecture": "Entrepreneurship fundamentals", "assets": "video+transcript"},
                ]
            },
            {
                "title": "Supply chain",
                "views": 45000,
                "quality": "C",
                "importance": "High",
                "templates": ["Missing information"],
                "ocw_matches": [
                    {"course": "15.762J", "title": "Supply Chain Planning", "lecture": "Logistics and planning", "assets": "video+transcript"},
                    {"course": "ESD.273J", "title": "Logistics and Supply Chain Management", "lecture": "Supply chain design", "assets": "lecture-notes"},
                ]
            },
            {
                "title": "Finance",
                "views": 200000,
                "quality": "C",
                "importance": "Top",
                "templates": ["Citation needed"],
                "ocw_matches": [
                    {"course": "15.401", "title": "Finance Theory I", "lecture": "Corporate finance", "assets": "video+transcript"},
                    {"course": "15.450", "title": "Analytics of Finance", "lecture": "Financial analytics", "assets": "lecture-notes"},
                ]
            },
            {
                "title": "Marketing",
                "views": 72000,
                "quality": "C",
                "importance": "High",
                "templates": ["Refimprove"],
                "ocw_matches": [
                    {"course": "15.810", "title": "Marketing Management", "lecture": "Marketing strategy", "assets": "video+transcript"},
                ]
            },
        ],
        "total_views": 9500000,
        "period": "2026-04-01 to 2026-04-30"
    },
    "Aviation": {
        "articles": [
            {
                "title": "Aerodynamics",
                "views": 55000,
                "quality": "C",
                "importance": "High",
                "templates": ["More citations needed"],
                "ocw_matches": [
                    {"course": "16.121", "title": "Analytical Subsonic Aerodynamics", "lecture": "Lift and drag", "assets": "video+transcript"},
                    {"course": "16.885J", "title": "Aircraft Systems Engineering", "lecture": "Aerodynamics overview", "assets": "lecture-notes"},
                ]
            },
            {
                "title": "Air traffic control",
                "views": 42000,
                "quality": "C",
                "importance": "High",
                "templates": ["Refimprove"],
                "ocw_matches": [
                    {"course": "16.682", "title": "Technology in Transportation", "lecture": "Air traffic management", "assets": "video+transcript"},
                ]
            },
            {
                "title": "3D printing",
                "views": 310000,
                "quality": "C",
                "importance": "Mid",
                "templates": ["Citation needed"],
                "ocw_matches": [
                    {"course": "16.810", "title": "Engineering Design and Rapid Prototyping", "lecture": "Rapid prototyping techniques", "assets": "video+transcript"},
                ]
            },
        ],
        "total_views": 407000,
        "period": "2026-04-01 to 2026-04-30"
    },
    "Mathematics": {
        "articles": [
            {
                "title": "Probability",
                "views": 180000,
                "quality": "C",
                "importance": "Top",
                "templates": ["More citations needed"],
                "ocw_matches": [
                    {"course": "18.600", "title": "Probability and Random Variables", "lecture": "Probability axioms", "assets": "video+transcript"},
                ]
            },
            {
                "title": "Number theory",
                "views": 95000,
                "quality": "C",
                "importance": "High",
                "templates": ["Citation needed"],
                "ocw_matches": [
                    {"course": "18.785", "title": "Number Theory I", "lecture": "Modular forms", "assets": "video+transcript"},
                ]
            },
            {
                "title": "Statistics",
                "views": 220000,
                "quality": "B",
                "importance": "Top",
                "templates": ["More citations needed"],
                "ocw_matches": [
                    {"course": "18.465", "title": "Topics in Statistics: Nonparametrics and Robustness", "lecture": "Nonparametric methods", "assets": "lecture-notes"},
                ]
            },
        ],
        "total_views": 495000,
        "period": "2026-04-01 to 2026-04-30"
    },
    "Philosophy": {
        "articles": [
            {
                "title": "Ethics",
                "views": 290000,
                "quality": "B",
                "importance": "Top",
                "templates": ["More citations needed"],
                "ocw_matches": [
                    {"course": "24.191", "title": "Ethics in Your Life: Being, Thinking, Doing (or Not?)", "lecture": "Moral reasoning", "assets": "video+transcript"},
                    {"course": "24.00", "title": "Problems of Philosophy", "lecture": "Ethical theories", "assets": "lecture-notes"},
                ]
            },
            {
                "title": "Feminist theory",
                "views": 68000,
                "quality": "C",
                "importance": "High",
                "templates": ["Citation needed"],
                "ocw_matches": [
                    {"course": "WGS.301J", "title": "Feminist Thought", "lecture": "Feminist epistemologies", "assets": "reading-list"},
                ]
            },
            {
                "title": "Linguistics",
                "views": 110000,
                "quality": "C",
                "importance": "High",
                "templates": ["Refimprove"],
                "ocw_matches": [
                    {"course": "24.900", "title": "Introduction to Linguistics", "lecture": "Language universals", "assets": "video+transcript"},
                ]
            },
        ],
        "total_views": 468000,
        "period": "2026-04-01 to 2026-04-30"
    },
    "Medicine": {
        "articles": [
            {
                "title": "Neurophysiology",
                "views": 48000,
                "quality": "C",
                "importance": "High",
                "templates": ["More citations needed"],
                "ocw_matches": [
                    {"course": "9.16", "title": "Cellular Neurophysiology", "lecture": "Ion channels", "assets": "video+transcript"},
                ]
            },
            {
                "title": "Hearing",
                "views": 105000,
                "quality": "C",
                "importance": "Top",
                "templates": ["Citation needed"],
                "ocw_matches": [
                    {"course": "HST.723J", "title": "Neural Coding and Perception of Sound", "lecture": "Auditory pathways", "assets": "video+transcript"},
                ]
            },
            {
                "title": "Perception",
                "views": 135000,
                "quality": "B",
                "importance": "High",
                "templates": ["More citations needed"],
                "ocw_matches": [
                    {"course": "9.35", "title": "Sensation And Perception", "lecture": "Visual perception", "assets": "video+transcript"},
                ]
            },
            {
                "title": "Neuroethics",
                "views": 22000,
                "quality": "Start",
                "importance": "Mid",
                "templates": ["Expand section"],
                "ocw_matches": [
                    {"course": "9.46", "title": "Neuroscience of Morality", "lecture": "Moral cognition", "assets": "lecture-notes"},
                ]
            },
        ],
        "total_views": 310000,
        "period": "2026-04-01 to 2026-04-30"
    }
}


def timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def course_url(course_id: str) -> str:
    """Look up the OCW URL for a course by searching wiki pages for its course_id."""
    courses_dir = WIKI_DIR / "courses"
    if not courses_dir.exists():
        return ""
    for f in courses_dir.iterdir():
        if not f.name.endswith(".md"):
            continue
        content = f.read_text()
        if re.search(rf'^course_id:\s*"{re.escape(course_id)}"', content, re.M):
            m = re.search(r'^url:\s*"(.+?)"', content, re.M)
            if m:
                return m.group(1)
    return ""


def score_match(article: dict, match: dict) -> int:
    """Score a candidate match 0-100."""
    score = 0
    # Quality gap: C or below = good target
    quality_scores = {"Stub": 30, "Start": 25, "C": 20, "B": 10, "GA": 5, "FA": 0}
    score += quality_scores.get(article["quality"], 0)
    # Importance
    importance_scores = {"Top": 25, "High": 20, "Mid": 10, "Low": 5}
    score += importance_scores.get(article["importance"], 0)
    # Templates present
    if article.get("templates"):
        score += min(len(article["templates"]) * 10, 25)
    # Asset richness
    asset_scores = {"video+transcript": 20, "lecture-notes": 10, "reading-list": 5}
    score += asset_scores.get(match.get("assets", ""), 5)
    # Views (log-scaled)
    views = article.get("views", 0)
    if views > 100000:
        score += 10
    elif views > 50000:
        score += 7
    elif views > 20000:
        score += 4
    else:
        score += 1
    return min(score, 100)


def generate_summary(top_n=10):
    """Layer 1: Executive summary report."""
    total_courses = set()
    total_matches = 0
    high_priority = 0
    all_matches = []

    for project, data in DEMO_DATA.items():
        for article in data["articles"]:
            if not article["ocw_matches"]:
                continue
            total_matches += len(article["ocw_matches"])
            for match in article["ocw_matches"]:
                total_courses.add(match["course"])
                s = score_match(article, match)
                if s >= 60:
                    high_priority += 1
                all_matches.append((s, project, article, match))

    all_matches.sort(key=lambda x: -x[0])

    lines = []
    lines.append("> Generated by `scripts/crossref-wikipedia.py --report --demo`")
    lines.append("")
    lines.append("# Wikipedia CrossRef: Summary Report")
    lines.append("")
    lines.append(f"Demo based on WikiProject Environment Popular pages data (April 2026).")
    lines.append(f"**{total_matches} candidate matches** across **{len(total_courses)} OCW courses**.")
    lines.append("")
    lines.append(f"## Top {min(top_n, len(all_matches))} highest-impact matches")
    lines.append("")
    lines.append("| # | OCW Course | Wikipedia Article | Views | Quality | Importance | Templates | Score")
    lines.append("|---|------------|-------------------|-------|---------|------------|-----------|-------")
    for i, (s, proj, article, match) in enumerate(all_matches[:top_n]):
        tmpl = ", ".join(article.get("templates", [])) or "—"
        lines.append(f"| {i+1} | **{match['course']}** | [[en:{article['title'].replace(' ', '_')}]] | {article['views']:,} | {article['quality']} | {article['importance']} | {tmpl} | **{s}**")

    lines.append("")
    lines.append("## By OCW Department")
    lines.append("")
    dept_map = {}
    for s, proj, article, match in all_matches:
        dept = match["course"].split(".")[0]
        dept_map.setdefault(dept, {"matches": 0, "high": 0})
        dept_map[dept]["matches"] += 1
        if s >= 60:
            dept_map[dept]["high"] += 1

    lines.append("| Department | Matches | High-priority |")
    lines.append("|------------|---------|---------------|")
    for dept in sorted(dept_map.keys()):
        name = DEPT_NAMES.get(dept, dept)
        lines.append(f"| **{dept}** {name} | {dept_map[dept]['matches']} | {dept_map[dept]['high']} |")

    lines.append("")
    lines.append("## By Quality Class")
    lines.append("")
    q_counts = {}
    for s, proj, article, match in all_matches:
        q = article["quality"]
        q_counts[q] = q_counts.get(q, 0) + 1
    lines.append("| Quality | Matches |")
    lines.append("|---------|---------|")
    for q in ["Stub", "Start", "C", "B", "GA", "FA"]:
        if q in q_counts:
            lines.append(f"| {q} | {q_counts[q]} |")

    lines.append("")
    lines.append("---")
    lines.append(f"_Report generated {timestamp()}._")

    return "\n".join(lines)


def generate_project_summary(project: str):
    """Layer 2: Detail page for a single WikiProject."""
    data = DEMO_DATA.get(project)
    if not data:
        return "# No data"

    # Separate by priority quadrant
    primary = []   # High importance, C or below
    secondary = [] # Low importance, C or below
    done = []      # B/GA/FA
    templates_by_type = {}

    for article in data["articles"]:
        for tmpl in article.get("templates", []):
            templates_by_type.setdefault(tmpl, []).append(article)
        if article["quality"] in ("Stub", "Start", "C") and article["importance"] in ("Top", "High"):
            primary.append(article)
        elif article["quality"] in ("Stub", "Start", "C"):
            secondary.append(article)
        else:
            done.append(article)

    lines = []
    lines.append(f"> Generated by `scripts/crossref-wikipedia.py --report --demo`")
    lines.append("")
    lines.append(f"# WikiProject: {project}")
    lines.append("")
    lines.append(f"Period: {data['period']}  ·  Total views: {data['total_views']:,}")
    lines.append(f"Articles in scope: {len(data['articles'])}")
    lines.append("")

    # Primary targets
    lines.append("## Primary targets (High importance, needs work)")
    lines.append("")
    lines.append("| Article | Views | Quality | Templates | OCW match | Score")
    lines.append("|---------|-------|---------|-----------|-----------|-------")
    for article in primary:
        tmpl = ", ".join(article.get("templates", [])) or "—"
        if article["ocw_matches"]:
            for match in article["ocw_matches"]:
                s = score_match(article, match)
                lines.append(f"| [[en:{article['title'].replace(' ', '_')}]] | {article['views']:,} | {article['quality']} | {tmpl} | {match['course']} ({match['lecture']}) | **{s}**")
            else:
                lines.append(f"| [[en:{article['title'].replace(' ', '_')}]] | {article['views']:,} | {article['quality']} | {tmpl} | — | —")

    # Templates breakdown
    lines.append("")
    lines.append("## Maintenance templates found")
    lines.append("")
    lines.append("| Template | Articles |")
    lines.append("|----------|----------|")
    for tmpl, articles in sorted(templates_by_type.items()):
        names = ", ".join(a["title"] for a in articles[:5])
        if len(articles) > 5:
            names += f" … and {len(articles)-5} more"
        lines.append(f"| `{{{{{tmpl}}}}}` | {names}")

    lines.append("")
    lines.append("## Score distribution")
    lines.append("")
    all_scores = []
    for article in data["articles"]:
        for match in article.get("ocw_matches", []):
            all_scores.append(score_match(article, match))
    if all_scores:
        buckets = {"0-19": 0, "20-39": 0, "40-59": 0, "60-79": 0, "80-100": 0}
        for s in all_scores:
            if s < 20: buckets["0-19"] += 1
            elif s < 40: buckets["20-39"] += 1
            elif s < 60: buckets["40-59"] += 1
            elif s < 80: buckets["60-79"] += 1
            else: buckets["80-100"] += 1
        
        max_count = max(buckets.values()) or 1
        lines.append("| Score | Count | Distribution |")
        lines.append("|-------|-------|--------------|")
        for bucket, count in buckets.items():
            bar = "█" * int(count / max_count * 30) if max_count else ""
            lines.append(f"| {bucket} | {count} | {bar}")

    lines.append("")
    lines.append("---")
    lines.append(f"_Generated {timestamp()} from demo data._")

    return "\n".join(lines)


def generate_heatmap():
    """Generate an HTML heatmap with grouped rows, sortable columns, sidebar panel, rich tooltips, and search."""
    projects = list(DEMO_DATA.keys())
    depts = sorted(set(
        match["course"].split(".")[0]
        for data in DEMO_DATA.values()
        for article in data["articles"]
        for match in article.get("ocw_matches", [])
    ))

    matrix = {}
    details = {}
    for dept in depts:
        matrix[dept] = {}
        for proj in projects:
            matrix[dept][proj] = 0
    for proj, data in DEMO_DATA.items():
        for article in data["articles"]:
            for match in article.get("ocw_matches", []):
                dept = match["course"].split(".")[0]
                matrix.setdefault(dept, {})
                matrix[dept].setdefault(proj, 0)
                matrix[dept][proj] += 1
                key = f"{dept}_{proj}"
                details.setdefault(key, [])
                details[key].append({
                    "course": match["course"],
                    "title": match["title"],
                    "lecture": match["lecture"],
                    "assets": match["assets"],
                    "article": article["title"],
                    "quality": article["quality"],
                    "importance": article["importance"],
                    "views": article["views"],
                    "templates": article.get("templates", []),
                    "url": course_url(match["course"])
                })

    max_val = max(matrix[d][p] for d in depts for p in projects) or 1
    details_json = json.dumps(details)

    school_order = ["Engineering", "Science", "Humanities, Arts & Social Sciences",
                    "Architecture & Planning", "Management",
                    "Health Sciences & Technology", "Other"]
    groups = {}
    for s in school_order:
        groups[s] = [d for d in depts if DEPT_SCHOOL.get(d) == s]
    groups = {k: v for k, v in groups.items() if v}
    ungrouped = [d for d in depts if d not in DEPT_SCHOOL]
    if ungrouped:
        groups.setdefault("Other", [])
        groups["Other"].extend(ungrouped)

    def heat_color(t):
        if t <= 0: return "#f5f5f5"
        r = min(255, int(255 * (1 - t * 0.85)))
        g = min(255, int(255 * (1 - t * 0.45)))
        b = min(255, int(255 * (1 - t * 0.15)))
        return f"rgb({r},{g},{b})"

    def fmt_compact(n):
        if n >= 1000000:
            s = f"{n/1000000:.1f}M"
            return s.replace(".0M", "M")
        if n >= 1000:
            s = f"{n/1000:.1f}k"
            return s.replace(".0k", "k")
        return str(n)

    proj_cols = ""
    for p in projects:
        info = WIKIPROJECT_INFO.get(p, {})
        url = info.get("url", "#")
        desc = info.get("desc", "")
        proj_cols += (
            f'    <th class="hc" data-proj="{p}" onclick="sortBy(\'{p}\')">\n'
            f'      <a href="{url}" target="_blank" rel="noopener" class="wpl" title="{desc}">\U0001F310</a>\n'
            f'      <span class="pn">{p}</span>\n'
            f'      <span class="sa">\u2195</span>\n'
            f'    </th>\n'
        )

    rows_html = ""
    for school, dept_list in groups.items():
        rows_html += (
            f'  <tr class="gh" data-school="{school}">\n'
            f'    <td colspan="{len(projects) + 1}">'
            f'<span class="gs">{school}</span> '
            f'<span class="gc">({len(dept_list)} dep{"t" if len(dept_list) == 1 else "ts"})</span>'
            f'</td>\n  </tr>\n'
        )
        for d in dept_list:
            name = DEPT_NAMES.get(d, d)
            rows_html += (
                f'  <tr class="dr" data-dept="{d}" data-name="{name}">\n'
                f'    <td class="ll"><strong>{d}</strong> <span class="dn">{name}</span></td>\n'
            )
            for p in projects:
                val = matrix.get(d, {}).get(p, 0)
                key = f"{d}_{p}"
                if val == 0:
                    rows_html += f'    <td class="nc">\u2014</td>\n'
                else:
                    bg = heat_color(val / max_val)
                    items = details.get(key, [])
                    tip_lines = []
                    for item in items[:5]:
                        q = f'<span class="ql ql-{item["quality"]}">{item["quality"]}</span>'
                        tip_lines.append(
                            f'<div class="tl">{item["course"]} &middot; '
                            f'{item["article"]} {q}</div>'
                        )
                    if len(items) > 5:
                        tip_lines.append(
                            f'<div class="tl tm">+{len(items) - 5} more</div>'
                        )
                    tip_html = "".join(tip_lines)
                    rows_html += (
                        f'    <td class="mc" data-key="{key}">\n'
                        f'      <span class="bc clickable" style="background:{bg}" '
                        f'onclick="showDetail(\'{key}\')">\n'
                        f'        {val}\n'
                        f'        <span class="tip">{tip_html}</span>\n'
                        f'      </span>\n'
                        f'    </td>\n'
                    )
            rows_html += "  </tr>\n"

    legend_parts = "".join(
        f'<div style="background:{heat_color(i / max_val)}"></div>'
        for i in range(max_val + 1)
    )

    school_filters = '<span class="fl" data-sel="1" onclick="filterSchool(\'all\',this)">All</span>'
    for s in groups:
        school_filters += (
            f'<span class="fl" onclick="filterSchool(\'{s}\',this)">{s}</span>'
        )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CrossRef Match Heatmap — OCW ↔ Wikipedia</title>
<style>
*{{box-sizing:border-box}}
body{{font-family:'Inter','Segoe UI',sans-serif;background:#f6f8fa;margin:0;padding:2rem;color:#1a1a1a}}
h1{{font-size:1.5rem;font-weight:700;margin:0 0 .2rem;letter-spacing:-.02em}}
.s{{color:#666;font-size:.85rem;margin-bottom:1.5rem}}

/* Search + filters */
#sb{{display:flex;gap:12px;margin-bottom:1rem;flex-wrap:wrap;align-items:center}}
#search{{flex:1;min-width:180px;padding:8px 14px;border:1px solid #d0d7de;border-radius:6px;font-size:.85rem;background:#fff}}
#search:focus{{outline:0;border-color:#2563eb;box-shadow:0 0 0 3px rgba(37,99,235,.15)}}
#sf{{display:flex;gap:6px;flex-wrap:wrap}}
.fl{{padding:4px 12px;border-radius:20px;font-size:.78rem;cursor:pointer;color:#555;background:#e8ecf0;transition:all .15s;white-space:nowrap}}
.fl:hover{{background:#d0d7de}}
.fl[data-sel="1"]{{background:#2563eb;color:#fff}}

/* Table */
#ht{{border-collapse:collapse;width:100%;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
th,td{{padding:6px 8px;font-size:.78rem;text-align:center;border-bottom:1px solid #eee}}
.hl{{text-align:right;font-weight:600;color:#444;font-size:.7rem;letter-spacing:.04em;border-bottom:2px solid #d0d7de;padding-right:14px;white-space:nowrap}}
.hc{{font-weight:600;color:#444;font-size:.7rem;letter-spacing:.02em;border-bottom:2px solid #d0d7de;cursor:pointer;user-select:none;white-space:nowrap;position:relative;padding:8px 6px;vertical-align:middle}}
.hc:hover{{background:#f0f4f8}}
.wpl{{text-decoration:none;font-size:.85rem;opacity:.5;vertical-align:middle;margin-right:2px}}
.wpl:hover{{opacity:1}}
.pn{{vertical-align:middle}}
.sa{{margin-left:3px;font-size:.6rem;opacity:.3;vertical-align:middle}}
.hc:hover .sa{{opacity:.7}}
.ll{{text-align:right;font-weight:500;color:#222;padding-right:14px;white-space:nowrap;vertical-align:middle}}
.dn{{font-weight:400;color:#999;font-size:.7rem}}
.nc{{color:#ddd;font-size:.75rem}}
.mc{{text-align:center;padding:4px 6px;vertical-align:middle}}

/* Cell bubble */
.bc{{display:inline-flex;align-items:center;justify-content:center;height:26px;min-width:26px;border-radius:4px;padding:0 7px;font-size:.72rem;font-weight:700;color:#fff;position:relative;cursor:default;transition:transform .12s,box-shadow .12s}}
.bc:hover{{transform:scale(1.2);box-shadow:0 3px 12px rgba(0,0,0,.25);z-index:20}}
.clickable{{cursor:pointer!important}}
.bc.clickable:active{{transform:scale(.95)}}

/* Rich tooltip */
.tip{{position:absolute;bottom:calc(100% + 8px);left:50%;transform:translateX(-50%);background:#1a1a1a;color:#eee;padding:6px 10px;border-radius:5px;font-size:.7rem;white-space:nowrap;opacity:0;pointer-events:none;transition:opacity .15s;margin-bottom:0;line-height:1.5;z-index:100;box-shadow:0 4px 16px rgba(0,0,0,.3);font-weight:400;max-width:360px;white-space:normal}}
.tip::after{{content:'';position:absolute;top:100%;left:50%;margin-left:-5px;border:5px solid transparent;border-top-color:#1a1a1a}}
.bc:hover .tip{{opacity:1}}
.tl{{overflow:hidden;text-overflow:ellipsis}}
.tm{{color:#888;font-style:italic}}

/* Group header rows */
.gh td{{background:#f0f4f8;font-size:.75rem;font-weight:600;color:#555;text-align:left;padding:5px 14px;border-bottom:1px solid #d0d7de;letter-spacing:.03em}}
.gs{{text-transform:uppercase}}
.gc{{font-weight:400;color:#999;margin-left:6px}}

/* Legend */
.lg{{display:flex;align-items:center;gap:10px;margin-top:1.2rem;font-size:.78rem;color:#555}}
.lb{{display:flex;height:12px;border-radius:3px;overflow:hidden}}
.lb div{{width:24px}}

/* Quality badges */
.ql{{display:inline-block;padding:1px 6px;border-radius:3px;font-size:.65rem;font-weight:600;color:#fff}}
.ql-C{{background:#e68a2e}}
.ql-B{{background:#5599cc}}
.ql-Start{{background:#d45555}}
.ql-GA{{background:#5ba85b}}
.ql-Stub{{background:#aa5533}}

/* Sidebar panel */
#overlay{{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.35);z-index:200}}
#panel{{position:fixed;top:0;right:-520px;width:500px;height:100%;background:#fff;box-shadow:-4px 0 24px rgba(0,0,0,.12);z-index:300;transition:right .25s cubic-bezier(.4,0,.2,1);overflow-y:auto;overflow-x:hidden}}
#panel.panel-open{{right:0}}
.ph{{display:flex;align-items:center;justify-content:space-between;padding:1rem 1.25rem;border-bottom:1px solid #e8ecf0;position:sticky;top:0;background:#fff;z-index:10}}
#ptitle{{font-size:1rem;font-weight:600}}
.close{{cursor:pointer;color:#999;font-size:1.4rem;line-height:1;padding:2px 6px;border-radius:4px;transition:all .1s}}
.close:hover{{background:#f0f0f0;color:#333}}
#pbody{{padding:1rem 1.25rem}}
#pbody .sub{{color:#888;font-size:.82rem;margin-bottom:1rem}}

/* Detail table */
#dt{{width:100%;font-size:.78rem;border-collapse:collapse}}
#dt th{{text-align:left;font-weight:600;color:#555;font-size:.68rem;letter-spacing:.04em;border-bottom:2px solid #d0d7de;padding:6px 8px;white-space:nowrap}}
#dt td{{padding:8px;vertical-align:top;border-bottom:1px solid #f0f0f0}}
#dt tr:last-child td{{border-bottom:0}}
.cl{{font-weight:600;color:#2563eb;text-decoration:none}}
.cl:hover{{text-decoration:underline}}
.tt{{font-size:.72rem;color:#666}}
.vv{{font-size:.7rem;color:#888}}

/* Template pills */
.tc{{max-width:150px}}
.pill{{display:inline-block;padding:1px 8px;border-radius:10px;font-size:.65rem;background:#e8ecf0;color:#555;margin:1px 2px;white-space:nowrap}}
.pill:hover{{background:#d0d7de}}

/* Sort arrow active */
.sa-act{{opacity:1!important;color:#2563eb}}

/* Responsive */
@media(max-width:768px){{
body{{padding:1rem}}
h1{{font-size:1.2rem}}
#panel{{width:100%;right:-100%}}
#ht{{font-size:.7rem}}
th,td{{padding:4px 5px}}
}}
</style>
</head>
<body>
<h1>OCW ↔ Wikipedia Match Heatmap</h1>
<p class="s">{len(depts)} OCW departments &times; {len(projects)} WikiProjects — click a cell for details.</p>

<div id="sb">
  <input id="search" type="text" placeholder="Search departments by code or name\u2026" oninput="filterRows()">
  <div id="sf">{school_filters}</div>
</div>

<table id="ht">
  <thead>
    <tr>
      <th class="hl">Department</th>
      {proj_cols}
    </tr>
  </thead>
  <tbody>
    {rows_html}
  </tbody>
</table>

<div class="lg"><span>Match density:</span><div class="lb">{legend_parts}</div><span>0 &rarr; {max_val}</span></div>

<div id="overlay" onclick="hideDetail()"></div>
<div id="panel">
  <div class="ph"><span id="ptitle"></span><span class="close" onclick="hideDetail()">&times;</span></div>
  <div id="pbody"></div>
</div>

<script>
var DATA = {details_json};
var sortState = {{}};

function fmtViews(n) {{
    if (n >= 1000000) return (n/1000000).toFixed(1).replace('.0','') + 'M';
    if (n >= 1000) return (n/1000).toFixed(n%1000===0?0:1).replace('.0','') + 'k';
    return n.toString();
}}

function showDetail(key) {{
    var items = DATA[key];
    if (!items) return;
    var parts = key.split("_");
    var dept = parts[0], proj = parts.slice(1).join("_");
    document.getElementById('ptitle').textContent = dept + ' \u2192 ' + proj;
    var html = '<p class="sub">' + items.length + ' match' + (items.length !== 1 ? 'es' : '') + '</p>';
    html += '<table id="dt"><tr><th>Quality</th><th>Article</th><th>Templates</th><th>Course</th><th>Lecture</th><th>Assets</th></tr>';
    for (var i = 0; i < items.length; i++) {{
        var m = items[i];
        html += '<tr>';
        html += '<td><span class="ql ql-' + m.quality + '">' + m.quality + '</span></td>';
        html += '<td><a href="https://en.wikipedia.org/wiki/' + encodeURIComponent(m.article.replace(/ /g,"_")) + '" target="_blank">' + m.article + '</a><br><span class="vv">' + fmtViews(m.views) + ' views</span></td>';
        html += '<td class="tc">';
        for (var t = 0; t < m.templates.length; t++) {{
            html += '<span class="pill">' + m.templates[t] + '</span> ';
        }}
        html += '</td>';
        html += '<td>' + (m.url ? '<a href="' + m.url + '" target="_blank" class="cl">' + m.course + '</a>' : '<strong>' + m.course + '</strong>') + '<br><span class="tt">' + m.title + '</span></td>';
        html += '<td>' + (m.url ? '<a href="' + m.url + '" target="_blank">' + m.lecture + '</a>' : m.lecture) + '</td>';
        html += '<td>' + m.assets.replace("video+transcript","🎬📄").replace("lecture-notes","📝").replace("reading-list","📚") + '</td>';
        html += '</tr>';
    }}
    html += '</table>';
    document.getElementById('pbody').innerHTML = html;
    document.getElementById('panel').className = 'panel-open';
    document.getElementById('overlay').style.display = 'block';
    document.body.style.overflow = 'hidden';
}}

function hideDetail() {{
    document.getElementById('panel').className = '';
    document.getElementById('overlay').style.display = 'none';
    document.body.style.overflow = '';
}}

// Sort by WikiProject column
function sortBy(proj) {{
    var dir = sortState[proj] || 1;
    dir = -dir;
    sortState[proj] = dir;

    // Update arrow indicators
    var arrows = document.querySelectorAll('.hc .sa');
    for (var a = 0; a < arrows.length; a++) arrows[a].className = 'sa';
    var th = document.querySelector('th[data-proj="' + proj + '"]');
    if (th) {{
        var arrow = th.querySelector('.sa');
        if (arrow) {{
            arrow.className = 'sa sa-act';
            arrow.textContent = dir === 1 ? '\u2193' : '\u2191';
        }}
    }}

    var colIdx = -1;
    var ths = document.querySelectorAll('#ht thead th');
    for (var i = 0; i < ths.length; i++) {{
        if (ths[i].getAttribute('data-proj') === proj) {{
            colIdx = i;
            break;
        }}
    }}
    if (colIdx < 0) return;

    var tbody = document.querySelector('#ht tbody');
    var groups = [];
    var current = null;
    for (var i = 0; i < tbody.children.length; i++) {{
        var row = tbody.children[i];
        if (row.classList.contains('gh')) {{
            current = {{header: row, rows: []}};
            groups.push(current);
        }} else if (row.classList.contains('dr') && current) {{
            current.rows.push(row);
        }}
    }}

    for (var g = 0; g < groups.length; g++) {{
        var grp = groups[g];
        var rows = grp.rows;
        if (rows.length < 2) continue;
        rows.sort(function(a, b) {{
            var va = parseInt(a.cells[colIdx].textContent) || 0;
            var vb = parseInt(b.cells[colIdx].textContent) || 0;
            return (va - vb) * dir;
        }});
        var ref = grp.header;
        for (var r = 0; r < rows.length; r++) {{
            tbody.insertBefore(rows[r], ref.nextSibling);
            ref = rows[r];
        }}
    }}
}}

// Search filter
function filterRows() {{
    var q = document.getElementById('search').value.toLowerCase();
    var rows = document.querySelectorAll('.dr');
    for (var i = 0; i < rows.length; i++) {{
        var dept = rows[i].getAttribute('data-dept').toLowerCase();
        var name = rows[i].getAttribute('data-name').toLowerCase();
        rows[i].style.display = (dept.indexOf(q) > -1 || name.indexOf(q) > -1) ? '' : 'none';
    }}
    // Hide group headers with no visible children
    var groups = document.querySelectorAll('.gh');
    for (var g = 0; g < groups.length; g++) {{
        var next = groups[g].nextElementSibling;
        var visible = 0;
        while (next && !next.classList.contains('gh')) {{
            if (next.style.display !== 'none') visible++;
            next = next.nextElementSibling;
        }}
        groups[g].style.display = visible > 0 ? '' : 'none';
    }}
}}

// School filter
function filterSchool(school, el) {{
    var filters = document.querySelectorAll('.fl');
    for (var f = 0; f < filters.length; f++) filters[f].removeAttribute('data-sel');
    if (el) el.setAttribute('data-sel', '1');

    if (school === 'all') {{
        var rows = document.querySelectorAll('.dr');
        for (var i = 0; i < rows.length; i++) rows[i].style.display = '';
        var groups = document.querySelectorAll('.gh');
        for (var g = 0; g < groups.length; g++) groups[g].style.display = '';
        document.getElementById('search').value = '';
        return;
    }}
    document.getElementById('search').value = '';
    var groups = document.querySelectorAll('.gh');
    for (var g = 0; g < groups.length; g++) {{
        var header = groups[g];
        if (header.getAttribute('data-school') === school) {{
            header.style.display = '';
            var next = header.nextElementSibling;
            while (next && !next.classList.contains('gh')) {{
                if (next.classList.contains('dr')) next.style.display = '';
                next = next.nextElementSibling;
            }}
        }} else {{
            header.style.display = 'none';
            var next = header.nextElementSibling;
            while (next && !next.classList.contains('gh')) {{
                if (next.classList.contains('dr')) next.style.display = 'none';
                next = next.nextElementSibling;
            }}
        }}
    }}
}}
</script>
<p style="margin-top:1.2rem;color:#888;font-size:.78rem">Click a numbered cell to see course details. Generated {timestamp()}.</p>
</body>
</html>"""


def main():
    args = sys.argv[1:]
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    if "--report" in args and "--demo" in args:
        top_n = 10
        for i, a in enumerate(args):
            if a == "--top" and i + 1 < len(args):
                top_n = int(args[i + 1])
                break

        print(f"Generating crossref demo reports (top {top_n} matches)...")

        # Layer 1: Executive summary
        summary = generate_summary(top_n)
        (REPORT_DIR / "crossref-summary.md").write_text(summary)
        print(f"  wrote {REPORT_DIR / 'crossref-summary.md'}")

        # Layer 2: Project detail pages
        for project in DEMO_DATA:
            detail = generate_project_summary(project)
            path = REPORT_DIR / f"crossref-{project.lower().replace(' ', '-')}.md"
            path.write_text(detail)
            print(f"  wrote {path}")

        # Layer 3: Heatmap
        heatmap = generate_heatmap()
        (REPORT_DIR / "crossref-heatmap.html").write_text(heatmap)
        print(f"  wrote {REPORT_DIR / 'crossref-heatmap.html'}")

        print(f"\nDone. Open wiki/reports/ in WikiWise to browse.")

    elif "--report" in args:
        print("Live report mode requires SSH tunnel. Use --demo for now, or set up .env credentials.")
        print("  python3 scripts/crossref-wikipedia.py --report --demo")

    elif "--apply" in args:
        print("Apply mode not yet implemented. Review reports first, then run --apply.")
        print("  python3 scripts/crossref-wikipedia.py --report --demo")

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
