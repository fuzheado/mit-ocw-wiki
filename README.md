# MIT OCW LLM Wiki

A living, interlinked knowledge base of MIT OpenCourseWare's 2,500+ courses, built incrementally by an LLM agent following the [LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

Courses are ingested from the [MIT Learn API](https://api.learn.mit.edu) and cross-referenced against Wikipedia to identify where MIT's open-licensed educational materials can improve articles. The wiki is maintained as markdown files, compiled into a browsable site by the WikiWise app.

## Status

- **Courses discovered:** 2,577
- **Courses ingested:** 4 (test batch)
- **Departments:** 37
- **Topics:** 110

## Quick start

```bash
# Open in your LLM agent (Claude Code, Codex, etc.)
claude

# The agent will read CLAUDE.md and proceed through the stages:
# Stage 0 — smoke test (done)
# Stage 1 — department and topic pages (done)
# Stage 2 — course ingest (in progress)
# Stage 3 — asset scanning
# Stage 4 — Wikipedia cross-referencing
```

## Structure

- `CLAUDE.md` — agent instructions and project schema
- `raw/` — immutable API source data
- `wiki/` — LLM-maintained markdown pages
- `site/` — WikiWise build tooling

## License

The wiki metadata and structure are MIT. Course content referenced is CC BY-NC-SA 4.0.
