#!/usr/bin/env python3
"""
Review the collaborator's 185 cross-encoder-scored matches interactively.

Parses reranked_p79.pdf, resolves OCW course names to our course IDs/URLs,
and presents each match in an interactive [y/N/q] loop that posts via
apply-l1-refideas.py or apply-l2-external-links.py.

Usage:
    python3 scripts/review-collaborator-matches.py [--mode L1|L2] [--min-score 0.79]
    python3 scripts/review-collaborator-matches.py --mode L2 --min-score 0.90
    python3 scripts/review-collaborator-matches.py --export /tmp/review.json
"""

import os, sys, re, json, subprocess
from difflib import SequenceMatcher
from collections import defaultdict

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPTS_DIR)

# ─── Collaborator data (parsed from reranked_p79.pdf) ──────────────────────

# Known OCW course names from the collaborator's corpus (Environment/Climate/Energy domain)
COLLAB_COURSES = [
    "Acoustical Oceanography",
    "Analytical Techniques for Studying Environmental and Geologic Samples",
    "Climate Justice Instructional Toolkit",
    "Climate Physics and Chemistry",
    "D-Lab: Waste",
    "D-Lab: Water, Climate Change, and Health",
    "Dynamics of the Atmosphere",
    "Ecology II: Engineering for Sustainability",
    "Electromagnetic Energy: From Motors to Lasers",
    "Energy Decisions, Markets, and Policies",
    "Engineering, Economics and Regulation of the Electric Power Sector",
    "Environmental Technologies in Buildings",
    "Experimental Atmospheric Chemistry",
    "Foshan China Workshop",
    "Fundamentals of Photovoltaics",
    "General Circulation of the Earth's Atmosphere",
    "Geobiology",
    "Geothermal Energy Networks: Transforming Our Thermal Energy System",
    "Global Climate Change: Economics, Science, and Policy",
    "Global Warming Science",
    "Groundwater Hydrology",
    "Healthy Cities: Assessing Health Impacts of Policies and Plans",
    "Internal Combustion Engines",
    "Introduction to Geology",
    "Introduction to Observational Physical Oceanography",
    "Managing Nuclear Technology",
    "Marine Chemistry",
    "Molecular Biogeochemistry",
    "Nuclear Reactor Safety",
    "S-Lab: Laboratory for Sustainable Business",
    "Sedimentary Geology",
    "Seminar in Geophysics: Mantle Convection",
    "Sustainable Real Estate",
    "Systems Perspectives on Industrial Ecology",
    "Theoretical Environmental Analysis",
    "Thermodynamics and Climate Change",
    "Topics in Fluid Dynamics",
    "Transportation Policy and Environmental Limits",
    "Turbulence in the Ocean and Atmosphere",
    "Urban Energy Systems and Policy",
    "Urban Transportation, Land Use, and the Environment",
    "Water and Sanitation Infrastructure in Developing Countries",
]

# The 185 matches as (article, score, course_raw, lecture_raw) tuples
# parsed from the extracted PDF text
COLLAB_MATCHES = [
    # Air pollution
    ("Air pollution", 0.791, "Transportation Policy and Environmental Limits", "lec6soniahamel.pdf"),
    # Atmosphere of Earth
    ("Atmosphere of Earth", 0.904, "Marine Chemistry", "lec_12_ocn_at_ed.pdf"),
    ("Atmosphere of Earth", 0.796, "Climate Physics and Chemistry", "The Origin of the Earth, Atmosphere and Life"),
    # Biogeochemical cycle
    ("Biogeochemical cycle", 0.933, "Marine Chemistry", "lec_21_cos.pdf"),
    ("Biogeochemical cycle", 0.904, "Marine Chemistry", "lec_23_nitrgn.pdf"),
    ("Biogeochemical cycle", 0.885, "Marine Chemistry", "lec_22_nov_30_cy.pdf"),
    ("Biogeochemical cycle", 0.835, "Climate Physics and Chemistry", "Carbon Cycle 1: Summary Outline"),
    # Carbon cycle
    ("Carbon cycle", 0.946, "Global Warming Science", "Global Warming Science, Lecture 13"),
    ("Carbon cycle", 0.917, "Marine Chemistry", "lec_21_cos.pdf"),
    ("Carbon cycle", 0.888, "Climate Physics and Chemistry", "Carbon Cycle 1: Summary Outline"),
    # Carbon dioxide in the atmosphere of Earth
    ("Carbon dioxide in the atmosphere of Earth", 0.887, "Experimental Atmospheric Chemistry", "CO2 and Climate Change"),
    ("Carbon dioxide in the atmosphere of Earth", 0.854, "Climate Physics and Chemistry", "Carbon Cycle 1: Summary Outline"),
    ("Carbon dioxide in the atmosphere of Earth", 0.850, "Theoretical Environmental Analysis", "Theoretical Environmental Analysis, Lectures 6-9"),
    ("Carbon dioxide in the atmosphere of Earth", 0.834, "Global Warming Science", "Global Warming Science, Lecture 13"),
    # Carbon price
    ("Carbon price", 0.883, "Global Climate Change: Economics, Science, and Policy", "Emissions Trading and Tax Systems"),
    ("Carbon price", 0.861, "Engineering, Economics and Regulation of the Electric Power Sector", "MITESD_934S10_lec_26.pdf"),
    ("Carbon price", 0.818, "Global Climate Change: Economics, Science, and Policy", "Economics II: The Economics of Greenhouse Gas Emissions Control"),
    # Carbon sequestration
    ("Carbon sequestration", 0.798, "Global Warming Science", "Global Warming Science, Lecture 13"),
    # Carbon tax
    ("Carbon tax", 0.820, "Global Climate Change: Economics, Science, and Policy", "Emissions Trading and Tax Systems"),
    # Causes of climate change
    ("Causes of climate change", 0.839, "Global Warming Science", "Global Warming Science, Lecture 21"),
    ("Causes of climate change", 0.837, "Global Warming Science", "Global Warming Science, Lecture 15"),
    ("Causes of climate change", 0.819, "Global Warming Science", "Global Warming Science, Lecture 5"),
    # Climate change
    ("Climate change", 0.906, "Energy Decisions, Markets, and Policies", "Lecture 6: Climate Science and Policy"),
    ("Climate change", 0.906, "Energy Decisions, Markets, and Policies", "Lecture 6: Climate Science and Policy"),
    ("Climate change", 0.883, "Global Warming Science", "Global Warming Science, Lecture 21"),
    ("Climate change", 0.883, "Global Warming Science", "Global Warming Science, Lecture 21"),
    ("Climate change", 0.866, "D-Lab: Water, Climate Change, and Health", "EC.719 D-Lab: Water, Climate, and Health, Lec 4"),
    ("Climate change", 0.864, "D-Lab: Water, Climate Change, and Health", "EC.719 D-Lab: Water, Climate, and Health, Lec 4"),
    ("Climate change", 0.855, "Thermodynamics and Climate Change", "Chapter 7: Mitigating the Climate Crisis"),
    ("Climate change", 0.855, "Thermodynamics and Climate Change", "Chapter 7: Mitigating the Climate Crisis"),
    ("Climate change", 0.804, "Global Climate Change: Economics, Science, and Policy", "The Climate Machine V: Unresolved Problems in Climate Analysis"),
    ("Climate change", 0.804, "Global Climate Change: Economics, Science, and Policy", "The Climate Machine V: Unresolved Problems in Climate Analysis"),
    # Climate change feedbacks
    ("Climate change feedbacks", 0.877, "Global Warming Science", "Global Warming Science, Lecture 17"),
    ("Climate change feedbacks", 0.820, "Global Warming Science", "Global Warming Science, Lecture 15"),
    # Climate change mitigation
    ("Climate change mitigation", 0.910, "Thermodynamics and Climate Change", "Chapter 7: Mitigating the Climate Crisis"),
    ("Climate change mitigation", 0.790, "Engineering, Economics and Regulation of the Electric Power Sector", "MITESD_934S10_lec_23.pdf"),
    # Climate model
    ("Climate model", 0.933, "Global Warming Science", "Global Warming Science, Lecture 18"),
    ("Climate model", 0.928, "Global Climate Change: Economics, Science, and Policy", "The Mathematics of Climate Modeling"),
    ("Climate model", 0.912, "D-Lab: Water, Climate Change, and Health", "EC.719 D-Lab: Water, Climate Change, and Health, Lecture 5: Climate Modelling"),
    ("Climate model", 0.804, "General Circulation of the Earth's Atmosphere", "section9.pdf"),
    # Climate sensitivity
    ("Climate sensitivity", 0.878, "Global Warming Science", "Global Warming Science, Lecture 15"),
    # Climate variability and change
    ("Climate variability and change", 0.858, "Introduction to Geology", "Lecture 12 Notes: Climate through Geologic History"),
    ("Climate variability and change", 0.835, "D-Lab: Water, Climate Change, and Health", "EC.719 D-Lab: Water, Climate, and Health, Lec 4"),
    ("Climate variability and change", 0.828, "Global Climate Change: Economics, Science, and Policy", "The Climate Machine I: Past Climate, and Gases, Aerosols and Radiation"),
    ("Climate variability and change", 0.822, "Global Warming Science", "Global Warming Science, Lecture 15"),
    # Coal
    ("Coal", 0.890, "Sedimentary Geology", "ch12.pdf"),
    # Earth science
    ("Earth science", 0.902, "Introduction to Geology", "Lecture 13-15 Notes: Plate Tectonics"),
    ("Earth science", 0.883, "Sedimentary Geology", "ch8.pdf"),
    ("Earth science", 0.854, "Introduction to Geology", "Lecture 5 Notes: Metamorphic Rocks"),
    ("Earth science", 0.850, "Geobiology", "Geobiology, Lecture Notes 2"),
    ("Earth science", 0.844, "Sedimentary Geology", "ch11.pdf"),
    ("Earth science", 0.841, "Geobiology", "Geobiology, Lecture Notes 3"),
    ("Earth science", 0.839, "Seminar in Geophysics: Mantle Convection", "310398_notes.pdf"),
    ("Earth science", 0.832, "Introduction to Geology", "Lecture 2 Notes: Origin and Age of the Earth"),
    ("Earth science", 0.830, "Theoretical Environmental Analysis", "Theoretical Environmental Analysis, Lectures 2-5"),
    ("Earth science", 0.803, "Marine Chemistry", "lec_9_redngs_hyd.pdf"),
    # Effects of climate change
    ("Effects of climate change", 0.873, "Global Climate Change: Economics, Science, and Policy", "Introduction and Overview"),
    ("Effects of climate change", 0.828, "Global Climate Change: Economics, Science, and Policy", "The Climate Machine V: Unresolved Problems"),
    ("Effects of climate change", 0.791, "Global Warming Science", "Global Warming Science, Lecture 21"),
    # Electrical grid
    ("Electrical grid", 0.868, "Energy Decisions, Markets, and Policies", "Lecture 18: Tomorrow's Electric Power System: Challenges & Opportunities"),
    ("Electrical grid", 0.847, "Seminar in Electric Power Systems", "plan_a.pdf"),
    # Emissions trading
    ("Emissions trading", 0.948, "Engineering, Economics and Regulation of the Electric Power Sector", "MITESD_934S10_lec_26.pdf"),
    ("Emissions trading", 0.944, "Engineering, Economics and Regulation of the Electric Power Sector", "MITESD_934S10_lec_26a.pdf"),
    ("Emissions trading", 0.892, "Global Climate Change: Economics, Science, and Policy", "Emissions Trading and Tax Systems"),
    # Energy transition
    ("Energy transition", 0.817, "Engineering, Economics and Regulation of the Electric Power Sector", "MITESD_934S10_lec_23.pdf"),
    ("Energy transition", 0.812, "Managing Nuclear Technology", "lec23slides.pdf"),
    ("Energy transition", 0.806, "Engineering, Economics and Regulation of the Electric Power Sector", "MITESD_934S10_lec_03.pdf"),
    # Environmental impact assessment
    ("Environmental impact assessment", 0.867, "Healthy Cities: Assessing Health Impacts of Policies and Plans", "Healthy Cities, Lecture 14: HIA Applications"),
    # Environmental justice
    ("Environmental justice", 0.948, "Geothermal Energy Networks: Transforming Our Thermal Energy System", "Session 2-2: How GENs Can Meet Environmental Justice Priorities"),
    ("Environmental justice", 0.891, "Climate Justice Instructional Toolkit", "Introduction to Climate and Environmental Justice"),
    ("Environmental justice", 0.877, "Climate Justice Instructional Toolkit", "Environmental Justice and Technical Innovation"),
    ("Environmental justice", 0.815, "Climate Justice Instructional Toolkit", "Engineering and Climate Justice 2.0"),
    ("Environmental justice", 0.799, "Climate Justice Instructional Toolkit", "Climate Justice and Environmental Data"),
    # Fossil fuel
    ("Fossil fuel", 0.907, "Sedimentary Geology", "ch12.pdf"),
    ("Fossil fuel", 0.867, "Molecular Biogeochemistry", "MIT12_158F11_lec11.pdf"),
    # General circulation model
    ("General circulation model", 0.930, "Global Warming Science", "Global Warming Science, Lecture 18"),
    ("General circulation model", 0.923, "Global Warming Science", "Global Warming Science, Lecture 19"),
    ("General circulation model", 0.904, "D-Lab: Water, Climate Change, and Health", "EC.719 D-Lab: Water, Climate Change, and Health, Lecture 5: Climate Modelling"),
    ("General circulation model", 0.897, "General Circulation of the Earth's Atmosphere", "section9.pdf"),
    ("General circulation model", 0.887, "Global Climate Change: Economics, Science, and Policy", "The Mathematics of Climate Modeling"),
    # Geothermal energy
    ("Geothermal energy", 0.852, "Geothermal Energy Networks: Transforming Our Thermal Energy System", "Session 4-1: Networked Geothermal: The European Experience"),
    ("Geothermal energy", 0.817, "Geothermal Energy Networks: Transforming Our Thermal Energy System", "Session 7-3: Techno-Economic Modeling with HEATNETS Model"),
    # Glaciology
    ("Glaciology", 0.917, "Introduction to Geology", "Lecture 32 Notes: Glaciers"),
    # Green building
    ("Green building", 0.909, "Sustainable Real Estate", "11.350 Lecture 05"),
    ("Green building", 0.897, "Sustainable Real Estate", "11.350 Lecture 11"),
    ("Green building", 0.852, "Sustainable Real Estate", "11.350 Lecture 02"),
    ("Green building", 0.849, "S-Lab: Laboratory for Sustainable Business", "Green Buildings: New Services and Products from Market Transformation"),
    ("Green building", 0.849, "Sustainable Real Estate", "11.350 Lecture 03"),
    # Greenhouse effect
    ("Greenhouse effect", 0.849, "Introduction to Geology", "Lecture 12 Notes: Climate through Geologic History"),
    # Greenhouse gas
    ("Greenhouse gas", 0.891, "Global Warming Science", "Global Warming Science, Lecture 5"),
    ("Greenhouse gas", 0.887, "Global Climate Change: Economics, Science, and Policy", "The Climate Machine II: Greenhouse Gas Exchange Rates"),
    ("Greenhouse gas", 0.878, "Experimental Atmospheric Chemistry", "CO2 and Climate Change"),
    ("Greenhouse gas", 0.855, "Global Warming Science", "Global Warming Science, Lecture 21"),
    ("Greenhouse gas", 0.841, "Global Climate Change: Economics, Science, and Policy", "The Climate Machine I: Past Climate"),
    # Hydroelectricity
    ("Hydroelectricity", 0.818, "Engineering, Economics and Regulation of the Electric Power Sector", "MITESD_934S10_lec_03.pdf"),
    # Hydrogen economy
    ("Hydrogen economy", 0.948, "Internal Combustion Engines", "Internal Combustion Engines, Lecture 21: Hydrogen, fuel cell and battery"),
    # Hydrology
    ("Hydrology", 0.917, "Groundwater Hydrology", "1_72_lecture_1.pdf"),
    ("Hydrology", 0.914, "Groundwater Hydrology", "1_72_lecture_6.pdf"),
    ("Hydrology", 0.900, "Groundwater Hydrology", "1_72_lecture_5.pdf"),
    ("Hydrology", 0.888, "Groundwater Hydrology", "1_72_lecture_2.pdf"),
    ("Hydrology", 0.875, "Water and Sanitation Infrastructure in Developing Countries", "Water Sources and Water Supply Planning"),
    ("Hydrology", 0.857, "Groundwater Hydrology", "1_72_lecture_11.pdf"),
    ("Hydrology", 0.846, "Introduction to Geology", "Lecture 28 Notes: Rivers"),
    ("Hydrology", 0.816, "Groundwater Hydrology", "1_72_lecture_13.pdf"),
    ("Hydrology", 0.816, "Groundwater Hydrology", "1_72_lecture_12.pdf"),
    # Industrial ecology
    ("Industrial ecology", 0.943, "Systems Perspectives on Industrial Ecology", "lec14.pdf"),
    ("Industrial ecology", 0.921, "Systems Perspectives on Industrial Ecology", "lec11.pdf"),
    ("Industrial ecology", 0.883, "Systems Perspectives on Industrial Ecology", "lec12.pdf"),
    ("Industrial ecology", 0.863, "Systems Perspectives on Industrial Ecology", "lec3.pdf"),
    ("Industrial ecology", 0.860, "Systems Perspectives on Industrial Ecology", "lec10.pdf"),
    ("Industrial ecology", 0.816, "Systems Perspectives on Industrial Ecology", "lec1.pdf"),
    ("Industrial ecology", 0.814, "Systems Perspectives on Industrial Ecology", "lec8.pdf"),
    ("Industrial ecology", 0.803, "D-Lab: Waste", "Session 16: Life Cycle Analysis"),
    # Just transition
    ("Just transition", 0.854, "Climate Justice Instructional Toolkit", "Energy Justice"),
    ("Just transition", 0.797, "Urban Energy Systems and Policy", "11.165 fall 2022: Lecture 3"),
    # Kyoto Protocol
    ("Kyoto Protocol", 0.923, "Global Climate Change: Economics, Science, and Policy", "Institutions II: International Climate Negotiations"),
    # Life-cycle assessment
    ("Life-cycle assessment", 0.949, "D-Lab: Waste", "Session 16: Life Cycle Analysis"),
    ("Life-cycle assessment", 0.939, "Ecology II: Engineering for Sustainability", "Life Cycle Assessment: Concrete Production"),
    ("Life-cycle assessment", 0.930, "D-Lab: Waste", "MITEC_716F15_Session18"),
    ("Life-cycle assessment", 0.918, "Systems Perspectives on Industrial Ecology", "lec11.pdf"),
    ("Life-cycle assessment", 0.819, "Systems Perspectives on Industrial Ecology", "lec17.pdf"),
    ("Life-cycle assessment", 0.806, "Climate Justice Instructional Toolkit", "From Mining to E-Waste"),
    # Meteorology
    ("Meteorology", 0.828, "Dynamics of the Atmosphere", "chapter_5.pdf"),
    # Methane emissions
    ("Methane emissions", 0.791, "Climate Physics and Chemistry", "Atmospheric Chemistry II: Methane"),
    # Nitrogen cycle
    ("Nitrogen cycle", 0.917, "Marine Chemistry", "lec_23_nitrgn.pdf"),
    # Nuclear fission
    ("Nuclear fission", 0.820, "Nuclear Reactor Safety", "Lecture 2: Reactor Physics Review"),
    # Nuclear power
    ("Nuclear power", 0.819, "Managing Nuclear Technology", "lec14note_1.pdf"),
    ("Nuclear power", 0.809, "Nuclear Reactor Safety", "Lecture 23: Current Regulatory Issues"),
    ("Nuclear power", 0.802, "Nuclear Reactor Safety", "Lecture 1: Introduction and Overview"),
    ("Nuclear power", 0.799, "Managing Nuclear Technology", "lec15note.pdf"),
    ("Nuclear power", 0.791, "Managing Nuclear Technology", "lec23slides.pdf"),
    # Ocean acidification
    ("Ocean acidification", 0.904, "Marine Chemistry", "lec_7_crblc2006.pdf"),
    # Oceanography
    ("Oceanography", 0.890, "Acoustical Oceanography", "Lecture 13 Background Notes"),
    ("Oceanography", 0.857, "Climate Physics and Chemistry", "Notes on the Ocean Circulation for Climate Understanding"),
    ("Oceanography", 0.854, "Turbulence in the Ocean and Atmosphere", "ch9.pdf"),
    ("Oceanography", 0.846, "Introduction to Observational Physical Oceanography", "course_notes_10.pdf"),
    ("Oceanography", 0.842, "Introduction to Observational Physical Oceanography", "course_notes_7.pdf"),
    ("Oceanography", 0.823, "Introduction to Observational Physical Oceanography", "gbl_hgpc_atlas.pdf"),
    ("Oceanography", 0.817, "Topics in Fluid Dynamics", "Essay 3: A Coriolis Tutorial, Part 4"),
    # Ozone depletion
    ("Ozone depletion", 0.961, "Climate Physics and Chemistry", "Atmospheric Chemistry I: Ozone, CFCs, Nitrogen Oxides, and Dimethyl Sulfide"),
    ("Ozone depletion", 0.949, "Climate Physics and Chemistry", "Atmospheric Chemistry I: Ozone, CFCs, Nitrogen Oxides, and Dimethyl Sulfide"),
    # Particulate matter
    ("Particulate matter", 0.805, "Global Warming Science", "Global Warming Science, Lecture 14"),
    # Petroleum
    ("Petroleum", 0.894, "Molecular Biogeochemistry", "MIT12_158F11_lec11.pdf"),
    # Photovoltaics
    ("Photovoltaics", 0.921, "Fundamentals of Photovoltaics", "Modules Systems Reliability"),
    ("Photovoltaics", 0.896, "Electromagnetic Energy: From Motors to Lasers", "6.007 Lecture 47: Photodetectors, solar cells"),
    ("Photovoltaics", 0.893, "Fundamentals of Photovoltaics", "Lecture 14: Efficiency Limits"),
    ("Photovoltaics", 0.887, "Fundamentals of Photovoltaics", "Thin Films"),
    ("Photovoltaics", 0.881, "Fundamentals of Photovoltaics", "Advanced Concepts"),
    ("Photovoltaics", 0.873, "Fundamentals of Photovoltaics", "Silicon-based Photovoltaics"),
    # Plate tectonics
    ("Plate tectonics", 0.922, "Introduction to Geology", "Lecture 13-15 Notes: Plate Tectonics"),
    ("Plate tectonics", 0.854, "Seminar in Geophysics: Mantle Convection", "310398_notes.pdf"),
    ("Plate tectonics", 0.818, "Theoretical Environmental Analysis", "Theoretical Environmental Analysis, Lectures 2-5"),
    # Pollution
    ("Pollution", 0.897, "Analytical Techniques for Studying Environmental and Geologic Samples", "Anthropogenic Geochemistry"),
    ("Pollution", 0.802, "Experimental Atmospheric Chemistry", "Atmospheric Photochemistry and Air Pollution IV"),
    # Radiative forcing
    ("Radiative forcing", 0.913, "Global Warming Science", "Global Warming Science, Lecture 17"),
    ("Radiative forcing", 0.901, "Global Warming Science", "Global Warming Science, Lecture 15"),
    ("Radiative forcing", 0.800, "Global Climate Change: Economics, Science, and Policy", "The Climate Machine I: Past Climate"),
    # Recycling
    ("Recycling", 0.813, "D-Lab: Waste", "Session 6: End Goal of Waste"),
    # Renewable energy
    ("Renewable energy", 0.860, "Engineering, Economics and Regulation of the Electric Power Sector", "MITESD_934S10_lec_03.pdf"),
    # Sea level rise
    ("Sea level rise", 0.867, "Global Climate Change: Economics, Science, and Policy", "Sea Level Rise and Adaptation"),
    # Smart grid
    ("Smart grid", 0.821, "Energy Decisions, Markets, and Policies", "Lecture 18: Tomorrow's Electric Power System"),
    # Solar cell
    ("Solar cell", 0.927, "Electromagnetic Energy: From Motors to Lasers", "6.007 Lecture 47: Photodetectors, solar cells"),
    ("Solar cell", 0.897, "Fundamentals of Photovoltaics", "Thin Films"),
    ("Solar cell", 0.891, "Fundamentals of Photovoltaics", "Lecture 8: Materials Parameters"),
    ("Solar cell", 0.875, "Fundamentals of Photovoltaics", "Charge Transport"),
    ("Solar cell", 0.875, "Fundamentals of Photovoltaics", "Silicon-based Photovoltaics"),
    ("Solar cell", 0.873, "Fundamentals of Photovoltaics", "Lecture 7: Device Fundamentals"),
    ("Solar cell", 0.868, "Fundamentals of Photovoltaics", "Charge Transport"),
    ("Solar cell", 0.866, "Fundamentals of Photovoltaics", "Light Absorption"),
    ("Solar cell", 0.852, "Fundamentals of Photovoltaics", "Lecture 14: Efficiency Limits"),
    ("Solar cell", 0.844, "Fundamentals of Photovoltaics", "Advanced Concepts"),
    # Sustainable architecture
    ("Sustainable architecture", 0.839, "Sustainable Real Estate", "11.350 Lecture 03"),
    ("Sustainable architecture", 0.802, "S-Lab: Laboratory for Sustainable Business", "Green Buildings: New Services and Products"),
    # Sustainable transport
    ("Sustainable transport", 0.850, "Urban Transportation, Land Use, and the Environment", "lecture2.pdf"),
    ("Sustainable transport", 0.846, "Transportation Policy and Environmental Limits", "lec6soniahamel.pdf"),
    ("Sustainable transport", 0.826, "Transportation Policy and Environmental Limits", "lec5joe.pdf"),
    # Urban planning
    ("Urban planning", 0.861, "Foshan China Workshop", "mid_term_feed.pdf"),
    ("Urban planning", 0.796, "Urban Transportation, Land Use, and the Environment", "lecture4.pdf"),
    # Waste management
    ("Waste management", 0.922, "D-Lab: Waste", "Session 9: Waste Management Actors"),
    ("Waste management", 0.881, "D-Lab: Waste", "Session 6: End Goal of Waste"),
    ("Waste management", 0.814, "D-Lab: Waste", "MITEC_716F15_Session18"),
    ("Waste management", 0.801, "D-Lab: Waste", "Session 4: Landfill, Q&A, Numbers Game"),
    # Water cycle
    ("Water cycle", 0.910, "Groundwater Hydrology", "1_72_lecture_1.pdf"),
    ("Water cycle", 0.904, "Water and Sanitation Infrastructure in Developing Countries", "Water Sources and Water Supply Planning"),
    # Wind turbine
    ("Wind turbine", 0.860, "Environmental Technologies in Buildings", "4.401 Lecture 4"),
]

# ─── Resolve collaborator course names to wiki courses ─────────────────────

def load_wiki_courses():
    """Build {normalized_title: {slug, course_id, url, title}} from wiki/courses/."""
    courses_dir = os.path.join(PROJECT_DIR, "wiki", "courses")
    wiki = {}
    for fname in os.listdir(courses_dir):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(courses_dir, fname)
        with open(fpath) as f:
            content = f.read()
        cid = title = url = None
        in_fm = False
        for line in content.splitlines():
            if line == "---":
                in_fm = not in_fm
                continue
            if in_fm:
                if line.startswith("course_id:"):
                    cid = line.split(":", 1)[1].strip().strip('"')
                elif line.startswith("title:"):
                    title = line.split(":", 1)[1].strip().strip('"')
                elif line.startswith("url:"):
                    url = line.split(":", 1)[1].strip().strip('"')
        if cid and title and url:
            wiki[title.lower().strip()] = {"slug": fname[:-3], "course_id": cid, "url": url, "title": title}
    return wiki


def resolve_course(course_name: str, wiki_courses: dict) -> dict:
    """Match a collaborator course name to a wiki course entry."""
    nl = course_name.lower().strip()
    # Direct match
    if nl in wiki_courses:
        return wiki_courses[nl]
    # Before colon
    if ":" in nl:
        short = nl.split(":")[0].strip()
        if short in wiki_courses:
            return wiki_courses[short]
    # Fuzzy
    best = None
    best_score = 0
    for wt, info in wiki_courses.items():
        score = SequenceMatcher(None, nl, wt).ratio()
        if score > best_score:
            best_score = score
            best = info
    return best if best_score >= 0.5 else None


# ─── Color output ──────────────────────────────────────────────────────────

class Color:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

def c(text, color):
    return f"{color}{text}{Color.RESET}"


# ─── Build structured match list ───────────────────────────────────────────

def build_matches(wiki_courses: dict, min_score: float = 0.0):
    """Build structured match list from collaborator data."""
    matches = []
    unresolved_courses = set()
    
    for article, score, course_name, lecture in COLLAB_MATCHES:
        if score < min_score:
            continue
        
        resolved = resolve_course(course_name, wiki_courses)
        if not resolved:
            unresolved_courses.add(course_name)
            continue
        
        # Build a nice lecture description
        lecture_desc = lecture.replace(".pdf", "").replace("_", " ").replace("  ", " ").strip()
        
        matches.append({
            "article": article,
            "cross_encoder_score": score,
            "course_name": course_name,
            "course_id": resolved["course_id"],
            "course_title": resolved["title"],
            "course_url": resolved["url"],
            "course_slug": resolved["slug"],
            "lecture": lecture_desc,
            "source": "collaborator (zerank-2 cross-encoder)",
        })
    
    if unresolved_courses:
        print(c(f"  ⚠️  {len(unresolved_courses)} course names unresolved:", Color.YELLOW))
        for cn in sorted(unresolved_courses):
            print(f"       • {cn}")
    
    # Sort by score descending
    matches.sort(key=lambda m: m["cross_encoder_score"], reverse=True)
    return matches


# ─── Preview wikitext ──────────────────────────────────────────────────────

def build_refideas_wikitext(match: dict) -> str:
    """Build a {{refideas}} snippet for this match."""
    url = match["course_url"]
    title = match["course_title"]
    cid = match["course_id"]
    lecture = match["lecture"]
    
    if lecture and lecture != cid and not lecture.startswith("page"):
        description = f"MIT {cid}: {title} — {lecture}"
    else:
        description = f"MIT {cid}: {title}"
    
    return (
        f"{{{{Refideas\n"
        f"|1={{{{cite web |url={url} |title={title} |publisher=MIT OpenCourseWare}}}}\n"
        f"|comment=MIT {cid} covers this topic{' with ' + lecture if lecture and not lecture.startswith('page') and lecture != cid else ''}. "
        f"Cross-encoder similarity: {match['cross_encoder_score']:.3f}.\n"
        f"}}}}\n"
    )


def build_external_link_wikitext(match: dict) -> str:
    """Build an External links entry for this match."""
    url = match["course_url"]
    title = match["course_title"]
    cid = match["course_id"]
    lecture = match["lecture"]
    
    if lecture and lecture != cid and not lecture.startswith("page"):
        description = f"Full course with lecture on {lecture}."
    else:
        description = "Full course with video lectures, problem sets, and exams."
    
    return (
        f"* {{{{cite web |url={url} |title={title} |publisher=MIT OpenCourseWare}}}} — {description}"
    )


# ─── Post via existing tools ───────────────────────────────────────────────

def post_l1(match: dict):
    """Post refideas via apply-l1-refideas.py."""
    script = os.path.join(SCRIPTS_DIR, "apply-l1-refideas.py")
    cmd = [
        sys.executable, script,
        match["article"],
        "--course-id", match["course_id"],
        "--course-title", match["course_title"],
        "--course-url", match["course_url"],
        "--note", f"zerank-2 cross-encoder score: {match['cross_encoder_score']:.3f}. {match['lecture']}",
        "--yes",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return result


def post_l2(match: dict):
    """Post external links via apply-l2-external-links.py."""
    script = os.path.join(SCRIPTS_DIR, "apply-l2-external-links.py")
    cmd = [
        sys.executable, script,
        match["article"],
        "--course", match["course_slug"],
        "--description", f"Cross-encoder score {match['cross_encoder_score']:.3f}. Matched lecture: {match['lecture']}",
        "--yes",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return result


# ─── Interactive review ────────────────────────────────────────────────────

def show_match(match: dict, idx: int, total: int, mode: str):
    """Display one match for review."""
    score = match["cross_encoder_score"]
    score_color = Color.GREEN if score >= 0.90 else Color.YELLOW if score >= 0.80 else Color.RED
    score_bar = "█" * int(score * 20) + "░" * (20 - int(score * 20))
    
    print(f"\n{'='*70}")
    print(f"  {c(f'[{idx}/{total}]', Color.BOLD)} {c(match['article'], Color.BOLD)}")
    print(f"  ─{'─'*68}")
    print(f"  {c('Cross-encoder score:', Color.BOLD)} {c(f'{score:.3f}', score_color)}  {score_bar}")
    print(f"  {c('Course:', Color.BOLD)}            {match['course_id']} — {match['course_title']}")
    print(f"  {c('Lecture:', Color.BOLD)}           {match['lecture']}")
    print(f"  {c('Source:', Color.BOLD)}            {match['source']}")
    print(f"  {c('URL:', Color.BOLD)}               {match['course_url']}")
    print()
    
    if mode == "L1":
        print(f"  {c('├─ Refideas preview:', Color.CYAN)}")
        for line in build_refideas_wikitext(match).splitlines():
            print(f"  │  {line}")
    else:
        print(f"  {c('├─ External links preview:', Color.CYAN)}")
        for line in build_external_link_wikitext(match).splitlines():
            print(f"  │  {line}")
    print(f"  └{'─'*68}")


def interactive_review(matches: list, mode: str = "L1"):
    """Interactive [y/N/q] review loop."""
    if not matches:
        print(c("\n  No matches to review.", Color.YELLOW))
        return
    
    posted = 0
    skipped = 0
    
    print(f"\n  Reviewing {len(matches)} collaborator matches in {c(mode, Color.BOLD)} mode.")
    print(f"  {c('[y]', Color.GREEN)} = post  {c('[N]', Color.DIM)} = skip  {c('[q]', Color.RED)} = quit")
    
    for i, match in enumerate(matches, 1):
        show_match(match, i, len(matches), mode)
        
        try:
            response = input(f"\n  {c('Post? [y/N/q] ', Color.BOLD)}")
        except (EOFError, KeyboardInterrupt):
            print(c("\n  Quit.", Color.RED))
            break
        
        if response.lower() == "q":
            print(c("  Quit.", Color.RED))
            break
        elif response.lower() not in ("y", "yes"):
            print(c(f"  ⏭  Skipped.", Color.DIM))
            skipped += 1
            continue
        
        # Post it
        print(f"  {c('Posting...', Color.CYAN)}")
        if mode == "L1":
            result = post_l1(match)
        else:
            result = post_l2(match)
        
        stdout = result.stdout + result.stderr
        for line in stdout.splitlines():
            if any(kw in line for kw in ["✅", "❌", "⏭", "Refideas posted", "Edit failed"]):
                print(f"    {line.strip()}")
                break
        else:
            lines = [l for l in stdout.splitlines() if l.strip() and "Authenticated" not in l]
            if lines:
                print(f"    {lines[-1].strip()[:120]}")
        
        if "✅" in stdout or "Refideas posted" in stdout:
            posted += 1
        print()
    
    # Summary
    print(f"\n{'='*70}")
    print(f"  {c('Done.', Color.BOLD)} {posted} posted, {skipped} skipped, {len(matches) - posted - skipped} remaining.")
    print(f"{'='*70}\n")


# ─── Export ────────────────────────────────────────────────────────────────

def export_json(matches: list, path: str):
    """Export matches as JSON for use with prioritize-matches.py."""
    # Group into a project-like structure
    output = {
        "Environment (collaborator)": {
            "articles": []
        }
    }
    
    # Group by article
    from collections import OrderedDict
    by_article = OrderedDict()
    for m in matches:
        art = m["article"]
        if art not in by_article:
            by_article[art] = {"title": art, "templates": [], "ocw_matches": [], "quality": "?", "importance": "?", "views": 0}
        by_article[art]["ocw_matches"].append({
            "course": m["course_id"],
            "title": m["course_title"],
            "lecture": m["lecture"],
            "assets": "",
            "cross_encoder_score": m["cross_encoder_score"],
        })
    
    output["Environment (collaborator)"]["articles"] = list(by_article.values())
    
    with open(path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"  Exported {len(by_article)} articles ({len(matches)} matches) to {path}")


# ─── CLI ────────────────────────────────────────────────────────────────────

def main():
    mode = "L1"
    min_score = 0.79
    export_path = None
    
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--mode":
            i += 1
            if i < len(args):
                mode = args[i].upper()
        elif args[i] == "--min-score":
            i += 1
            if i < len(args):
                min_score = float(args[i])
        elif args[i] == "--export":
            i += 1
            if i < len(args):
                export_path = args[i]
        elif args[i] in ("-h", "--help"):
            print(__doc__)
            return
        i += 1
    
    print(f"  Loading wiki course catalog...")
    wiki_courses = load_wiki_courses()
    print(f"  Loaded {len(wiki_courses)} courses")
    
    print(f"  Building match list (min score: {min_score})...")
    matches = build_matches(wiki_courses, min_score)
    print(f"  {len(matches)} matches across {len(set(m['article'] for m in matches))} articles")
    
    # Score distribution
    if matches:
        bins = {"0.95+": 0, "0.90-0.94": 0, "0.85-0.89": 0, "0.80-0.84": 0, "0.79-0.79": 0}
        for m in matches:
            s = m["cross_encoder_score"]
            if s >= 0.95: bins["0.95+"] += 1
            elif s >= 0.90: bins["0.90-0.94"] += 1
            elif s >= 0.85: bins["0.85-0.89"] += 1
            elif s >= 0.80: bins["0.80-0.84"] += 1
            else: bins["0.79-0.79"] += 1
        print(f"  Score distribution:")
        for label, count in bins.items():
            bar = "█" * count
            print(f"    {label}: {count:>3} {bar}")
    
    if export_path:
        export_json(matches, export_path)
        return
    
    if not matches:
        print(c("\n  No matches to review.", Color.YELLOW))
        return
    
    interactive_review(matches, mode)


if __name__ == "__main__":
    main()
