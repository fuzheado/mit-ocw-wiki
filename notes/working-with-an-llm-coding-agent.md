# Working with an LLM Coding Agent on Wikimedia Projects

## Project Context

This document describes how the Wiki MIT project was built — not by a
developer writing code from a spec, but by a human Wikipedia editor
collaborating with an LLM coding agent over many sessions. The project's
goal: connect MIT OpenCourseWare's 2,577 open-licensed courses to Wikipedia
articles that need improvement, using WikiProject data (pageviews, quality
ratings, maintenance templates) to surface high-impact editing opportunities.
The tools produced include a D3.js bubble scatterplot (Contribution Impact
Matrix) and a cross-reference heatmap between OCW departments and Wikipedia
WikiProjects. The project is primarily **Python** (data generation, SQL
queries, wikitext parsing, API orchestration) with **vanilla JavaScript +
D3.js** for the browser visualization — no frameworks, no build step.

The agent used was **OpenCode CLI** running **DeepSeek V4 Flash**. All
sessions combined consumed no more than **USD $10** in API costs (May 2026).
This extremely low cost — a few dollars for what would have been weeks of
human developer time — is itself a notable data point about the current
economics of LLM-assisted software development.

The collaboration spanned roughly a dozen sessions over several days, each
session an open-ended conversation rather than a written specification. I
would describe what I wanted in plain language — "make the bubble color
reflect how many maintenance templates are on the page" — and the agent would
propose code, I'd review the result, and we'd iterate. No tickets, no PR
reviews, no formal requirements documents. The agent retained context across
sessions via project files (continuation documents, checkpoint files),
meaning it could pick up where it left off without re-explaining the
architecture. This fluidity — the ability to try an idea, see it fail, and
redirect in minutes — is the core advantage over traditional development.
And it required no specialized training or fine-tuning of the model; a
general-purpose LLM with internet-era knowledge of Python, D3.js, and SQL
was sufficient.

## What This Document Is

A retrospective on how this project was actually built — not as a linear
spec-to-implementation pipeline, but as a human–LLM collaboration that
required both sides to bring different strengths. If you're reading this
to understand whether a coding agent could replicate this work, the answer
is: not alone, and not in one shot.

---

## The Division of Labor

### What the Human Did

**Set the vision.** The core idea — connect MIT OCW courseware to Wikipedia
article gaps using WikiProjects as the organizing structure — came from years
of Wikipedia editing experience. The agent had no way to know which signals
mattered (pageviews, quality, importance, templates) or that WikiProjects
were the right unit of analysis.

**Pointed to obscure but essential tools.** Three examples:

- **`mwparserfromhell`** — The agent initially tried regex-based wikitext
  parsing, which broke on edge cases. I knew about mwparserfromhell because
  it's the de-facto wikitext parser in the Python ecosystem, born from years
  of frustration with MediaWiki's irregular, evolved-over-decades markup. The
  name itself ("from hell") is a inside joke about how hard wikitext is to
  parse. The agent didn't know this existed.

- **Community Tech bot Popular pages** — When the agent hit rate limits on
  the Wikimedia pageview REST API and found that the analytics database
  (`enwiki_p`) had zero pageview data, I pointed to the Community Tech bot's
  pre-compiled Popular pages tables. This bot has been quietly generating
  monthly popularity rankings for ~900 WikiProjects for years, but it's not
  well-known outside the WikiProject maintenance community. This single tip
  turned 1,000+ API calls per project into 1.

- **WikiProject Vital Articles taxonomy** — The agent's initial attempt at
  categorizing 942 WikiProjects into domains was ad-hoc keyword matching
  that left 334 projects uncategorized. I pointed to Wikipedia's own Vital
  Articles hierarchy, which has decades of editorial consensus behind it.
  This gave the taxonomy legitimacy and structure that keyword rules never
  could.

**Handled infrastructure that requires a real human identity.** The agent
could not create a Wikimedia developer account, set up SSH keys, or sign up
for Toolforge. These are gated by human identity and manual approval
processes. The SSH tunnel to `enwiki_p` — the analytics database replica —
required a human to:

1. Create a Wikimedia developer account
2. Set up SSH authentication with Toolforge
3. Manually establish the tunnel (`ssh -L 3306:enwiki.analytics.db.svc.wikimedia.cloud:3306`)
4. Keep the tunnel alive during data generation

**Made judgment calls.** When the data generation pipeline hit 942 projects
with Popular pages, the agent proposed several architectural options. I chose
Option 2 (per-project files + manifest) over the alternatives, and made the
pragmatic decision to elevate certain categories (Transportation, Sports,
Business) to top-level in the taxonomy even where the Vital hierarchy kept
them nested. These are editorial decisions rooted in understanding what
Wikipedia editors actually look for.

**Edited the README iteratively.** The README went through ~10 revisions in
conversation — each one responding to "this part is confusing" or "this doesn't
set the right expectations." An agent can draft, but it can't know what a
newcomer will find confusing until a human reads it.

### What the Agent Did

**Turned hypotheses into working code, fast.** The core visualization went from
idea to working standalone HTML in a single session. The agent built the
scatterplot, detail panel, filters, table view, slider, color scale, and
interactions without being told the specifics of D3.js usage — it already knew
the library.

**Discovered and documented constraints through experimentation.** The agent
tried three approaches to get pageview data before the Popular pages solution:
SQL on `page_props.pageview_daily_average` (0 rows), the Wikimedia REST API
monthly endpoint (rate limited at ~15 req/min before UA fix), and the REST API
daily endpoint. Each attempt was logged, and the failures informed the final
design decision. A human doing this alone would have spent days on each dead
end.

**Handled the complexity of real-world data.** Wikipedia articles have
en-dashes, HTML entities, URL-encoded characters, malformed wikitext, and
templates that appear in duplicate due to mwparserfromhell's recursive
traversal. The agent found and fixed each edge case as it appeared — the
template deduplication by text position, the `<ref>` containment detection
using last-unmatched check, the plural-form word boundary issue in
classification. These are exactly the kind of details that a spec document
would miss and that emerge only when you run the code against real data.

**Generated the taxonomy programmatically.** 942 WikiProjects classified into
15 domains with zero uncategorized, using whole-word keyword matching and
exclusion rules. The agent iterated on the classification, fixed false
positives, and documented every edge case in the decision log. Doing this by
hand would have taken days.

**Tested scalability without building the full system.** Before implementing
the per-project manifest architecture, the agent analyzed data size scaling,
generation time, and versioning gaps — showing that the single-file approach
breaks around 50-80 projects. This analysis happened in minutes, not days.

**Used a real browser to test interactive visuals.** The Contribution Impact
Matrix is a D3.js visualization that responds to clicks, hovers, filters, and
sliders — none of which can be verified by reading code alone. The agent used
**Playwright** (a browser automation tool) to open the standalone HTML file
from `file://`, take screenshots at each iteration, click on bubbles to
verify the detail panel slid out, type in the search box, toggle filters,
and check the browser console for JavaScript errors. This was essential for a
project with zero automated test suite — the browser was the test harness.
Without this capability, every visual bug would have required me to open the
file, reproduce the issue, and describe it back to the agent. With Playwright,
the agent could see what it built and self-correct.

**Created reusable skills.** Competencies like Wikimedia database access,
page assessment queries, and pageview retrieval were isolated into Claude
skill files (`.claude/skills/`). These are standalone markdown documents that
any Claude Code session can discover and use, meaning the agent won't have to
re-derive the SSH tunnel setup or the Popular pages parsing logic from scratch
next time.

---

## Key Insights for Future Projects

### 1. The Human–LLM Partnership Is Asymmetric

The human provides: domain expertise, infrastructure access, editorial
judgment, tool discovery, and reality checks on what users actually need.
The LLM provides: rapid prototyping, constraint discovery through
experimentation, edge-case handling at scale, and the ability to grind
through thousands of items without fatigue.

Neither can replace the other. A human alone would take weeks to build
the visualization, discover all the edge cases, and classify 942 projects.
An LLM alone would produce something technically functional but misaligned
with how Wikipedia editors actually work.

### 2. The Most Valuable Human Input Is Domain Knowledge

The single highest-leverage contributions from the human side were not code
reviews or architecture decisions — they were pointers to obscure but
essential tools and data sources. `mwparserfromhell`, the Community Tech
bot's Popular pages, the Vital Articles taxonomy — none of these appear in
the top results of a web search for "Wikipedia data tools." They live in
the tacit knowledge of experienced Wikipedia editors.

If you're a domain expert working with an LLM, your most productive
contribution is: "Try using this tool/library/dataset instead." The agent
will figure out the technical details.

### 3. The Process Is Iterative, Not Linear

This project went through:

1. **Data exploration** — what's available in `enwiki_p`? Answer: templates,
   assessments, metadata. NOT pageviews.
2. **Data source discovery** — Popular pages instead of pageview API.
3. **Architecture prototyping** — single file → per-project files + manifest.
4. **Taxonomy development** — ad-hoc → keyword → Vital Articles → pragmatic
   elevation. Five iterations.
5. **UIDesign** — dropdown → command palette → two-column browser. Three
   iterations, still in progress.
6. **Documentation** — ~10 README revisions.

Each stage unearthed new constraints that changed the approach. The agent
could keep the full context of these iterations; a human would need to
re-discover them through documentation.

### 4. Skills Work, But They Need Active Maintenance

The `.claude/skills/` directory isolates competencies into files that
Claude Code auto-discovers. This is effective for:

- **Reusable procedures** — SSH tunnel setup, SQL query patterns, API call
  templates.
- **Hard-won knowledge** — the `linktarget` migration, the `page_props`
  column naming, the `ifilter_templates` deduplication bug.
- **Compliance** — User-Agent strings, rate-limit best practices.

However, skills are static documents. They don't update themselves when
Wikimedia's schema changes or when a new API endpoint becomes available.
They need periodic human review to stay current.

For non-Claude agents (Codex, Copilot, OpenCode), skills are just markdown
files that the human can point the agent to. The pattern works but requires
the human to know the skill exists and tell the agent to read it.

### 5. The "One-Shot" Myth

The most important takeaway: **this project could not have been built in a
single prompt or even a single session.** The architecture, data sources,
taxonomy, and visual design each required multiple rounds of
proposal—testing—feedback—revision. Any demo that claims to produce a
working Contribution Impact Matrix from a single prompt is either
cherry-picking a trivial subset or hiding the human work that happened
before the prompt was written.

The value of the LLM agent was not that it could build everything at once —
it was that it could move fast through the implementation details once the
human pointed in the right direction, and could absorb feedback across
dozens of iterations without losing context.

---

## Suggested Citation

If referencing this collaboration pattern in academic or project
documentation:

> The technical implementation — data pipeline, visualization, classification
> — was built by an LLM coding agent (Claude Code / OpenCode) guided by a
> human domain expert who set the strategic direction, identified key tools
> and data sources, and made editorial decisions about the taxonomy and user
> experience. The work required approximately [N] sessions over [M] days,
> with each session involving multiple rounds of proposal and revision.

---

*Documented May 2026. Project: Wiki MIT — Contribution Impact Matrix and
OCW-Wikipedia Cross-Linking.*
