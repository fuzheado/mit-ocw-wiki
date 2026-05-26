---
name: wikipedia-editing
description: Programmatically edit Wikipedia pages — talk page insertion, template manipulation with mwparserfromhell, API auth, encoding, and test-driven approach. Distills lessons from building the Wiki MIT refideas linter/fixer.
license: MIT
compatibility: opencode
---

## When to use this skill

You're building a tool that edits Wikipedia pages programmatically — fixing template formatting, inserting talk page banners, replacing citations, or any wikitext mutation applied via the API.

## SOP: Talk page insertion points

Talk pages have variable structure. From sampling 25 crossref-matched articles:

| Pattern | Frequency | Strategy |
|---------|-----------|----------|
| `{{WikiProject banner shell\|...}}` then `==` sections | 88% | Insert before first `==` heading |
| Banner shell + tables, todo lists, extra banners | 8% | Insert before first `==` heading (same) |
| Templates only, no discussion sections | 4% | Append at end |

**The insertion algorithm:**

```
1. Fetch Talk page wikitext via action=parse&prop=wikitext
2. Parse with mwparserfromhell
3. Find first real heading: code.filter_headings()
4. Locate heading in original wikitext string (NOT via regex on ==)
5. Insert new block before it
6. Fallback: if no headings, append at end
```

**⚠️ Never use `re.split(r'\n==', ...)` to find headings.** The `==` pattern appears inside template parameters, table cells, and HTML comments — it will produce false matches. Always use mwparserfromhell's AST-based `filter_headings()`.

## SOP: mwparserfromhell gotchas

### `filter_templates(matches=...)` receives the Template node, not the name

```python
# ❌ WRONG — str(template) returns "{{Refideas|...}}" with braces
code.filter_templates(matches=lambda n: str(n).lower().strip() == "refideas")

# ✅ CORRECT — use t.name to get just the template name
code.filter_templates(matches=lambda t: str(t.name).lower().strip() == "refideas")
```

### Capture `str(tmpl)` BEFORE modifying params

```python
# ❌ WRONG — str(tmpl) captured after tmpl.remove(param)
tmpl.remove(param)
old_text = str(tmpl)  # modified text doesn't exist in original wikitext
wikitext.replace(old_text, new_block)  # silently fails

# ✅ CORRECT — capture original first
old_text = str(tmpl)
tmpl.remove(param)
wikitext.replace(old_text, new_block)  # works
```

### Template params: named vs positional

In mwparserfromhell:
- `|1=value` → `param.name = "1"` (numbered, `name.isdigit()`)
- `|value` → `param.name = "1"` (positional, serialized without number)
- `|state=collapsed` → `param.name = "state"`, `param.value = "collapsed"`
- `|comment=note` → `param.name = "comment"`, `param.value = "note"`

When rebuilding a template, preserve numbered params as `|1=value` and named params as `|state=collapsed`.

### Template aliases

Templates can have many aliases. For `{{refideas}}`, we found 11: Refideas, Refidea, RI, Ref ideas, Suggested sources, Suggested refs, Source ideas, Potential sources, Possible sources, Refideas-nonotice, Refsuggestion. Always check `Special:WhatLinksHere` for the full list.

## SOP: Wikipedia API encoding

### The double-encoding trap

`urllib.parse.urlencode()` re-encodes percent signs. If you pre-encode a title with `quote()` and then pass it through `urlencode()`, it becomes double-encoded (`%26` → `%2526`).

```python
# ❌ WRONG — urlencode will double-encode %26 to %2526
encoded = urllib.parse.quote("Agony & Irony")  # → "Agony_%26_Irony"
params = {"page": f"Talk:{encoded}"}
url = WIKIPEDIA_API + "?" + urllib.parse.urlencode(params)

# ✅ CORRECT — build URL directly when you need percent-encoding
encoded = urllib.parse.quote("Agony & Irony")
url = f"{WIKIPEDIA_API}?action=parse&page=Talk:{encoded}&..."

# ✅ ALSO CORRECT — pass raw title to urlencode, let it encode once
params = {"page": "Talk:Agony & Irony"}
url = WIKIPEDIA_API + "?" + urllib.parse.urlencode(params, safe="|:")
```

### Cache titles may be percent-encoded

When storing page titles from `list=embeddedin`, the API returns them in percent-encoded form. Always `unquote()` before re-encoding or passing to `urlencode`.

```python
# Titles from API cache
title = "Black_Mesa_%28video_game%29"  # has %28 for (
decoded = urllib.parse.unquote(title)   # → "Black_Mesa_(video_game)"
```

### Multi-page queries can't use rvlimit

```python
# ❌ WRONG — rvlimit only works on single-page queries
url = f"{WIKIPEDIA_API}?action=query&titles=A|B|C&prop=revisions&rvlimit=1"

# ✅ CORRECT — API automatically returns latest revision for multi-page
url = f"{WIKIPEDIA_API}?action=query&titles=A|B|C&prop=revisions&rvprop=content&rvslots=*"
```

### Batch fetching: one API call for 50 pages

```python
titles = "|".join(f"Talk:{quote(unquote(a).replace(' ', '_'), safe='')}" for a in articles[:50])
url = f"{WIKIPEDIA_API}?action=query&titles={quote(titles, safe='|:')}&prop=revisions&rvprop=content&rvslots=*"
```

## SOP: Authentication

### Bot passwords (simpler for CLI tools)

1. Create at `Special:BotPasswords` with "Edit existing pages" grant
2. Login name: `YourUsername@BotName`
3. Store in `.env`: `WIKIPEDIA_USERNAME` and `WIKIPEDIA_BOT_PASSWORD`

```python
# Login flow with cookie jar (shared jar is ESSENTIAL)
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

# Step 1: Get login token (cookies saved in jar)
url = f"{API}?action=query&meta=tokens&type=login&format=json&formatversion=2"
req = urllib.request.Request(url, headers={"User-Agent": UA})
with opener.open(req) as resp:
    login_token = json.loads(resp.read())["query"]["tokens"]["logintoken"]

# Step 2: Login with POST (same jar — THIS IS THE KEY)
post_data = urllib.parse.urlencode({
    "action": "login", "lgname": username, "lgpassword": password,
    "lgtoken": login_token, "format": "json",
}).encode()
req = urllib.request.Request(API, data=post_data, headers={...})
with opener.open(req) as resp:
    result = json.loads(resp.read())["login"]

# Step 3: Get CSRF token (same jar)
url = f"{API}?action=query&meta=tokens&type=csrf&format=json&formatversion=2"
req = urllib.request.Request(url, headers={"User-Agent": UA})
with opener.open(req) as resp:
    csrf = json.loads(resp.read())["query"]["tokens"]["csrftoken"]

# Step 4: Post edit (same jar)
post_data = urllib.parse.urlencode({
    "action": "edit", "title": f"Talk:{title}",
    "text": wikitext, "summary": "Edit summary", "token": csrf, "format": "json",
}).encode()
req = urllib.request.Request(API, data=post_data, headers={...})
with opener.open(req) as resp:
    result = json.loads(resp.read())["edit"]
```

**⚠️ The cookie jar must be shared across all 4 steps.** If you create a new opener for each step, the session is lost and login fails.

## SOP: Test-driven approach for wikitext tools

Wikitext editing tools have subtle failure modes that only surface in production. A test suite catches these before deployment.

### Test categories

1. **Happy path** — each fix type with canonical input
2. **Edge cases** — empty templates, nested templates, special characters
3. **Idempotency** — running the fix twice produces no changes
4. **Regression** — specific bugs found in production
5. **Format preservation** — numbering, comments, state params survive reformat

### Test pattern

```python
def lint_and_fix(wikitext):
    """Helper: run linter + fixer on wikitext, return (result, fixed, errors)."""
    result = lint.lint_refideas_templates(wikitext, "Test")
    fixed, errors, summary = lint.generate_fix(wikitext, "Test")
    return result, fixed, errors

class TestDuplicateURL(unittest.TestCase):
    def test_simple_duplicate(self):
        wikitext = """{{refideas
|1=https://a.com/article
|2=https://b.com/stuff
|3=https://a.com/article
}}
== Talk ==
Text."""
        result, fixed, errors = lint_and_fix(wikitext)
        self.assertTrue(result.has_actionable_errors)
        self.assertEqual(fixed.count("https://a.com/article"), 1)
```

### Key assertions

- `result.has_actionable_errors` — true for errors/warnings, false for info-only
- `fixed != wikitext` — a change was actually made
- `refs_in_output(fixed) == N` — correct number of references after fix
- `has_numbered_params(fixed)` — numbering preserved
- `"state=collapsed" in fixed` — non-ref params preserved

## SOP: Refideas template specifics

The `{{refideas}}` template appears on ~29,000 English Wikipedia Talk pages.

### Common errors found

| Error | Frequency | Auto-fixable |
|-------|-----------|-------------|
| Bullet syntax (`|* url` or multi-bullet) | ~14% of pages | ✅ Yes |
| Bare URLs without `[url Label]` | ~52% of refs | ❌ Need label from page |
| Duplicate URLs | ~2% | ✅ Remove duplicate |
| Missing parameter numbering | ~2% | ✅ Add numbers |

### Fix formatting

Produce clean, readable wikitext with each reference on its own line:

```wikitext
{{refideas
|1=[https://example.com/article Label], Source (note)
|2={{cite journal|title=Paper|journal=Nature|...}}
|3=https://archive.org/details/book
}}
```

Never output refideas content on a single line — this is hard for other editors to read.
