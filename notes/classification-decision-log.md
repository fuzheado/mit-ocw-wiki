# Classification Decision Log

## Purpose

This document records every classification decision made in
`scripts/classify_projects.py` so that future contributors can understand
why a project was placed in a particular domain, and can make informed
decisions about reclassifications.

The taxonomy organizes 942 WikiProjects with Popular pages into 15 domains
for the Contribution Impact Matrix project picker UI.

---

## Architecture

### Classification Engine

The classifier uses keyword-based whole-word matching with exclusion rules.
Each domain rule specifies:

- **keywords**: words or phrases that, if found as whole words (`\b` boundaries)
  in the lowercased project name, trigger a match
- **excludes**: words or phrases that, if also present, suppress the match
  (used to prevent false positives when a keyword appears in a compound term)

Rules are evaluated in **priority order** (top to bottom). The first matching
rule wins. Priority order is:

1.  Geography & Places
2.  Transportation
3.  Sports & Games
4.  Wikipedia Maintenance
5.  Health, Medicine & Biology
6.  Physical Sciences
7.  Mathematics
8.  Technology & Engineering
9.  Business & Economics
10. Society & Social Sciences
11. History
12. Arts & Culture
13. Philosophy & Religion
14. People & Biography
15. Everyday Life & Food

### Why Exact Whole Words?

Whole-word matching (using `\b` / `(?<![a-zA-Z])...(?![a-zA-Z])`) prevents
false positives that pure substring matching would produce:
- `"polo"` in `"anthropology"` (false sports match)
- `"art"` in `"article"` or `"artillery"` (false arts match)
- `"roman"` in `"romania"` (false history match)

The tradeoff is that **plural forms must be added explicitly**:
- `"bird"` does NOT match `"Birds"` (word boundary before 's')
- `"company"` does NOT match `"Companies"` (-ies plural)
- `"film"` does NOT match `"Films"`

This is the single most common cause of missed classifications.

---

## Domain Decisions

### 1. Geography & Places (327 projects)

**Scope**: Countries, US states, cities, regions, continents, islands.

**Inherited from**: Vital Articles Level 4, modified.

**Key exclusion rules**: Terms like "ancient", "medieval", "roman",
"empire", "monarchy" are excluded because they indicate a History topic
that happens to contain a place name (e.g., "Ancient Egypt", "Roman
Empire"). Without exclusions, these would be caught by Geography running
first in priority order.

**Edge cases**:
- "United Kingdom" contains "kingdom" which was initially an exclusion
  term, causing it to fall through. **Decision**: removed "kingdom" from
  Geography exclusions; the country match takes priority.
- "United States" was omitted from the country list (bug). **Decision**:
  added to country list.
- Regions like "East Anglia", "Hudson Valley", "Tamil Nadu", "Wiltshire"
  are not countries but are place-based WikiProjects. **Decision**: listed
  individually.
- "Bangladesh Premier League" matches "bangladesh" in Geography. This is
  technically a cricket league (Sports), but the country match fires first.
  **Decision**: accept as-is; the Geography label is close enough for a
  picker UI. To fix, would need to add "premier league" to Geography
  exclusions.

### 2. Transportation (29 projects)

**Scope**: Aviation, roads, railways, shipping, transit, cycling, automotive.

**Elevated to top-level**: Yes.

**Justification**: Vital Articles buries transport under "Everyday life."
With 29 projects spanning air, road, rail, and sea, this is a coherent
cluster that editors naturally search for at the top level.

**Edge cases**:
- "Spaceflight" and "Aircraft" keywords had to be excluded from
  Transportation (they belong to Physical Sciences and Technology
  respectively). **Decision**: added "spaceflight" and "astronomical" as
  exclusion terms.

### 3. Sports & Games (84 projects)

**Scope**: All sports, board games, video games, esports, gambling.

**Elevated to top-level**: Yes.

**Justification**: Third-largest cluster. Vital buries under "Everyday
life." 84 projects is too large for a subcategory.

**Edge cases**:
- "Athletics" — singular form matched `\bathletic\s`, but "Athletics"
  (the project name) didn't match because of word boundary. **Decision**:
  added "athletics" and "athletics" as explicit keywords.
- "Go" — the board game. `\bgo\b` is too short; could match many things.
  **Decision**: accepted; no false positives observed.

### 4. Wikipedia Maintenance (11 projects)

**Scope**: Wikipedia-internal pages, not encyclopedic content.

**NEW category**: Yes.

**Justification**: Vital Articles has no equivalent — it organizes
articles, not meta-projects. These projects (Abandoned articles, Articles
for creation, Disambiguation, etc.) need a home outside the content
taxonomy.

### 5. Health, Medicine & Biology (86 projects)

**Scope**: Medicine, biology, zoology, botany, veterinary, psychology,
nutrition, specific animal/plant groups.

**Inherited from**: Vital "Biological and health sciences."

**Expanded**: Yes. Absorbs all animal/plant/fungi WikiProjects.

**Edge cases**:
- Animal group names (Birds, Mammals, Dinosaurs, Sharks, Turtles, etc.)
  needed explicit plural forms. **Decision**: added singular AND plural
  for every animal/plant group. This is the most keyword-dense domain.
- "Phasmatodea" (stick insects) — a specific insect order not in the
  original keyword list. **Decision**: added alongside mantodea,
  lepidoptera, etc.
- "Cannabis" — could be Health (medicinal) or Everyday Life (recreational).
  **Decision**: Health, because citation gaps related to medical cannabis
  research are more relevant to this tool.

### 6. Physical Sciences (36 projects)

**Scope**: Physics, astronomy, chemistry, earth sciences, environment,
climate, geology, oceanography.

**Inherited from**: Vital "Physical sciences."

**Expanded**: Yes. Absorbs environment, climate, and miscellaneous
science projects.

**Edge cases**:
- "Environment" — the WikiProject. Could be Earth Sciences or Society.
  **Decision**: Physical Sciences, as the project primarily deals with
  environmental science, not environmental policy.
- "Channel Islands" — place name, caught by Geography. The Physical
  Sciences sample showing "Channel Islands" is actually misclassified in
  the display (it IS under Geography, where it belongs).

### 7. Mathematics (2 projects)

**Scope**: Mathematics, statistics.

**Inherited from**: Vital. No changes.

### 8. Technology & Engineering (32 projects)

**Scope**: Computing, engineering, electronics, software, databases,
systems, open source.

**Inherited from**: Vital "Technology."

**Edge cases**:
- "Open" — the project name. This is about Open Access / Open Source /
  Open Content movements. **Decision**: Technology & Engineering.
- "Systems" — could be Technology or Philosophy (systems theory).
  **Decision**: Technology, as the WikiProject covers computing systems.

### 9. Business & Economics (13 projects)

**Scope**: Economics, finance, companies, trade, marketing, cooperatives.

**Elevated to top-level**: Yes.

**Justification**: Vital buries this under "Society and social
sciences" → "Politics and economics." Business & Economics is one of
Wikipedia's highest-editor-interest areas with massive article volume.
The Vital hierarchy systematically undervalues it. Pragmatic elevation.

**Edge cases**:
- "Companies" — plural form. **Decision**: added explicitly.
- "Square Enix" — a video game company. Could be Arts (game developer) or
  Business. **Decision**: Arts & Culture, as it primarily creates
  entertainment products.

### 10. Society & Social Sciences (67 projects)

**Scope**: Politics, law, education, media, journalism, sociology,
anthropology, and related social topics.

**Inherited from**: Vital "Society and social sciences."

**Expanded**: Yes. Absorbs education, media, journalism, accessibility,
and social justice projects.

**Edge cases**:
- "Science" — the generic WikiProject. Could be Society (science policy)
  or Physical Sciences. **Decision**: Society, as "Science" without a
  specific field usually refers to the science-of-science or general
  science topics, which is social-science adjacent.
- "Freemasonry" — a fraternal organization. **Decision**: Society, not
  Philosophy/Religion, because it's primarily a social organization.
- "Schools" — plural form of "school". **Decision**: added explicitly.

### 11. History (70 projects)

**Scope**: Ancient, medieval, military, genealogical, heritage.

**Inherited from**: Vital. Absorbs Military & Defense.

**Edge cases**:
- "Presidents of the United States" — contains "united states" (Geography)
  but matched "presidents" in History. **Decision**: Accept as-is —
  History is the correct domain for a biographical history project.
- "Ancient Egypt" — was initially caught by Geography via "egypt".
  **Decision**: added "ancient" to Geography exclusions, allowing History
  to catch it.

### 12. Arts & Culture (88 projects)

**Scope**: Music, film, television, literature, comics, visual arts,
performing arts, architecture, museums.

**Unified from**: 5 separate domains in the initial classification (Music,
Film & Television, Literature & Writing, Visual & Plastic Arts, Performing
Arts).

**Justification**: 88 projects is manageable as one top-level category with
sub-filters. Five separate picker sections would be too granular.

**Edge cases**:
- "Alien" — the science fiction franchise. **Decision**: Arts & Culture.
- "20th Century Studios", "EastEnders", "South Park", "The Simpsons" —
  specific media properties. **Decision**: Arts & Culture.
- "Films" — plural form needed explicit addition.

### 13. Philosophy & Religion (41 projects)

**Scope**: Philosophy, religion, mythology, languages, linguistics.

**Inherited from**: Vital "Philosophy and religion."

**Expanded**: Yes. Languages & Linguistics are placed here as the best
available home.

**Edge cases**:
- "Languages", "Linguistics", "Constructed languages", "Latin" — these
  have no dedicated taxonomical slot. Philosophy & Religion is the closest
  fit (language study as a humanistic discipline). **Decision**: accepted
  compromise. A future "Languages" top-level category is worth considering
  if more language projects appear.
- "Anthroponymy" — the study of personal names. **Decision**: Philosophy &
  Religion (linguistics-adjacent).
- "Altered States of Consciousness" — psychology/philosophy. **Decision**:
  Philosophy & Religion.

### 14. People & Biography (32 projects)

**Scope**: Individual biographies, celebrity WikiProjects, bands, women's
history projects.

**Inherited from**: Vital "People."

**Expanded**: Yes. Absorbs individual artist/band WikiProjects from
uncategorized.

**Edge cases**:
- Individual artist names were added as explicit keywords (Beyoncé,
  Alexandra Stan, Björk, Inna, Rufus Wainwright). **Decision**: listed
  individually because they don't follow a pattern.
- "Women in Red", "Women in Green" — WikiProjects focused on creating
  articles about women. **Decision**: People & Biography (matched by
  "women in" keyword).

### 15. Everyday Life & Food (24 projects)

**Scope**: Agriculture, food, drink, amusements, lifestyle.

**Remnant category**: All that remains of Vital's "Everyday life" after
Sports & Games and Transportation were elevated.

**Edge cases**:
- "Spirits" — alcoholic beverages. **Decision**: Everyday Life & Food.
- "Underwater diving" — recreational activity. **Decision**: Everyday
  Life & Food.

---

## Known Issues & Future Improvements

### Current misclassifications (minor):

1. **"Bangladesh Premier League"** → Geography (should be Sports).
   Fix: add "premier league" to Geography exclusions.

2. **"Channel Islands"** → Geography (correct), but listed under Physical
   Sciences in sample output due to "islands" matching both. This is a
   display artifact only (the sample shows Geography entries that also
   match Physical Sciences keywords). The actual classification IS correct
   because Geography runs first.

3. **"Biota of Great Britain and Ireland"** → Geography (matched "britain").
   Should be Health/Medicine & Biology. Fix would require a more specific
   exclusion for "biota" in Geography.

### Design patterns to maintain:

1. **Always add both singular and plural forms.** This is the most common
   source of uncategorized projects. If you add "bird", also add "birds".
   If you add "company", also add "companies".

2. **Check Geography exclusions when adding new country names.** Some
   country names overlap with History terms (e.g., "Romania" contains
   "roman"). Test with `classify_domain()` to verify.

3. **Priority order matters.** Geography (rule 1) catches anything with a
   place name. Add exclusions when a non-geography project contains a
   place name (e.g., "Ancient Egypt" → exclude "ancient" from Geography).

4. **No uncategorized should persist.** If a new WikiProject appears on the
   Community Tech bot's Popular pages page, update the classification
   rules to cover it before running the data generation pipeline.

### Testing checklist:

After any rule change:
```python
from classify_projects import classify_domain

# Test specific cases
assert classify_domain("United States") == "Geography & Places"
assert classify_domain("Ancient Egypt") == "History"
assert classify_domain("Phasmatodea") == "Health, Medicine & Biology"

# Run full classification and verify zero uncategorized
from classify_projects import fetch_project_names, classify_domain
names = fetch_project_names()
uncategorized = [n for n in names if classify_domain(n) == "Other / Uncategorized"]
assert len(uncategorized) == 0, f"{len(uncategorized)} uncategorized: {uncategorized}"
```

---

## Source of Truth

The list of 942 WikiProjects with Popular pages is maintained at:
https://en.wikipedia.org/wiki/User:Community_Tech_bot/Popular_pages

This is the authoritative source. The `fetch_project_names()` function in
`classify_projects.py` fetches this page via `action=parse`. Do NOT use
database queries for discovery — they produce false positives from
sub-projects, task forces, and redirects.
