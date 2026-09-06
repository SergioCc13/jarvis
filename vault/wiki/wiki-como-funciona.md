---
title: How this wiki works
tags: [meta]
status: living
updated: 2026-09-01
summary: Wiki conventions and what bin/wiki-graph does (graph + index + checks).
---

# How this wiki works

## Conventions

- One note per concept, in `vault/wiki/` (at any depth).
- Filename in `kebab-case`; that's the node **id** and the target of `[[links]]`.
- Frontmatter:
  - `title` — human-readable title.
  - `tags` — a list; **the first one** is the group in the index (`subsystem`, `pr`, `idea`, `meta`, `decision`).
  - `status` — `active`, `open`, `merged`, `idea`, `living`…
  - `updated` — `YYYY-MM-DD`.
  - `summary` — one sentence; this is what shows in the index and in `_graph`.
- Over-link: `[[bridge]]`, `[[ollama-fallback]]`. A link to a note that doesn't exist yet is a
  to-do, not an error (the generator reports it).

## `bin/wiki-graph`

```
bin/wiki-graph           # regenerate _graph.json, _graph.md and the MOC.md index
bin/wiki-graph --check   # exit 1 if something is stale or there are broken links
```

It scans every note (except `private/` and `_*`), extracts frontmatter + `[[links]]`
(ignoring the ones inside code blocks) and writes:

- **`_graph.json`** — `{nodes:[{id,title,summary,tags,status,file,links}], edges:[[a,b]]}`.
  One read gives the whole map. Ideal for Claude or scripts.
- **`_graph.md`** — the same, grouped by tag, + **broken links** and **orphans** sections.
- The `<!-- AUTO:INDEX -->` block of [[MOC]].

(`_graph.*` start with `_` → the generator doesn't treat them as notes.)
Idempotent: running it twice changes nothing. Can hang off a pre-commit or the cron.

## Scaling

Adding a topic = create a `.md` with frontmatter and run `bin/wiki-graph`. Nothing in the
generator lists notes by hand; the graph is rebuilt whole every time.

See also: [[cron]], [[coste-tokens]].
