# Contribution Protocol

> **Purpose:** Define the data structure for a "unit of contribution" — the atomic record that flows from identification (Impact Matrix) through matching (matchmaker) to execution (work queue / editing interface).
>
> This protocol is designed *before* the contribution interface so we can validate that each contribution type has the right fields, generates correct wikitext, and can be serialized to a work queue.

---

## Design Principles

1. **One record, one edit.** Each ContributionRecord maps to exactly one Wikipedia edit action (one talk page post, one citation replacement, one section addition). No multi-step records.
2. **Self-contained.** Every field needed to execute the edit is in the record. The work queue never needs to look up additional data.
3. **Serializable.** Records survive across sessions. JSON-serializable, hashable by (type, article, resource) for deduplication.
4. **Pre-formatted wikitext.** Every record includes a `wikitext` field that is the exact text to insert. For L3-L5, this is what the editor sees pre-populated.
5. **Status-tracked.** Records have a lifecycle: pending → in_review → applied → rejected. This enables incremental progress across sessions.

---

## The ContributionRecord

### Common fields (all levels)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | ✅ | Unique ID, e.g. `"L3-nuclear_weapon-22.01-cn_1"` |
| `level` | enum | ✅ | `L1`, `L2`, `L3`, `L4`, `L5` |
| `status` | enum | ✅ | `pending`, `in_review`, `applied`, `rejected`, `skipped` |
| `score` | float | ✅ | Impact score 0-100 (from crossref scoring model) |
| `created` | ISO8601 | ✅ | When the record was generated |

### Target fields (the Wikipedia article)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `article.title` | string | ✅ | Wikipedia article title (e.g., `"Nuclear weapon"`) |
| `article.url` | string | ✅ | Full Wikipedia URL |
| `article.quality` | string | ✅ | Assessed quality: Stub/Start/C/B/GA/FA |
| `article.importance` | string | ✅ | WikiProject importance: Low/Mid/High/Top |
| `article.views` | int | ✅ | Monthly pageviews |
| `article.wikiproject` | string | ✅ | WikiProject name (e.g., `"Environment"`) |

### Source fields (the OCW resource)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `source.course_id` | string | ✅ | e.g., `"5.111SC"` |
| `source.course_title` | string | ✅ | e.g., `"Principles of Chemical Science"` |
| `source.course_url` | string | ✅ | OCW course page URL |
| `source.lecture_title` | string | L3-L5 | Specific lecture or resource title |
| `source.lecture_url` | string | L3-L5 | Direct URL to the lecture/resource |
| `source.resource_type` | string | ✅ | `video`, `lecture_notes`, `problem_set`, `reading_list` |
| `source.license` | string | ✅ | Always `"CC BY-NC-SA 4.0"` for OCW content |

### Action fields (what to do)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `action.type` | string | ✅ | `talk_page`, `external_link`, `replace_template`, `add_section`, `new_content` |
| `action.target_location` | string | ✅ | Where on the page to edit: section name, or `__TALK__`, `__EXTERNAL_LINKS__`, `__CITATION_TAG__` |
| `action.wikitext` | string | ✅ | Pre-formatted wikitext to insert |
| `action.edit_summary` | string | ✅ | Proposed edit summary for Wikipedia |
| `action.context_before` | string | L3-L5 | The surrounding text (for editor orientation) |
| `action.context_after` | string | L3-L5 | Text after the edit point |

### Review fields (for human oversight)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `review.notes` | string | ❌ | Editor notes |
| `review.applied_at` | ISO8601 | ❌ | When applied to Wikipedia |
| `review.revision_id` | int | ❌ | Wikipedia revision ID after application |

---

## Level-specific schemas

### L1 — Talk page `{{Refideas}}`

**What it is:** A suggestion posted to the article's Talk page. Doesn't modify the article. Safest contribution type.

**Extra fields:** none (all covered by common fields)

**Wikitext template:**
```wikitext
{{Refideas
|1={{cite web |url=<source.course_url> |title=<source.course_title> |publisher=MIT OpenCourseWare}}
|comment=<source.course_id> covers <article.title> topics. <source.resource_type>: <source.lecture_title if present>
}}
```

**Target location:** `__TALK__` (new section on Talk page, or append to existing Refideas section)

---

### L2 — External links / Further reading

**What it is:** Add an OCW course link to the article's "External links" or "Further reading" section.

**Extra fields:**

| Field | Type | Description |
|-------|------|-------------|
| `link.label` | string | Display text for the link |
| `link.description` | string | One-line description of why this course is relevant |

**Wikitext template:**
```wikitext
* {{cite web |url=<source.course_url> |title=<source.course_title> |publisher=MIT OpenCourseWare}} — <link.description>
```

**Target location:** `== External links ==` or `== Further reading ==` (append)

---

### L3 — Replace `{{Citation needed}}`

**What it is:** Replace a `{{Citation needed}}` (or `{{cn}}`, `{{fact}}`) tag with a `{{cite web}}` pointing to a specific OCW resource.

**Extra fields:**

| Field | Type | Description |
|-------|------|-------------|
| `template.name` | string | The template being replaced: `"Citation needed"`, `"Cn"`, `"Fact"` |
| `template.section` | string | Section name where the template appears |
| `template.date` | string | `|date=` parameter from the template (e.g., `"April 2023"`) |
| `template.context` | string | The sentence containing the template |

**Wikitext template:**
```wikitext
<ref>{{cite web |url=<source.lecture_url or course_url> |title=<source.lecture_title or course_title> |publisher=MIT OpenCourseWare |access-date=<today>}}</ref>
```

This is inserted in place of the `{{Citation needed}}` tag within the existing wikitext.

**Target location:** `__CITATION_TAG__` (exact position of the template in wikitext)

---

### L4 — Fill `{{Missing information}}`

**What it is:** Add a paragraph or bullet points filling in the missing information identified by a `{{Missing information}}` template, citing the OCW resource.

**Extra fields:**

| Field | Type | Description |
|-------|------|-------------|
| `template.section` | string | Section where the template appears |
| `template.missing_topic` | string | What the template says is missing (from `|about=` parameter) |
| `content.summary` | string | The OCW-based content to add (1-3 sentences) |
| `content.format` | string | `"paragraph"` or `"bullets"` |

**Wikitext template:**
```wikitext
<content.summary><ref>{{cite web |url=<source.lecture_url> |title=<source.lecture_title> |publisher=MIT OpenCourseWare |access-date=<today>}}</ref>
```

The `{{Missing information}}` template is then removed.

**Target location:** After the `{{Missing information}}` template, before the next paragraph

---

### L5 — New content / section

**What it is:** Propose a new section or substantial new content based on OCW course material. Highest risk — intended as a draft for human review.

**Extra fields:**

| Field | Type | Description |
|-------|------|-------------|
| `content.section_title` | string | Proposed section heading |
| `content.body` | string | Draft wikitext (1-4 paragraphs with citations) |
| `content.position` | string | Where to insert: `"before"`, `"after"` + target section name |

**Wikitext template:**
```wikitext
== <content.section_title> ==

<content.body>

== References ==
{{reflist}}
```

**Target location:** After the specified anchor section

---

## Example records (from real project data)

### L1 Example — Talk page Refideas

```json
{
  "id": "L1-electron_configuration-5.111SC",
  "level": "L1",
  "status": "pending",
  "score": 79,
  "created": "2026-05-25T00:00:00Z",
  "article": {
    "title": "Electron configuration",
    "url": "https://en.wikipedia.org/wiki/Electron_configuration",
    "quality": "Start",
    "importance": "High",
    "views": 42000,
    "wikiproject": "Chemistry"
  },
  "source": {
    "course_id": "5.111SC",
    "course_title": "Principles of Chemical Science",
    "course_url": "https://ocw.mit.edu/courses/5-111sc-principles-of-chemical-science-fall-2014/",
    "lecture_title": "Lecture 7: Multi-electron Atoms",
    "lecture_url": "https://ocw.mit.edu/courses/5-111sc-principles-of-chemical-science-fall-2014/pages/unit-i-the-atom/lecture-7/",
    "resource_type": "video",
    "license": "CC BY-NC-SA 4.0"
  },
  "action": {
    "type": "talk_page",
    "target_location": "__TALK__",
    "wikitext": "{{Refideas\n|1={{cite web |url=https://ocw.mit.edu/courses/5-111sc-principles-of-chemical-science-fall-2014/ |title=Principles of Chemical Science |publisher=MIT OpenCourseWare}}\n|comment=MIT 5.111SC covers electron configuration and multi-electron atoms in detail. Lecture 7 has a video lecture, lecture notes, and problem set with solutions.\n}}",
    "edit_summary": "/* OCW reference suggestion */ Suggested MIT 5.111SC as a resource for electron configuration via Wiki MIT"
  }
}
```

### L2 Example — External link

```json
{
  "id": "L2-algorithm-6.006",
  "level": "L2",
  "status": "pending",
  "score": 85,
  "created": "2026-05-25T00:00:00Z",
  "article": {
    "title": "Algorithm",
    "url": "https://en.wikipedia.org/wiki/Algorithm",
    "quality": "C",
    "importance": "Top",
    "views": 180000,
    "wikiproject": "Computer Science"
  },
  "source": {
    "course_id": "6.006",
    "course_title": "Introduction to Algorithms",
    "course_url": "https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/",
    "lecture_title": null,
    "lecture_url": null,
    "resource_type": "reading_list",
    "license": "CC BY-NC-SA 4.0"
  },
  "action": {
    "type": "external_link",
    "target_location": "__EXTERNAL_LINKS__",
    "wikitext": "* {{cite web |url=https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/ |title=Introduction to Algorithms |publisher=MIT OpenCourseWare}} — Full course with video lectures, problem sets, and exams covering algorithm design and analysis.",
    "edit_summary": "/* External links */ Added MIT 6.006 as an educational resource via Wiki MIT"
  },
  "link": {
    "label": "MIT 6.006: Introduction to Algorithms",
    "description": "Full course with video lectures, problem sets, and exams covering algorithm design and analysis."
  }
}
```

### L3 Example — Replace Citation needed

```json
{
  "id": "L3-nuclear_weapon-22.01-cn_1",
  "level": "L3",
  "status": "pending",
  "score": 87,
  "created": "2026-05-25T00:00:00Z",
  "article": {
    "title": "Nuclear weapon",
    "url": "https://en.wikipedia.org/wiki/Nuclear_weapon",
    "quality": "C",
    "importance": "High",
    "views": 95651,
    "wikiproject": "Environment"
  },
  "source": {
    "course_id": "22.01",
    "course_title": "Introduction to Nuclear Engineering and Ionizing Radiation",
    "course_url": "https://ocw.mit.edu/courses/22-01-introduction-to-nuclear-engineering-and-ionizing-radiation-fall-2016/",
    "lecture_title": "Lecture 15: Nuclear Reactions",
    "lecture_url": "https://ocw.mit.edu/courses/22-01-introduction-to-nuclear-engineering-and-ionizing-radiation-fall-2016/pages/lecture-15/",
    "resource_type": "video",
    "license": "CC BY-NC-SA 4.0"
  },
  "action": {
    "type": "replace_template",
    "target_location": "__CITATION_TAG__",
    "wikitext": "<ref>{{cite web |url=https://ocw.mit.edu/courses/22-01-introduction-to-nuclear-engineering-and-ionizing-radiation-fall-2016/pages/lecture-15/ |title=Lecture 15: Nuclear Reactions (22.01 Introduction to Nuclear Engineering) |publisher=MIT OpenCourseWare |access-date=2026-05-25}}</ref>",
    "edit_summary": "/* Citation */ Added citation from MIT 22.01 for nuclear reaction claim via Wiki MIT",
    "context_before": "The first nuclear weapons were gravity bombs, dropped from aircraft.",
    "context_after": "In the decades since, warheads have been developed for delivery by missiles, torpedoes, and artillery."
  },
  "template": {
    "name": "Citation needed",
    "section": "Weapons delivery",
    "date": "March 2024",
    "context": "The first nuclear weapons were gravity bombs, dropped from aircraft.{{Citation needed|date=March 2024}} In the decades since..."
  }
}
```

### L4 Example — Fill Missing information

```json
{
  "id": "L4-electron_configuration-5.111SC-missing",
  "level": "L4",
  "status": "pending",
  "score": 79,
  "created": "2026-05-25T00:00:00Z",
  "article": {
    "title": "Electron configuration",
    "url": "https://en.wikipedia.org/wiki/Electron_configuration",
    "quality": "Start",
    "importance": "High",
    "views": 42000,
    "wikiproject": "Chemistry"
  },
  "source": {
    "course_id": "5.111SC",
    "course_title": "Principles of Chemical Science",
    "course_url": "https://ocw.mit.edu/courses/5-111sc-principles-of-chemical-science-fall-2014/",
    "lecture_title": "Lecture 7: Multi-electron Atoms",
    "lecture_url": "https://ocw.mit.edu/courses/5-111sc-principles-of-chemical-science-fall-2014/pages/unit-i-the-atom/lecture-7/",
    "resource_type": "lecture_notes",
    "license": "CC BY-NC-SA 4.0"
  },
  "action": {
    "type": "add_section",
    "target_location": "Aufbau principle",
    "wikitext": "In multi-electron atoms, the energy of an orbital depends on both the principal quantum number n and the angular momentum quantum number l. For a given n, orbital energy increases with l (s < p < d < f). This explains why the 4s orbital fills before 3d — the 4s orbital has lower energy than 3d for potassium and calcium, though this ordering shifts for transition metals.<ref>{{cite web |url=https://ocw.mit.edu/courses/5-111sc-principles-of-chemical-science-fall-2014/pages/unit-i-the-atom/lecture-7/ |title=Lecture 7: Multi-electron Atoms (5.111SC Principles of Chemical Science) |publisher=MIT OpenCourseWare |access-date=2026-05-25}}</ref>",
    "edit_summary": "/* Aufbau principle */ Added explanation of orbital energy ordering in multi-electron atoms, citing MIT 5.111SC via Wiki MIT",
    "context_before": "The Aufbau principle takes its name from the German word Aufbauprinzip, meaning 'building-up principle'.",
    "context_after": "The principle takes its name from the German word Aufbauprinzip..."
  },
  "template": {
    "section": "Aufbau principle",
    "missing_topic": "explanation of energy ordering in multi-electron atoms"
  },
  "content": {
    "summary": "In multi-electron atoms, the energy of an orbital depends on both the principal quantum number n and the angular momentum quantum number l. For a given n, orbital energy increases with l (s < p < d < f). This explains why the 4s orbital fills before 3d...",
    "format": "paragraph"
  }
}
```

### L5 Example — New section draft

```json
{
  "id": "L5-machine_learning-6.867-new",
  "level": "L5",
  "status": "pending",
  "score": 85,
  "created": "2026-05-25T00:00:00Z",
  "article": {
    "title": "Machine learning",
    "url": "https://en.wikipedia.org/wiki/Machine_learning",
    "quality": "C",
    "importance": "Top",
    "views": 250000,
    "wikiproject": "Computer Science"
  },
  "source": {
    "course_id": "6.867",
    "course_title": "Machine Learning",
    "course_url": "https://ocw.mit.edu/courses/6-867-machine-learning-fall-2006/",
    "lecture_title": null,
    "lecture_url": null,
    "resource_type": "reading_list",
    "license": "CC BY-NC-SA 4.0"
  },
  "action": {
    "type": "new_content",
    "target_location": "after:== Models ==",
    "wikitext": "== Bayesian approaches to machine learning ==\n\nBayesian methods provide a principled framework for reasoning under uncertainty in machine learning. Key concepts include prior distributions over model parameters, likelihood functions for observed data, and posterior inference via Bayes' theorem. These approaches naturally handle model selection through marginal likelihoods and provide uncertainty estimates alongside predictions.\n\nApplications include Gaussian processes for regression, Bayesian neural networks, and probabilistic graphical models for structured prediction.<ref>{{cite web |url=https://ocw.mit.edu/courses/6-867-machine-learning-fall-2006/ |title=Machine Learning |publisher=MIT OpenCourseWare |access-date=2026-05-25}}</ref>",
    "edit_summary": "/* Bayesian approaches */ Added section on Bayesian methods in machine learning, citing MIT 6.867 via Wiki MIT",
    "context_before": "== Models ==\n\nMachine learning models can be categorized into...",
    "context_after": "== Applications ==\n\nMachine learning has been applied to..."
  },
  "content": {
    "section_title": "Bayesian approaches to machine learning",
    "body": "Bayesian methods provide a principled framework for reasoning under uncertainty in machine learning...",
    "position": "after:== Models =="
  }
}
```

---

## Work Queue Schema

A work queue is a list of ContributionRecords, filterable and sortable:

```json
{
  "version": 1,
  "generated": "2026-05-25T00:00:00Z",
  "total_pending": 57,
  "items": [ ...ContributionRecord... ]
}
```

**Filter dimensions:**
- `level` — L1 through L5
- `article.wikiproject` — WikiProject name
- `article.quality` — quality class
- `status` — pending, in_review, applied, rejected
- `score` — minimum threshold
- `source.resource_type` — video, lecture_notes, etc.

**Sort options:**
- Score descending (default — highest impact first)
- Views descending
- Quality ascending (worst quality first)

---

## Validation Rules

1. **L1:** `action.type` must be `"talk_page"`. `wikitext` must contain `{{Refideas}}`.
2. **L2:** `action.type` must be `"external_link"`. `link.label` and `link.description` required.
3. **L3:** `action.type` must be `"replace_template"`. `template.name`, `template.section`, `template.context` required. `wikitext` must contain `<ref>`.
4. **L4:** `action.type` must be `"add_section"`. `template.missing_topic` and `content.summary` required.
5. **L5:** `action.type` must be `"new_content"`. `content.section_title`, `content.body`, and `content.position` required.
6. **All:** `source.course_url` must be a valid `ocw.mit.edu` URL. `source.license` must be `"CC BY-NC-SA 4.0"`. `article.title` must be non-empty. `score` must be 0-100.
