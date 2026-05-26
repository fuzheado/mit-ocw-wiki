# OCW LLM Wiki — Version Control with Git

The wiki is just a directory of markdown files — Git is the natural version control layer. Here are best practices for keeping the wiki clean at scale.

## Repository Structure

```
ocw-llm-wiki/
  .gitignore
  OCW-LLM-WIKI.md        # Schema file (this doc)
  raw/                   # Immutable source data
    api/                 # Raw API JSON (can be large)
  wiki/                  # LLM-generated markdown
    index.md
    log.md
    courses/
    departments/
    topics/
    instructors/
    assets/
    crossrefs/
    reports/
```

## `.gitignore`

```
# Raw API data is reproducible; commit only if you want snapshots
raw/api/

# OS junk
.DS_Store
Thumbs.db

# Editor temp files
*.swp
*.swo
*~
```

**Recommendation:** Gitignore `raw/api/` if you can re-fetch from the API. If you want reproducible builds, keep it but consider Git LFS for the larger JSON pages.

## Commit Strategy

### One operation, one commit

Each workflow step gets its own commit with a predictable message format:

```
ocw: bootstrap {N} courses from API              # Initial ingest
ocw: ingest {course_id} - {title}                 # Single new course
ocw: crossref {topic} → {N} Wikipedia articles    # Crossref pass
ocw: lint — fix {N} broken links, {N} orphans     # Lint pass
ocw: asset — {asset_title} tagged [Visual-Rich]   # Asset tagging
ocw: report — topic coverage analysis             # Generated report
```

The prefix `ocw:` makes it trivial to filter: `git log --oneline --grep="^ocw:"`

### Use `log.md` as the commit source

Since `wiki/log.md` is an append-only record with consistent prefixes, you can use it directly:

```bash
# After an ingest
git add wiki/
git commit -m "$(tail -1 wiki/log.md)"
```

### Batch size

For the initial 2,577-course bootstrap, consider committing in batches of ~100-200 courses rather than one giant commit. This makes it easier to find when something was introduced. The API paginates at 100 anyway, so one commit per API page is a natural rhythm.

## Branching

### Long-lived branches

- `main` — the canonical, reviewed wiki
- `experiment/{feature}` — try different topic hierarchies, crossref strategies, or page templates. Merge or discard.

### Per-session branches

Before a lint pass that may touch many files, create a branch:

```bash
git checkout -b lint/may-2026
# run lint workflow
git commit -m "ocw: lint — May 2026 pass"
git checkout main
git merge lint/may-2026
```

This keeps `main` clean and gives you a rollback point if the LLM introduces bad changes.

## Dealing with Scale

### 2,500+ files is fine for Git

Git handles repositories with tens of thousands of markdown files without issue. However:

- **`git status` will be slow** — use `git status --short` or scope it to a subdirectory.
- **`git log` over the whole tree** may be noisy — filter with `-- wiki/courses/` to see only course changes.
- **Use `.gitattributes`** to mark markdown files for better diffs:
  ```
  *.md diff=markdown
  ```

### Shallow clone for CI

If you set up automation (e.g., GitHub Actions to refresh data), use a shallow clone:

```bash
git clone --depth 1 <repo-url>
```

## Recovery

### Roll back a bad ingest

```bash
# Find the commit before the bad ingest
git log --oneline --grep="^ocw:"
# Roll back
git revert <bad-commit-hash>
```

### Revert specific files without losing others

```bash
# Check out a single page from a previous commit
git checkout <hash> -- wiki/courses/21h-151-dynastic-china-fall-2024.md
```

## GitHub Actions (Optional)

A simple weekly refresh workflow:

```yaml
name: Refresh OCW data
on:
  schedule:
    - cron: '0 6 * * 1'  # Mondays
jobs:
  refresh:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Fetch new courses
        run: |
          # script to fetch API and diff against wiki/courses/
          # commit any new courses found
      - name: Create PR
        run: |
          git add -A
          git diff --cached --quiet || \
            gh pr create --title "ocw: weekly ingest $(date +%Y-%m-%d)"
```

This creates a PR instead of committing directly to `main`, giving you a chance to review the LLM's work before merging.

## Summary

| Scenario | Command |
|----------|---------|
| After bootstrap batch | `git commit -m "ocw: bootstrap courses {offset}-{offset+99}"` |
| After single ingest | `git commit -m "$(tail -1 wiki/log.md)"` |
| After crossref pass | `git commit -m "ocw: crossref — {N} Wikipedia matches"` |
| Before lint | `git checkout -b lint/$(date +%Y-%m-%d)` |
| Roll back one operation | `git revert <hash>` |
| See only course changes | `git log -- wiki/courses/` |
| See all OCW work | `git log --oneline --grep="^ocw:"` |
