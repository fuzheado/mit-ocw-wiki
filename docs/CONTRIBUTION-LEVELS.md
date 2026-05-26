# Contribution Levels Reference

> **Status:** L1 fully documented and validated. L2-L5 designed in protocol, processing to be validated.

This document defines the five contribution levels — the atomic edit types that the Wiki MIT system can apply to Wikipedia. Each level is a different kind of Wikipedia edit, ordered from safest (L1) to most involved (L5).

---

## Overview

| Level | What it does | Edits | Risk | Wikipedia action |
|-------|-------------|-------|------|-----------------|
| **L1** | Suggest OCW as a reference | Talk page | Near-zero | Add `{{refideas}}` to article Talk page |
| **L2** | Add OCW course link | Article | Very low | Append to `== External links ==` or `== Further reading ==` |
| **L3** | Replace a `{{Citation needed}}` tag | Article | Low | Swap `{{cn}}` for `<ref>{{cite web}}</ref>` |
| **L4** | Fill a `{{Missing information}}` gap | Article | Medium | Add prose paragraph with `<ref>`, remove template |
| **L5** | Propose new section | Article | High | Add `== Section ==` with referenced content |

---

## L1 — Talk page `{{refideas}}`

**What:** Posts a suggestion to the article's Talk page pointing editors to relevant OCW resources. Does not touch the article.

**Input:**
- Article title
- OCW course ID, title, and URL
- Optional: specific lecture title, note about the resource

**Processing:**
1. Fetch Talk page wikitext (`action=parse&prop=wikitext`)
2. Parse with `mwparserfromhell`
3. If existing `{{refideas}}` found → append new numbered parameter
4. If no existing → insert new block before first `==` heading
5. Post via `action=edit`

**Output wikitext:**
```wikitext
{{refideas
| 1 = [https://ocw.mit.edu/courses/5-111sc-.../ MIT 5.111SC: Principles of Chemical Science], MIT OpenCourseWare (video lecture, lecture notes, and problem set with solutions)
}}
```

**API calls:** 3 (fetch wikitext, get CSRF token, post edit)
**Deduplication:** Check if course URL already appears on Talk page + local JSON log
**Status:** ✅ Algorithm validated on real Talk pages, reference implementation complete
**Docs:** `docs/L1-REFIDEAS.md`

---

## L2 — External links / Further reading

**What:** Adds an OCW course link to the article's `== External links ==` or `== Further reading ==` section.

**Input:**
- Article title
- OCW course ID, title, and URL
- One-sentence description of why the course is relevant

**Processing:**
1. Fetch article wikitext (`action=parse&prop=wikitext`)
2. Parse with `mwparserfromhell`
3. Find `== External links ==` section (by heading text match)
4. If found → append bulleted link to that section
5. If no external links section → create one at end of article (before `== References ==` or `== See also ==` if present)
6. Post via `action=edit` with `section` parameter targeting the section

**Output wikitext:**
```wikitext
* {{cite web |url=https://ocw.mit.edu/courses/6-006-.../ |title=Introduction to Algorithms |publisher=MIT OpenCourseWare}} — Full course with video lectures, problem sets, and exams covering algorithm design and analysis.
```

**API calls:** 4 (fetch wikitext, get CSRF token, post edit, verify)
**Deduplication:** Check if course URL already in External links section
**Status:** ⬜ Designed in protocol, processing not yet validated

**Open questions:**
- Should we use `{{cite web}}` or plain `[url Label]` for external links? *(Standard is `{{cite web}}` for external links sections, unlike L1 Refideas)*
- What if the article has no External links section? Create one or append elsewhere?
- Should we check section ordering (External links should come before References per WP:LAYOUT)?
- Some articles use `== Further reading ==` instead of `== External links ==` — which do we target?

---

## L3 — Replace `{{Citation needed}}`

**What:** Replaces a `{{Citation needed}}` (or `{{cn}}`, `{{fact}}`) inline tag with a `<ref>{{cite web}}</ref>` pointing to a specific OCW resource.

**Input:**
- Article title
- OCW course ID, title, and URL
- Specific lecture title and URL (the relevant resource)
- The template being replaced: name, section, date parameter, surrounding context sentence

**Processing:**
1. Fetch article wikitext (`action=parse&prop=wikitext`)
2. Parse with `mwparserfromhell`
3. Find all `{{Citation needed}}` / `{{cn}}` / `{{fact}}` templates
4. Match against the target template (by section + context sentence proximity)
5. Generate `<ref>{{cite web |url=... |title=... |publisher=MIT OpenCourseWare |access-date=...}}</ref>`
6. Replace the template node with the ref node
7. Post full wikitext via `action=edit`

**Output wikitext:**
The existing sentence with `{{Citation needed|date=March 2024}}` becomes:
```wikitext
The first nuclear weapons were gravity bombs, dropped from aircraft.<ref>{{cite web |url=https://ocw.mit.edu/courses/22-01-.../lecture-15/ |title=Lecture 15: Nuclear Reactions (22.01) |publisher=MIT OpenCourseWare |access-date=2026-05-25}}</ref>
```

**API calls:** 3 (fetch wikitext, get CSRF token, post edit)
**Deduplication:** The template itself provides dedup — we're removing it. If it's already been replaced (no `{{cn}}` found), skip.
**Status:** ⬜ Designed in protocol, processing not yet validated

**Open questions:**
- How to reliably match the correct `{{cn}}` when an article has multiple? (By section + context text proximity)
- Should we group multiple `{{cn}}` tags in the same section into one edit?
- Some `{{cn}}` tags are inside `<ref>` blocks — these are footnote-internal and should be skipped
- The OCW license is CC BY-NC-SA 4.0. Citing an NC-licensed work as a reference is standard academic practice but worth noting

---

## L4 — Fill `{{Missing information}}`

**What:** Adds content filling the gap identified by a `{{Missing information}}` template, with a citation to the OCW resource.

**Input:**
- Article title
- OCW course ID, title, and URL
- Specific lecture title and URL
- The missing information topic (from `|about=` parameter)
- Content summary: 1-3 sentences of prose filling the gap
- Section name where the template appears

**Processing:**
1. Fetch article wikitext (`action=parse&prop=wikitext`)
2. Parse with `mwparserfromhell`
3. Find the `{{Missing information}}` template by section
4. Generate a prose paragraph with `<ref>` citation pointing to OCW resource
5. Insert the paragraph after the template
6. Remove the `{{Missing information}}` template
7. Post via `action=edit`

**Output wikitext:**
```wikitext
In multi-electron atoms, the energy of an orbital depends on both the principal quantum number n and the angular momentum quantum number l. For a given n, orbital energy increases with l (s < p < d < f). This explains why the 4s orbital fills before 3d.<ref>{{cite web |url=https://ocw.mit.edu/courses/5-111sc-.../lecture-7/ |title=Lecture 7: Multi-electron Atoms (5.111SC) |publisher=MIT OpenCourseWare |access-date=2026-05-25}}</ref>
```

**API calls:** 3 (fetch wikitext, get CSRF token, post edit)
**Deduplication:** Check if `{{Missing information}}` template still exists on page. If already removed, skip.
**Status:** ⬜ Designed in protocol, processing not yet validated

**Open questions:**
- **This requires content generation.** Unlike L1-L3 which are purely mechanical (copy a URL, swap a tag), L4 needs prose. Where does the prose come from?
  - Option A: Extract from OCW lecture notes / transcripts (scrape + summarize)
  - Option B: LLM generates a factual summary from OCW lecture titles + course description
  - Option C: Human writes it (work queue becomes a draft editor, not an automated system)
- How to verify the generated content is accurate and NPOV?
- Should we remove the `{{Missing information}}` template or just add the content? (Removing without fixing the gap is worse than leaving the tag)

---

## L5 — New section / content

**What:** Proposes a new section for the article based on OCW course material. Highest risk — intended as a draft for human review.

**Input:**
- Article title
- OCW course ID, title, and URL
- Proposed section heading
- Draft body (1-4 paragraphs with citations)
- Insertion position (before/after a specific existing section)

**Processing:**
1. Fetch article wikitext
2. Parse with `mwparserfromhell`
3. Find the target position (before/after specified section)
4. Insert the new section with citations
5. Post via `action=edit`

**Output wikitext:**
```wikitext
== Bayesian approaches to machine learning ==

Bayesian methods provide a principled framework for reasoning under uncertainty in machine learning. Key concepts include prior distributions over model parameters, likelihood functions, and posterior inference via Bayes' theorem.<ref>{{cite web |url=https://ocw.mit.edu/courses/6-867-.../ |title=Machine Learning |publisher=MIT OpenCourseWare |access-date=2026-05-25}}</ref>

Applications include Gaussian processes for regression, Bayesian neural networks, and probabilistic graphical models.
```

**API calls:** 3 (fetch wikitext, get CSRF token, post edit)
**Deduplication:** Check if proposed section heading already exists on page
**Status:** ⬜ Designed in protocol, processing not yet validated

**Open questions:**
- Same content generation problem as L4, amplified — this is entire sections, not single paragraphs
- Should L5 ever be automated? Or always human-drafted with the tool providing the OCW source material?
- Should L5 be a "Draft" mode that creates a user sandbox draft rather than editing the live article?

---

## Processing complexity by level

| Level | Wikitext parsing | Content generation | API calls | Risk of rejection | Automation potential |
|-------|-----------------|-------------------|-----------|-------------------|---------------------|
| **L1** | ✅ Medium (find heading, find existing template) | None (just a URL + label) | 3 | Very low | High |
| **L2** | ✅ Medium (find specific section) | None (URL + description) | 4 | Low | High |
| **L3** | ✅ High (find template in context, precise replacement) | None (URL + ref tags) | 3 | Low-Medium | Medium-High |
| **L4** | ✅ High (find template, insert content, remove template) | **Required** (prose paragraph) | 3 | Medium | Medium |
| **L5** | ✅ Medium (find insertion point) | **Required** (multiple paragraphs) | 3 | High | Low (advisory only) |

The inflection point is between L3 and L4 — that's where the system transitions from "mechanical matching" to "content generation." L1-L3 can be fully automated without an LLM. L4-L5 require generating or surfacing actual prose.

---

## Implementation order

1. **L1 first** — safest, well-understood, establishes the pipeline
2. **L2** — also safe, similar parsing complexity
3. **L3** — the highest-value action (replacing `{{cn}}` tags) but requires precise wikitext surgery
4. **L4** — requires solving the content generation problem
5. **L5** — advisory draft mode, may never be fully automated

The primary user-facing deliverable is a **work queue** that shows L1-L3 items pre-populated with wikitext, plus L4-L5 items as "drafts for review" requiring human content creation before posting.

---

## Reference

| Document | Covers |
|----------|--------|
| `docs/L1-REFIDEAS.md` | L1 algorithm, empirical findings, pitfalls, reference implementation |
| `docs/CONTRIBUTION-PROTOCOL.md` | Full ContributionRecord schema for all levels, validation rules |
| `scripts/contribution-protocol.py` | Python implementation: factories, validation, `l1_insert_refideas()` |
| `docs/ROADMAP.md` | Project roadmap: subsystem integration (Phase 2) and contribution interface (Phase 3) |
