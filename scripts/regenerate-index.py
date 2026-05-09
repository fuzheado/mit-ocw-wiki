#!/usr/bin/env python3
"""
Regenerate wiki/index.md by scanning the actual file system.

Run after any batch ingest to keep the index in sync.
Usage: python3 scripts/regenerate-index.py
"""

import os
from pathlib import Path

WIKI_DIR = Path(__file__).resolve().parent.parent / "wiki"


def count_files(subdir: str) -> int:
    path = WIKI_DIR / subdir
    if not path.exists():
        return 0
    return len([f for f in os.listdir(path) if f.endswith(".md")])


def count_courses_by_department() -> dict:
    """Count how many courses link to each department page."""
    counts = {}
    dept_dir = WIKI_DIR / "departments"
    if not dept_dir.exists():
        return counts
    for f in sorted(dept_dir.iterdir()):
        if not f.name.endswith(".md"):
            continue
        content = f.read_text()
        course_lines = [l for l in content.split("\n") if l.strip().startswith("- [[") and "courses" not in l.split("[[")[0]]
        # Count lines under "## Courses" section
        in_section = False
        count = 0
        for line in content.split("\n"):
            if line.strip().startswith("## Courses"):
                in_section = True
                continue
            if in_section and line.strip().startswith("## "):
                break
            if in_section and line.strip().startswith("- [[") and "None yet" not in line:
                count += 1
        dept_id = f.name.replace(".md", "")
        name_line = [l for l in content.split("\n") if l.startswith("# ") and not l.startswith("## ")]
        name = name_line[0].replace("# ", "").strip() if name_line else dept_id
        counts[dept_id] = (name, count)
    return counts


def build_index() -> str:
    course_count = count_files("courses")
    instructor_count = count_files("instructors")
    dept_counts = count_courses_by_department()

    dept_order = [
        "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12",
        "14", "15", "16", "17", "18", "20", "21a", "21g", "21h", "21l", "21m",
        "22", "24", "cc", "cms-w", "ec", "es", "esd", "hst", "ids",
        "mas", "pe", "sp", "sts", "wgs"
    ]

    lines = []
    lines.append("> For a narrative overview, see [[home]].")
    lines.append("")
    lines.append("# Index")
    lines.append("")
    lines.append("## Meta")
    lines.append("")
    lines.append("- [[home]] — entry point and current status")
    lines.append("- [[log]] — chronological record of all work")
    lines.append("- [[overview]] — top-level synthesis of OCW as a whole")
    lines.append("")
    lines.append(f"## Courses ({course_count})")
    lines.append("")
    lines.append("Browse by department:")
    lines.append("")

    for dept_id in dept_order:
        if dept_id in dept_counts:
            name, count = dept_counts[dept_id]
            lines.append(f"- [[{dept_id}|{name}]] — {count} courses")

    lines.append("")
    lines.append("## Topics (110)")
    lines.append("")
    lines.append("""Browse by topic area:

- [[science-math|Science & Math]] — [[biology|Biology]], [[chemistry|Chemistry]], [[earth-science|Earth Science]], [[physics|Physics]], [[mathematics|Mathematics]], [[cognitive-science|Cognitive Science]]
- [[engineering|Engineering]] — [[civil-engineering|Civil]], [[mechanical-engineering|Mechanical]], [[electrical-engineering|Electrical]], [[chemical-engineering|Chemical]], [[aerospace-engineering|Aerospace]], [[environmental-engineering|Environmental]], [[materials-science-and-engineering|Materials Science]], [[nuclear-engineering|Nuclear]], [[ocean-engineering|Ocean]], [[biological-engineering|Biological]], [[systems-engineering|Systems]]
- [[data-science-analytics-and-computer-technology|Data Science & Computer Technology]] — [[computer-science|Computer Science]], [[ai|AI]], [[machine-learning|Machine Learning]], [[data-science|Data Science]], [[algorithms-and-data-structures|Algorithms]], [[programming-coding|Programming]], [[software-design-and-engineering|Software Engineering]], [[networks-and-security|Networks & Security]], [[cybersecurity|CyberSecurity]], [[visualization|Visualization]]
- [[business-and-management|Business & Management]] — [[entrepreneurship|Entrepreneurship]], [[finance-accounting|Finance]], [[marketing|Marketing]], [[operations|Operations]], [[supply-chain|Supply Chain]], [[strategy-and-innovation|Strategy]], [[management|Management]]
- [[social-sciences|Social Sciences]] — [[economics|Economics]], [[political-science|Political Science]], [[sociology|Sociology]], [[anthropology|Anthropology]], [[psychology|Psychology]], [[law|Law]], [[urban-studies|Urban Studies]], [[international-development|International Development]], [[communication|Communication]]
- [[humanities|Humanities]] — [[history|History]], [[literature|Literature]], [[philosophy|Philosophy]], [[linguistics|Linguistics]], [[music|Music]], [[language|Language]], [[religion|Religion]]
- [[art-design-and-architecture|Art, Design & Architecture]] — [[architecture|Architecture]], [[visual-arts|Visual Arts]], [[media-studies|Media Studies]], [[game-design|Game Design]], [[art-history|Art History]], [[performing-arts|Performing Arts]], [[real-estate|Real Estate]]
- [[energy-climate-and-sustainability|Energy, Climate & Sustainability]] — [[energy|Energy]], [[climate-science|Climate Science]], [[climate-and-energy-policy|Climate and Energy Policy]], [[sustainable-business|Sustainable Business]], [[environmental-and-climate-justice|Environmental Justice]], [[natural-systems|Natural Systems]], [[adaptation-and-resilience|Adaptation and Resilience]]
- [[health-and-medicine|Health & Medicine]] — [[public-health|Public Health]], [[biomedical-technologies|Biomedical Technologies]], [[health-care-management|Health Care Management]], [[imaging|Imaging]], [[immunology|Immunology]], [[mental-health|Mental Health]], [[pathology-and-pathophysiology|Pathology]], [[pharmacology-and-toxicology|Pharmacology]]
- [[innovation-and-entrepreneurship|Innovation & Entrepreneurship]] — [[startupsnew-enterprises|Startups]], [[innovation-process|Innovation Process]], [[product-innovation|Product Innovation]], [[corporate-innovation|Corporate Innovation]], [[inventions-and-patents|Inventions & Patents]]
- [[education-and-teaching|Education & Teaching]] — [[educational-technology|Educational Technology]], [[pedagogy-and-curriculum|Pedagogy]], [[education-policy|Education Policy]], [[digital-learning|Digital Learning]], [[faculty-leadership|Faculty Leadership]]""")
    lines.append("")
    lines.append(f"## Instructors ({instructor_count})")
    lines.append("")
    lines.append("Instructor pages exist for all faculty. Browse by department to find relevant instructors, or search the wiki.")
    lines.append("")
    lines.append("## Crossrefs (Wikipedia)")
    lines.append("")
    lines.append("*None yet. Stage 4 not yet run.*")
    lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    index = build_index()
    index_path = WIKI_DIR / "index.md"
    index_path.write_text(index)
    print(f"Regenerated {index_path} ({count_files('courses')} courses, {count_files('instructors')} instructors)")
