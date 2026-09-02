---
title: Cómo funciona este wiki
tags: [meta]
status: vivo
updated: 2026-09-01
summary: Convenciones del wiki y qué hace bin/wiki-graph (grafo + índice + chequeos).
---

# Cómo funciona este wiki

## Convenciones

- Una nota por concepto, en `vault/wiki/` (a cualquier profundidad).
- Nombre de fichero en `kebab-case`; ese es el **id** del nodo y el destino de `[[enlaces]]`.
- Frontmatter:
  - `title` — título legible.
  - `tags` — lista; **el primero** es el grupo en el índice (`subsistema`, `pr`, `idea`, `meta`, `decision`).
  - `status` — `activo`, `abierto`, `mergeado`, `idea`, `vivo`…
  - `updated` — `YYYY-MM-DD`.
  - `summary` — una frase; es lo que sale en el índice y en `_graph`.
- Enlaza de más: `[[bridge]]`, `[[ollama-fallback]]`. Un enlace a una nota que aún no existe
  es una tarea pendiente, no un error (lo reporta el generador).

## `bin/wiki-graph`

```
bin/wiki-graph           # regenera _graph.json, _graph.md y el índice de MOC.md
bin/wiki-graph --check   # exit 1 si algo está desactualizado o hay enlaces rotos
```

Escanea todas las notas (menos `private/` y `_*`), extrae frontmatter + `[[enlaces]]`
(ignora los que están dentro de bloques de código) y escribe:

- **`_graph.json`** — `{nodes:[{id,title,summary,tags,status,file,links}], edges:[[a,b]]}`.
  Una sola lectura da el mapa entero. Ideal para Claude o scripts.
- **`_graph.md`** — lo mismo agrupado por tag, + secciones de **enlaces rotos** y **huérfanas**.
- El bloque `<!-- AUTO:INDEX -->` de [[MOC]].

(`_graph.*` empiezan por `_` → el generador no los trata como notas.)
Idempotente: correrlo dos veces no cambia nada. Se puede colgar de un pre-commit o del cron.

## Escalar

Añadir tema = crear un `.md` con frontmatter y `bin/wiki-graph`. Nada en el generador
enumera notas a mano; el grafo se reconstruye entero cada vez.

Ver también: [[cron]], [[coste-tokens]].
