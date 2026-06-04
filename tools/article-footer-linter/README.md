# Article Footer Linter

Lint and fix Wikipedia article footers. Detects structural issues like
misplaced bullets, wrong template order, missing whitespace — and optionally
checks for dead external links.

Part of the [Wiki MIT](https://meta.wikimedia.org/wiki/Wiki_MIT) project.

## Quick start

```bash
# Install
pip install -e tools/article-footer-linter/

# Analyze an article
article-footer-lint "Climate change"

# Analyze and fix
article-footer-lint "Photovoltaics" --fix

# Preview without posting
article-footer-lint "Biology" --fix --dry-run

# Survey random articles
article-footer-lint --survey 50
```

From the project root, you can also use the wrapper:

```bash
python3 scripts/lint-article-footer.py "Climate change" --fix
```

## What it detects

| Issue | Severity | What it does |
|-------|----------|-------------|
| `bullet_after_categories` | Error | Moves `*` bullets from after `[[Category:...]]` to before them |
| `defaultsort_position` | Warning | Moves `{{DEFAULTSORT:...}}` to before categories |
| `auth_control_position` | Info | Moves `{{Authority control}}` to after navboxes |
| `stub_position` | Info | Moves stub templates to after the last category |
| `section_spacing` | Info | Ensures blank lines between sections |
| `whitespace_cleanup` | Info | Collapses 3+ blank lines, removes trailing blanks |

## Phase 2: Dead link detection (planned)

```bash
# Check for dead links (no changes)
article-footer-lint "Climate change" --check-links

# Tag dead links with {{dead link}}
article-footer-lint "DNA" --check-links --tag-dead
```

## Architecture

```
analyze_footer(wikitext)  → [Issue]           # Pure function — no I/O
apply_fixes(wikitext, issues) → (wikitext, [FixResult])  # Pure function — no I/O
check_links(wikitext)      → [LinkResult]     # HTTP calls (Phase 2)
```

## Tests

```bash
cd tools/article-footer-linter
python3 -m pytest tests/ -v
```

## License

MIT. See project root.
