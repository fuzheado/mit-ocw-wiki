#!/usr/bin/env python3
"""
Contribution Protocol — reference implementation.

Usage:
    python3 scripts/contribution-protocol.py --validate    # Validate all example records
    python3 scripts/contribution-protocol.py --examples    # Print example records as JSON
    python3 scripts/contribution-protocol.py --wikitext    # Print wikitext for each example
    python3 scripts/contribution-protocol.py --generate    # Generate records from live-data.js + crossref data
"""

import json
import re
import sys
import hashlib
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from enum import Enum


# ─── Enums ──────────────────────────────────────────────────────────────────

class Level(str, Enum):
    L1 = "L1"  # Talk page Refideas
    L2 = "L2"  # External links
    L3 = "L3"  # Replace Citation needed
    L4 = "L4"  # Fill Missing information
    L5 = "L5"  # New content / section

class Status(str, Enum):
    PENDING = "pending"
    IN_REVIEW = "in_review"
    APPLIED = "applied"
    REJECTED = "rejected"
    SKIPPED = "skipped"

class ActionType(str, Enum):
    TALK_PAGE = "talk_page"
    EXTERNAL_LINK = "external_link"
    REPLACE_TEMPLATE = "replace_template"
    ADD_SECTION = "add_section"
    NEW_CONTENT = "new_content"

class ResourceType(str, Enum):
    VIDEO = "video"
    LECTURE_NOTES = "lecture_notes"
    PROBLEM_SET = "problem_set"
    READING_LIST = "reading_list"


# ─── Data Classes ───────────────────────────────────────────────────────────

@dataclass
class Article:
    title: str
    url: str
    quality: str
    importance: str
    views: int
    wikiproject: str

@dataclass
class Source:
    course_id: str
    course_title: str
    course_url: str
    resource_type: str
    license: str = "CC BY-NC-SA 4.0"
    lecture_title: Optional[str] = None
    lecture_url: Optional[str] = None

@dataclass
class Action:
    type: str
    target_location: str
    wikitext: str
    edit_summary: str
    context_before: Optional[str] = None
    context_after: Optional[str] = None

@dataclass
class TemplateInfo:
    name: Optional[str] = None
    section: Optional[str] = None
    date: Optional[str] = None
    context: Optional[str] = None
    missing_topic: Optional[str] = None

@dataclass
class LinkInfo:
    label: Optional[str] = None
    description: Optional[str] = None

@dataclass
class ContentInfo:
    summary: Optional[str] = None
    format: Optional[str] = None
    section_title: Optional[str] = None
    body: Optional[str] = None
    position: Optional[str] = None

@dataclass
class Review:
    notes: Optional[str] = None
    applied_at: Optional[str] = None
    revision_id: Optional[int] = None

@dataclass
class ContributionRecord:
    id: str
    level: Level
    status: Status
    score: float
    created: str
    article: Article
    source: Source
    action: Action
    template: Optional[TemplateInfo] = None
    link: Optional[LinkInfo] = None
    content: Optional[ContentInfo] = None
    review: Optional[Review] = None

    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dict, omitting None optionals."""
        d = {
            "id": self.id,
            "level": self.level.value,
            "status": self.status.value,
            "score": self.score,
            "created": self.created,
            "article": asdict(self.article),
            "source": _omit_none(asdict(self.source)),
            "action": _omit_none(asdict(self.action)),
        }
        if self.template:
            d["template"] = _omit_none(asdict(self.template))
        if self.link:
            d["link"] = _omit_none(asdict(self.link))
        if self.content:
            d["content"] = _omit_none(asdict(self.content))
        if self.review:
            d["review"] = _omit_none(asdict(self.review))
        return d

    def validate(self) -> List[str]:
        """Validate the record. Returns list of errors (empty = valid)."""
        errors = []

        # Common validations
        if not self.article.title:
            errors.append("article.title is empty")
        if "ocw.mit.edu" not in self.source.course_url:
            errors.append(f"source.course_url is not an OCW URL: {self.source.course_url}")
        if not (0 <= self.score <= 100):
            errors.append(f"score out of range: {self.score}")
        if self.source.license != "CC BY-NC-SA 4.0":
            errors.append(f"source.license must be CC BY-NC-SA 4.0, got: {self.source.license}")

        # Level-specific
        level = self.level
        action_type = self.action.type

        if level == Level.L1:
            if action_type != ActionType.TALK_PAGE.value:
                errors.append(f"L1 requires action.type=talk_page, got: {action_type}")
            if "{{refideas" not in self.action.wikitext.lower():
                errors.append("L1 wikitext must contain {{refideas}}")
            if "[http" not in self.action.wikitext:
                errors.append("L1 wikitext must contain an external link in [url Label] format")

        elif level == Level.L2:
            if action_type != ActionType.EXTERNAL_LINK.value:
                errors.append(f"L2 requires action.type=external_link, got: {action_type}")
            if not self.link or not self.link.label:
                errors.append("L2 requires link.label")
            if not self.link or not self.link.description:
                errors.append("L2 requires link.description")
            if "* {{cite web" not in self.action.wikitext:
                errors.append("L2 wikitext must be a bulleted {{cite web}}")

        elif level == Level.L3:
            if action_type != ActionType.REPLACE_TEMPLATE.value:
                errors.append(f"L3 requires action.type=replace_template, got: {action_type}")
            if not self.template or not self.template.name:
                errors.append("L3 requires template.name")
            if not self.template or not self.template.section:
                errors.append("L3 requires template.section")
            if "<ref>" not in self.action.wikitext:
                errors.append("L3 wikitext must contain <ref> tags")
            if "{{cite web" not in self.action.wikitext:
                errors.append("L3 wikitext must contain a {{cite web}} template")

        elif level == Level.L4:
            if action_type != ActionType.ADD_SECTION.value:
                errors.append(f"L4 requires action.type=add_section, got: {action_type}")
            if not self.template or not self.template.missing_topic:
                errors.append("L4 requires template.missing_topic")
            if not self.content or not self.content.summary:
                errors.append("L4 requires content.summary")
            if "<ref>" not in self.action.wikitext:
                errors.append("L4 wikitext must contain <ref> tags")

        elif level == Level.L5:
            if action_type != ActionType.NEW_CONTENT.value:
                errors.append(f"L5 requires action.type=new_content, got: {action_type}")
            if not self.content or not self.content.section_title:
                errors.append("L5 requires content.section_title")
            if not self.content or not self.content.body:
                errors.append("L5 requires content.body")
            if not self.content or not self.content.position:
                errors.append("L5 requires content.position")
            if "==" not in self.action.wikitext:
                errors.append("L5 wikitext must contain section headings (== ... ==)")

        return errors


def _omit_none(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


# ─── Factory Functions ──────────────────────────────────────────────────────

def make_id(level: str, article_title: str, course_id: str, suffix: str = "") -> str:
    """Generate a deterministic, human-readable record ID."""
    slug = re.sub(r'[^a-zA-Z0-9]+', '_', article_title.lower()).strip('_')
    cid = course_id.lower().replace('.', '_')
    base = f"{level}-{slug}-{cid}"
    if suffix:
        base += f"-{suffix}"
    return base

def make_l1(
    article_title: str,
    course_id: str,
    course_title: str,
    course_url: str,
    resource_type: str,
    wikiproject: str,
    quality: str,
    importance: str,
    views: int,
    score: float,
    lecture_title: Optional[str] = None,
    lecture_url: Optional[str] = None,
    note: str = "",
) -> ContributionRecord:
    """Factory for L1 — Talk page Refideas.
    
    Generates a plain external link reference in the standard [url Label], Source format.
    If the Talk page already has a {{refideas}} block, the caller should append to it.
    If not, this block is inserted before the first == heading.
    """
    label = f"MIT {course_id}: {course_title}"
    ref = f"[{course_url} {label}], MIT OpenCourseWare"
    if note:
        ref += f" ({note})"
    if lecture_title:
        ref += f" — {lecture_title}"

    wikitext = (
        "{{refideas\n"
        f"| 1 = {ref}\n"
        "}}"
    )

    return ContributionRecord(
        id=make_id("L1", article_title, course_id),
        level=Level.L1,
        status=Status.PENDING,
        score=score,
        created=datetime.now(timezone.utc).isoformat(),
        article=Article(
            title=article_title,
            url=f"https://en.wikipedia.org/wiki/{article_title.replace(' ', '_')}",
            quality=quality,
            importance=importance,
            views=views,
            wikiproject=wikiproject,
        ),
        source=Source(
            course_id=course_id,
            course_title=course_title,
            course_url=course_url,
            lecture_title=lecture_title,
            lecture_url=lecture_url,
            resource_type=resource_type,
        ),
        action=Action(
            type=ActionType.TALK_PAGE.value,
            target_location="__BEFORE_FIRST_HEADING__",
            wikitext=wikitext,
            edit_summary=f"/* Reference suggestion */ Suggested MIT {course_id} as a resource for this article via Wiki MIT",
        ),
    )

def make_l2(
    article_title: str,
    course_id: str,
    course_title: str,
    course_url: str,
    wikiproject: str,
    quality: str,
    importance: str,
    views: int,
    score: float,
    description: str,
    resource_type: str = "reading_list",
) -> ContributionRecord:
    """Factory for L2 — External link."""
    label = f"MIT {course_id}: {course_title}"

    wikitext = (
        f"* {{{{cite web |url={course_url} |title={course_title} |publisher=MIT OpenCourseWare}}}} — {description}"
    )

    return ContributionRecord(
        id=make_id("L2", article_title, course_id),
        level=Level.L2,
        status=Status.PENDING,
        score=score,
        created=datetime.now(timezone.utc).isoformat(),
        article=Article(
            title=article_title,
            url=f"https://en.wikipedia.org/wiki/{article_title.replace(' ', '_')}",
            quality=quality,
            importance=importance,
            views=views,
            wikiproject=wikiproject,
        ),
        source=Source(
            course_id=course_id,
            course_title=course_title,
            course_url=course_url,
            resource_type=resource_type,
        ),
        action=Action(
            type=ActionType.EXTERNAL_LINK.value,
            target_location="__EXTERNAL_LINKS__",
            wikitext=wikitext,
            edit_summary=f"/* External links */ Added MIT {course_id} as an educational resource via Wiki MIT",
        ),
        link=LinkInfo(label=label, description=description),
    )

def make_l3(
    article_title: str,
    course_id: str,
    course_title: str,
    course_url: str,
    lecture_title: str,
    lecture_url: str,
    resource_type: str,
    wikiproject: str,
    quality: str,
    importance: str,
    views: int,
    score: float,
    template_name: str,
    template_section: str,
    template_date: str,
    template_context: str,
    context_before: str,
    context_after: str,
) -> ContributionRecord:
    """Factory for L3 — Replace Citation needed."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ref_title = lecture_title or course_title
    ref_url = lecture_url or course_url

    wikitext = (
        f"<ref>{{{{cite web |url={ref_url} |title={ref_title} ({course_id} {course_title}) "
        f"|publisher=MIT OpenCourseWare |access-date={today}}}}}</ref>"
    )

    return ContributionRecord(
        id=make_id("L3", article_title, course_id, template_name.lower()),
        level=Level.L3,
        status=Status.PENDING,
        score=score,
        created=datetime.now(timezone.utc).isoformat(),
        article=Article(
            title=article_title,
            url=f"https://en.wikipedia.org/wiki/{article_title.replace(' ', '_')}",
            quality=quality,
            importance=importance,
            views=views,
            wikiproject=wikiproject,
        ),
        source=Source(
            course_id=course_id,
            course_title=course_title,
            course_url=course_url,
            lecture_title=lecture_title,
            lecture_url=lecture_url,
            resource_type=resource_type,
        ),
        action=Action(
            type=ActionType.REPLACE_TEMPLATE.value,
            target_location="__CITATION_TAG__",
            wikitext=wikitext,
            edit_summary=f"/* Citation */ Added citation from MIT {course_id} via Wiki MIT",
            context_before=context_before,
            context_after=context_after,
        ),
        template=TemplateInfo(
            name=template_name,
            section=template_section,
            date=template_date,
            context=template_context,
        ),
    )

def make_l4(
    article_title: str,
    course_id: str,
    course_title: str,
    course_url: str,
    lecture_title: str,
    lecture_url: str,
    resource_type: str,
    wikiproject: str,
    quality: str,
    importance: str,
    views: int,
    score: float,
    template_section: str,
    missing_topic: str,
    content_summary: str,
    context_before: str,
    context_after: str,
) -> ContributionRecord:
    """Factory for L4 — Fill Missing information."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ref_title = lecture_title or course_title
    ref_url = lecture_url or course_url

    wikitext = (
        f"{content_summary}"
        f"<ref>{{{{cite web |url={ref_url} |title={ref_title} ({course_id} {course_title}) "
        f"|publisher=MIT OpenCourseWare |access-date={today}}}}}</ref>"
    )

    return ContributionRecord(
        id=make_id("L4", article_title, course_id, "missing"),
        level=Level.L4,
        status=Status.PENDING,
        score=score,
        created=datetime.now(timezone.utc).isoformat(),
        article=Article(
            title=article_title,
            url=f"https://en.wikipedia.org/wiki/{article_title.replace(' ', '_')}",
            quality=quality,
            importance=importance,
            views=views,
            wikiproject=wikiproject,
        ),
        source=Source(
            course_id=course_id,
            course_title=course_title,
            course_url=course_url,
            lecture_title=lecture_title,
            lecture_url=lecture_url,
            resource_type=resource_type,
        ),
        action=Action(
            type=ActionType.ADD_SECTION.value,
            target_location=template_section,
            wikitext=wikitext,
            edit_summary=f"/* {template_section} */ Added content on {missing_topic}, citing MIT {course_id} via Wiki MIT",
            context_before=context_before,
            context_after=context_after,
        ),
        template=TemplateInfo(
            section=template_section,
            missing_topic=missing_topic,
        ),
        content=ContentInfo(
            summary=content_summary,
            format="paragraph",
        ),
    )

def make_l5(
    article_title: str,
    course_id: str,
    course_title: str,
    course_url: str,
    wikiproject: str,
    quality: str,
    importance: str,
    views: int,
    score: float,
    section_title: str,
    body: str,
    position: str,
    resource_type: str = "reading_list",
) -> ContributionRecord:
    """Factory for L5 — New content / section."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    wikitext = (
        f"== {section_title} ==\n\n"
        f"{body}"
        f"<ref>{{{{cite web |url={course_url} |title={course_title} "
        f"|publisher=MIT OpenCourseWare |access-date={today}}}}}</ref>\n"
    )

    return ContributionRecord(
        id=make_id("L5", article_title, course_id),
        level=Level.L5,
        status=Status.PENDING,
        score=score,
        created=datetime.now(timezone.utc).isoformat(),
        article=Article(
            title=article_title,
            url=f"https://en.wikipedia.org/wiki/{article_title.replace(' ', '_')}",
            quality=quality,
            importance=importance,
            views=views,
            wikiproject=wikiproject,
        ),
        source=Source(
            course_id=course_id,
            course_title=course_title,
            course_url=course_url,
            resource_type=resource_type,
        ),
        action=Action(
            type=ActionType.NEW_CONTENT.value,
            target_location=position,
            wikitext=wikitext,
            edit_summary=f"/* {section_title} */ Added section citing MIT {course_id} via Wiki MIT",
        ),
        content=ContentInfo(
            section_title=section_title,
            body=body,
            position=position,
        ),
    )


# ─── L1 Insertion Utility ─────────────────────────────────────────────────

def build_refideas_wikitext(
    wikitext: str,
    url: str,
    label: str,
    source: str = "",
    note: str = "",
) -> dict:
    """
    Pure function: given Talk page wikitext, produce new wikitext with a
    {{refideas}} reference appended or inserted. No API calls, no side effects.

    This is the testable core — feed it any wikitext string, get back the
    modified wikitext. For testing, pass hand-crafted wikitext fixtures.

    Returns:
        {"action": "append" | "insert" | "append_end",
         "detail": str, "wikitext": str, "summary": str}
    """
    import mwparserfromhell
    import re

    # Known refideas template aliases (all redirect to Template:Refideas)
    _REFIDEAS_ALIASES = {
        "refideas", "refidea", "ri", "ref ideas",
        "suggested sources", "suggested refs", "source ideas",
        "potential sources", "possible sources", "refideas-nonotice",
        "refsuggestion",
    }

    # Construct the reference string
    ref = f"[{url} {label}]"
    if source:
        ref += f", {source}"
    if note:
        ref += f" ({note})"

    code = mwparserfromhell.parse(wikitext)
    existing = code.filter_templates(
        matches=lambda t: str(t.name).lower().strip() in _REFIDEAS_ALIASES
    )

    if existing:
        # Append to existing Refideas
        tmpl = existing[0]
        max_num = 0
        for param in tmpl.params:
            try:
                n = int(str(param.name).strip())
                max_num = max(max_num, n)
            except ValueError:
                pass
        new_num = max_num + 1
        tmpl.add(str(new_num), ref)
        new_wikitext = str(code)
        return {
            "action": "append",
            "detail": f"Appended as param #{new_num} to existing {{{{refideas}}}} (had {max_num} params)",
            "wikitext": new_wikitext,
            "summary": f"/* Reference suggestion */ Added {label} to existing reference suggestions",
        }
    else:
        # Insert new Refideas block before first == heading
        refideas_block = f"\n{{{{refideas\n| 1 = {ref}\n}}}}\n"
        headings = code.filter_headings()
        if headings:
            first_heading_text = str(headings[0].title).strip()
            escaped = re.escape(first_heading_text)
            # Match heading at start of line (or start of page)
            pattern = rf"(?:^|\n)==\s*{escaped}\s*=="
            m = re.search(pattern, wikitext, re.MULTILINE)
            if m:
                insert_pos = m.start()
                if insert_pos == 0:
                    # Heading at very start of page — no leading newline needed
                    new_wikitext = refideas_block.lstrip('\n') + wikitext
                else:
                    new_wikitext = (
                        wikitext[:insert_pos] + refideas_block + wikitext[insert_pos:]
                    )
                return {
                    "action": "insert",
                    "detail": f"Inserted new {{{{refideas}}}} block before == {first_heading_text} ==",
                    "wikitext": new_wikitext,
                    "summary": f"/* Reference suggestion */ Suggested {label} as a resource",
                }
        # Fallback: no headings or couldn't locate — append at end
        new_wikitext = wikitext + refideas_block
        return {
            "action": "append_end",
            "detail": "No sections found — appended new {{refideas}} block at end of page",
            "wikitext": new_wikitext,
            "summary": f"/* Reference suggestion */ Suggested {label} as a resource",
        }


def refideas_add(
    article_title: str,
    url: str,
    label: str,
    source: str = "",
    note: str = "",
) -> dict:
    """
    Add a reference to a Wikipedia Talk page's {{refideas}} template.

    Orchestrator: fetches the current Talk page wikitext via the API,
    runs dedup, then delegates to build_refideas_wikitext() for the
    pure wikitext manipulation.

    Generic — works for any reference, not just OCW.

    Returns:
        {"action": str, "detail": str, "wikitext": str, "summary": str,
         "skipped": bool, "reason": str}
    """
    import urllib.request
    import urllib.parse
    import json

    UA = "MIT OCW Bot/1.0 (https://meta.wikimedia.org/wiki/Wiki_MIT; andrew.lih@gmail.com) ContentGapResearch"

    encoded = urllib.parse.quote(urllib.parse.unquote(article_title).replace(" ", "_"), safe="")
    api_url = (
        f"https://en.wikipedia.org/w/api.php"
        f"?action=parse&page=Talk:{encoded}"
        f"&prop=wikitext&format=json&formatversion=2"
    )
    req = urllib.request.Request(api_url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
        wikitext = data["parse"]["wikitext"]

    # Dedup: check if URL already appears on the Talk page
    if url in wikitext:
        return {
            "action": "skip",
            "detail": "URL already present on Talk page — skipping",
            "wikitext": wikitext,
            "summary": "",
            "skipped": True,
            "reason": "duplicate_url",
        }

    result = build_refideas_wikitext(wikitext, url, label, source, note)
    result["skipped"] = False
    result["reason"] = ""
    return result


def l1_insert_refideas(
    article_title: str,
    course_id: str,
    course_title: str,
    course_url: str,
    note: str = "",
) -> dict:
    """
    OCW-specific wrapper around refideas_add().

    Formats the reference as:
        [course_url MIT course_id: course_title], MIT OpenCourseWare (note)
    """
    return refideas_add(
        article_title=article_title,
        url=course_url,
        label=f"MIT {course_id}: {course_title}",
        source="MIT OpenCourseWare",
        note=note,
    )


# ─── Example Records (from real project data) ───────────────────────────────

def get_examples() -> List[ContributionRecord]:
    """Return example records built from real project data."""
    return [
        # L1 — Talk page Refideas: Electron configuration + MIT 5.111SC
        make_l1(
            article_title="Electron configuration",
            course_id="5.111SC",
            course_title="Principles of Chemical Science",
            course_url="https://ocw.mit.edu/courses/5-111sc-principles-of-chemical-science-fall-2014/",
            lecture_title="Lecture 7: Multi-electron Atoms",
            lecture_url="https://ocw.mit.edu/courses/5-111sc-principles-of-chemical-science-fall-2014/pages/unit-i-the-atom/lecture-7/",
            resource_type="video",
            wikiproject="Chemistry",
            quality="Start",
            importance="High",
            views=42000,
            score=79,
            note="video lecture, lecture notes, and problem set with solutions",
        ),

        # L2 — External link: Algorithm + MIT 6.006
        make_l2(
            article_title="Algorithm",
            course_id="6.006",
            course_title="Introduction to Algorithms",
            course_url="https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/",
            wikiproject="Computer Science",
            quality="C",
            importance="Top",
            views=180000,
            score=85,
            description="Full course with video lectures, problem sets, and exams covering algorithm design and analysis.",
        ),

        # L3 — Replace Citation needed: Nuclear weapon + MIT 22.01
        make_l3(
            article_title="Nuclear weapon",
            course_id="22.01",
            course_title="Introduction to Nuclear Engineering and Ionizing Radiation",
            course_url="https://ocw.mit.edu/courses/22-01-introduction-to-nuclear-engineering-and-ionizing-radiation-fall-2016/",
            lecture_title="Lecture 15: Nuclear Reactions",
            lecture_url="https://ocw.mit.edu/courses/22-01-introduction-to-nuclear-engineering-and-ionizing-radiation-fall-2016/pages/lecture-15/",
            resource_type="video",
            wikiproject="Environment",
            quality="C",
            importance="High",
            views=95651,
            score=87,
            template_name="Citation needed",
            template_section="Weapons delivery",
            template_date="March 2024",
            template_context="The first nuclear weapons were gravity bombs, dropped from aircraft.{{Citation needed|date=March 2024}} In the decades since...",
            context_before="The first nuclear weapons were gravity bombs, dropped from aircraft.",
            context_after="In the decades since, warheads have been developed for delivery by missiles, torpedoes, and artillery.",
        ),

        # L4 — Fill Missing information: Electron configuration + MIT 5.111SC
        make_l4(
            article_title="Electron configuration",
            course_id="5.111SC",
            course_title="Principles of Chemical Science",
            course_url="https://ocw.mit.edu/courses/5-111sc-principles-of-chemical-science-fall-2014/",
            lecture_title="Lecture 7: Multi-electron Atoms",
            lecture_url="https://ocw.mit.edu/courses/5-111sc-principles-of-chemical-science-fall-2014/pages/unit-i-the-atom/lecture-7/",
            resource_type="lecture_notes",
            wikiproject="Chemistry",
            quality="Start",
            importance="High",
            views=42000,
            score=79,
            template_section="Aufbau principle",
            missing_topic="explanation of energy ordering in multi-electron atoms",
            content_summary=(
                "In multi-electron atoms, the energy of an orbital depends on both "
                "the principal quantum number n and the angular momentum quantum number l. "
                "For a given n, orbital energy increases with l (s < p < d < f). "
                "This explains why the 4s orbital fills before 3d — the 4s orbital has "
                "lower energy than 3d for potassium and calcium, though this ordering "
                "shifts for transition metals."
            ),
            context_before="The Aufbau principle takes its name from the German word Aufbauprinzip, meaning 'building-up principle'.",
            context_after="The principle takes its name from the German word Aufbauprinzip...",
        ),

        # L5 — New section: Machine learning + MIT 6.867
        make_l5(
            article_title="Machine learning",
            course_id="6.867",
            course_title="Machine Learning",
            course_url="https://ocw.mit.edu/courses/6-867-machine-learning-fall-2006/",
            wikiproject="Computer Science",
            quality="C",
            importance="Top",
            views=250000,
            score=85,
            section_title="Bayesian approaches to machine learning",
            body=(
                "Bayesian methods provide a principled framework for reasoning under "
                "uncertainty in machine learning. Key concepts include prior distributions "
                "over model parameters, likelihood functions for observed data, and "
                "posterior inference via Bayes' theorem. These approaches naturally handle "
                "model selection through marginal likelihoods and provide uncertainty "
                "estimates alongside predictions.\n\n"
                "Applications include Gaussian processes for regression, Bayesian neural "
                "networks, and probabilistic graphical models for structured prediction."
            ),
            position="after:== Models ==",
        ),
    ]


# ─── CLI ────────────────────────────────────────────────────────────────────

def cmd_validate():
    examples = get_examples()
    all_ok = True
    for rec in examples:
        errors = rec.validate()
        if errors:
            all_ok = False
            print(f"❌ {rec.id}:")
            for e in errors:
                print(f"   - {e}")
        else:
            print(f"✅ {rec.id} ({rec.level.value}) — valid")
    if all_ok:
        print("\nAll records valid.")
    else:
        print(f"\n{sum(1 for r in examples if r.validate())} errors found.")
        sys.exit(1)

def cmd_examples():
    examples = get_examples()
    output = [r.to_dict() for r in examples]
    print(json.dumps(output, indent=2))

def cmd_wikitext():
    examples = get_examples()
    for rec in examples:
        print(f"{'─'*60}")
        print(f"  {rec.id}  ({rec.level.value})")
        print(f"  Target: {rec.article.title} ({rec.article.quality}, {rec.article.views:,} views)")
        print(f"  Source: MIT {rec.source.course_id} — {rec.source.course_title}")
        print(f"  Edit summary: {rec.action.edit_summary}")
        print(f"  {'─'*56}")
        print(rec.action.wikitext)
        print()

def cmd_generate():
    """Generate records from live-data.js (stub — requires crossref match data)."""
    print("Generate mode requires crossref match data not yet available.")
    print("Run validation on the example records to test the protocol:")
    print("  python3 scripts/contribution-protocol.py --validate")
    sys.exit(0)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "--validate":
        cmd_validate()
    elif cmd == "--examples":
        cmd_examples()
    elif cmd == "--wikitext":
        cmd_wikitext()
    elif cmd == "--generate":
        cmd_generate()
    elif cmd == "--l1-test":
        # Dry-run L1 insertion on a test article
        article = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "Geothermal energy"
        result = l1_insert_refideas(
            article, "5.111SC", "Principles of Chemical Science",
            "https://ocw.mit.edu/courses/5-111sc-principles-of-chemical-science-fall-2014/",
            "test insertion"
        )
        print(f"Article: {article}")
        print(f"Action: {result['action']}")
        print(f"Detail: {result['detail']}")
        print(f"Summary: {result['summary']}")
        print(f"\nWikitext length: {len(result['wikitext'])} bytes")
        # Show the refideas block
        import mwparserfromhell
        code = mwparserfromhell.parse(result['wikitext'])
        refs = code.filter_templates(
            matches=lambda t: str(t.name).lower().strip() == 'refideas'
        )
        if refs:
            print(f"\nRefideas params:")
            for p in refs[0].params:
                try:
                    int(str(p.name).strip())
                    v = str(p.value).strip()
                    print(f"  [{p.name.strip()}] {v[:100]}{'...' if len(v) > 100 else ''}")
                except ValueError:
                    pass
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)
