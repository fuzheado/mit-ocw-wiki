# Detail Panel: Content Spec

What shows in the slide-out panel when a user clicks a bubble.

## Layout

```
┌──────────────────────────────────────────┐
│  Article title              [× close]     │
├──────────────────────────────────────────┤
│                                           │
│  Global context (top section)             │
│  ────────────────────────────────         │
│  Short description: "Annual event..."     │
│  Quality: C  → B   (next class up)       │
│  Last edit: 2026-04-15  |  Size: 45 KB   │
│                                           │
│  Maintenance templates (one each)         │
│  ────────────────────────────────         │
│                                           │
│  [1] {{Citation needed}}                  │
│      Tagged: April 2026                   │
│      Section: "History"                   │
│      Possible context:                    │
│        "The first Earth Day was          │
│         organized by Gaylord Nelson..."   │
│        ⚠ This is a best guess — verify   │
│          against the article source.      │
│      ⚠ This tag may be in a table,       │
│        infobox, or list — section         │
│        context is shown above.            │
│                                           │
│  [2] {{Unreferenced section}}             │
│      Tagged: May 2023                     │
│      Section: "Criticism"                 │
│      This template applies to an entire   │
│      section (not an inline claim).       │
│                                           │
│  Links                                    │
│  ────────────────────────────────         │
│  📄 Read article     ✏️ Edit page         │
│  🗂 View WikiProject                      │
│                                           │
└──────────────────────────────────────────┘
```

## Data sources

| Field | Source | Method |
|---|---|---|
| Short description | SQL: `page_props WHERE pp_propname = 'wikibase-shortdesc'` | Single batch query for all articles in the current project |
| Quality class, importance | Already in article data | From Popular pages |
| Last edit, page size | SQL: `page.page_touched, page.page_len` | Batch query |
| Template date param | Raw wikitext: mwparserfromhell extracts `{{citation needed\|date=...}}` | One `action=raw` fetch per article (memoized) |
| Section name | Raw wikitext: mwparserfromhell locates template position, walks up to nearest `== Section ==` | Same raw fetch |
| Sentence context | Raw wikitext: grab text from last `\n\n` or sentence boundary before the template node | Same raw fetch |
| Edit link | Constructed: `https://en.wikipedia.org/w/index.php?title={article}&action=edit` | Static |
| Read link | Constructed: `https://en.wikipedia.org/wiki/{article}` | Static |

## Sentence context heuristics

For `{{Citation needed}}` and other inline templates (`{{Cn}}`, `{{Fact}}`):

1. Parse the raw wikitext with mwparserfromhell
2. Walk the parsed tree to find the template node
3. Get the text node immediately preceding the template
4. Extract text from the last paragraph break (`\n\n`) or the last sentence-ending punctuation (`.!?`) before the template, whichever is closer
5. Classify the context:

| Pattern | Label | Display |
|---|---|---|
| Text before template is ≥20 chars and contains words | "Possible context" | Show the extracted text |
| Template is inside `{{Infobox...}}` | "Infobox template" | "This tag is inside an infobox — edit the infobox directly" |
| Template is inside `{|...|}` | "Table template" | "This tag is in a table cell — view the article to locate it" |
| Template is inside `<ref>...</ref>` | "Footnote template" | "This tag was placed inside a reference — check the article" |
| Template is inside `{{Quote...}}` or `<blockquote>` | "Blockquote template" | "This tag is inside a quotation — verify against the original source" |
| Text before template is <20 chars | "Minimal context" | "Little surrounding text found — the tag may be in a list or navigation element" |

6. Always append: "⚠ This is a best guess — verify against the article source."

## Template explanation messages

Each maintenance template gets a short explanation:

| Template | Explanation |
|---|---|
| Citation needed | "Article has one or more unsourced statements. Adding a citation from a reliable source would help readers verify this information." |
| Cn / Fact | Same as Citation needed |
| Refimprove | "Article needs more references to reliable sources for verification." |
| Sources | Same as Refimprove (alias) |
| Primary sources | "Article relies heavily on primary sources. Adding secondary sources (analysis, commentary, review) would strengthen it." |
| Better source needed | "A cited source is of low quality or reliability. A more authoritative source would improve this claim." |
| Technical | "Article may be too technical for a general audience. Adding introductory explanation or simpler analogies would help." |
| Missing information | "Article is missing important information on a specific subtopic." |
| Expand section | "A section of this article needs expansion." |
| Unreferenced section | "A section of this article has no references at all." |
| Image requested | "This article would benefit from an illustration. The talk page has a specific image request." |
| Diagram needed | "This article needs a diagram or schematic." |
| Video requested | "This article would benefit from video content." |

## Implementation notes

**Batch prioritization:**
1. When the project loads, batch-fetch short descriptions and page metadata for ALL visible articles (one SQL query).
2. When a user clicks a specific article, fetch its raw wikitext (one API call, memoized per session).
3. Parse with mwparserfromhell for section names, template params, and sentence context.

**Caching:**
- Wikitext fetches are memoy, cached per article during a session.
- SQL batch results are global, cached per project load.
- Template explanations are static, hardcoded.

## Edge cases

- Article has no short description → omit that line.
- Article has 5+ templates → collapse to "5 maintenance templates" with expand toggle.
- Article has both inline and section templates → show inline first (more actionable).
- Article wikitext fails to parse → fall back to article title + edit link only, note "Could not load article source".
- Template has no date and no section context → show "Date unknown" and "Section unknown" gracefully.
