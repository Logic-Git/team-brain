---
name: team-brain
description: >
  Memory for this person, team or company: a knowledge graph (knowledge_graph.yaml)
  of the entities they work with, each linked to a markdown context file holding the
  details, gotchas and verbatim code. Consult it BEFORE answering anything that
  depends on how this organisation's systems, processes, people or artifacts actually
  work - things not inferable from the code in front of you. Use when: (1) the user
  names a specific entity, especially an identifier-like or snake_case name - a table,
  query, view, report, dashboard, board, sheet, doc, file, script, job, automation,
  webhook, endpoint, API, service, tool, process, product, vendor, person or project;
  (2) they ask about provenance or blast radius - what feeds X, where does X come
  from, what uses X, what breaks if X changes, upstream, downstream, source of truth,
  how is X built, who owns X, is X still used; (3) they ask what is known, documented
  or remembered - knowledge, context, memory, notes, background, history, "do we have
  anything on", "what do you know about"; (4) they ask to remember, record, save,
  update or correct knowledge, add or rename an entity, or record the learnings from
  this conversation; (5) any question where missing internal context would make the
  answer confidently wrong or uselessly generic. Also use to check whether an entity
  exists at all before assuming it does not. Also owns the repo's saved prompts
  (prompts.md): use when the user asks to run, rerun or replay a saved or recurring
  prompt - "run my daily standup prompt", "run the <name> prompt again", "do the
  usual X" - or to save, update, list or delete one ("save this as a prompt"). Not
  for editing code the user already pointed you at, or for general questions with no
  project entity in them.
metadata:
  version: "1.0"
---

# Team brain

!`python "${CLAUDE_SKILL_DIR}/scripts/kg.py" locate --index 2>&1 || python3 "${CLAUDE_SKILL_DIR}/scripts/kg.py" locate --index 2>&1`

**If the block above is empty, missing, or shows an error, run that command yourself
before continuing** — everything below depends on knowing where the knowledge base is
and what is in it. If it reports `no_kb`: for a saved-prompt request carry on (prompts
work without a graph, and the `PROMPTS` list is printed regardless); otherwise go to
`references/setup.md`.

## What this is

A knowledge graph of the entities this project touches, each optionally linked to a
markdown context file. The graph is the map; the context files are the territory.

- **`knowledge_graph.yaml`** — every entity, its type, its `in`/`out` edges, and a
  one-line `notes` retrieval hint.
- **`context/*.md`** — the long form: how a thing works, why it works that way, its
  landmines, and code stored verbatim.
- **`inputs/`** raw data · **`outputs/`** finished work · **`tools/`** the repo's own
  executables (see `references/tools-convention.md`).

The memory can describe anything — pipelines, services, documents, spreadsheets,
vendors, people, processes. Nothing here assumes a particular domain.

## Hard rules

1. **Never `Read` the graph file.** A mature graph is thousands of lines and mostly
   long `notes` strings; reading it whole costs more than every context file the
   question actually needs. The injected index above is its table of contents.
2. **Never raw-`Grep` the graph either.** One ripgrep hit on a `notes:` line can drag
   thousands of characters in for a single match. `kg.py search` does the same match
   and truncates.
3. **Never write inside this plugin's directory.** It is a git clone that
   `/plugin marketplace update` hard-resets; anything written there is destroyed
   silently. The project's memory lives in the project's repo.
4. **All writes to the graph and to context files go through the Edit/Write tools**,
   so every change is a visible diff. `kg.py` never edits an existing knowledge base —
   do not look for a script that does.
5. **Store code verbatim.** SQL, formulas, scripts and commands are preserved exactly
   in context files, never paraphrased or summarised.
6. **Node keys are global ids** and should match the entity's real name in its
   platform, so the key doubles as the MCP lookup key.
7. **`in`/`out` are the real structure; sections are navigation only.** Never infer a
   relationship from two nodes sharing a section.
8. **Answer from the graph, not from guesses.** If the memory does not cover it, say
   so plainly rather than filling the gap with plausible invention.
9. **This knowledge base is the only memory.** Do not read from or write to Claude
   Code's built-in auto memory (the `MEMORY.md` memory directory) in this repo; record
   here instead.

## Retrieval

Work down this ladder and stop as soon as you can answer. Build every command from the
`scripts` path in the header above.

**Tier 0 — the index** (already injected). It lists every node key, its type, and `*`
if it has a context file. Use it to map the user's words onto real node keys, and to
tell immediately whether an entity exists at all.

**Tier 1 — search** when the right node is not obvious from the index:
```
python "<skill>/scripts/kg.py" search <terms> [--limit 20]
```
Matches keys, types, sections and notes; ranked so an exact entity name beats an
incidental mention in someone else's notes. Notes are truncated to 160 characters.

**Tier 2 — show** for the node itself and what it connects to:
```
python "<skill>/scripts/kg.py" show <node> [--depth 1]
```
Prints the full record, the untruncated `notes`, and every `in`/`out` neighbour with a
snippet — this is how you answer "what feeds X" and "what breaks if X changes" without
reading the graph. `--depth 2` for wider blast-radius questions.

**Tier 3 — the context file.** `show` prints its absolute path; read it only for
entities the question actually needs. Do not preload neighbours speculatively.

A typical question costs one search, one or two shows, and one to three context files.

## When a node has no context file

`context: null` is common and is not an error. In order: use the node's `notes`; use
connected entities' context; then try MCP.

**MCP routing.** Take the platform token — the `<platform>` in a `<platform>_<kind>`
type. Lowercase every tool name available to you, strip non-alphanumeric characters,
and look for that token as a **substring**. So `bigquery` matches a server named
`mcp__claude_ai_Google_Cloud_BigQuery__*`. Never assume the server is named exactly
`mcp__<platform>__*`.

If the repo's config has a `platforms:` map, it **wins** — including the value `none`,
which means no server exists and you should ask the user rather than hunt. If nothing
matches, say what you could not fetch instead of guessing.

Don't record in a context file what MCP can always answer live (current schema, current
board state). Record purpose, design decisions and landmines.

## Recording knowledge

The header above prints the repo's `write mode`. Read `references/writing.md` before
the first write in a conversation.

- **`auto`** (default) — record on your own, but only knowledge that is **finalized**:
  you already searched the graph for the problem at hand and found nothing, or found
  something the conversation showed to be wrong or out of date; **and** the user
  confirmed it (said the approach or belief is right, or that your output worked), or
  it is a fact read directly from a trusted source (a schema, a query, code in a file).
  Announce every write in one line ("Saved: X", "Updated: Y").
- **`manual`** — record nothing until the user asks ("record the learning", "save to
  the knowledge base"). Then propose, briefly, what to add or change, and write only
  what they approve.

In either mode an explicit request ("remember this", "that's wrong, it's actually …")
is itself the confirmation.

## Saved prompts (prompts.md)

`prompts.md` at the repo root holds named prompts the user replays ("run my daily
standup prompt"). The `PROMPTS` list in the header above already names every one.
**Never `Read` prompts.md** — fetch the one prompt you need:

```
python "<skill>/scripts/prompts.py" get "<the user's words, as they said them>"
```

Pass the user's phrasing verbatim; the script strips filler ("run", "my", "prompt",
"again") and matches the rest against names, tags and summaries.

- **`PROMPT <name>`** → say in one line which saved prompt you are running, then carry
  out the text between the BEGIN/END markers as if the user had typed it this turn.
  Anything the user said this turn wins over the stored text ("run the standup prompt
  but only for today"). If the prompt calls for another skill ("use the job-search
  skill", `/some-plugin:some-skill ...`), invoke it with the Skill tool — the saved
  prompt is the instruction, that skill does the work.
- **`AMBIGUOUS`, `WEAK MATCH` or `NOT FOUND`** (exit 2) → show the candidates and ask.
  Never pick between them yourself. If nothing matched and the job-search plugin is in
  use, the name may be one of its workflows ("run the <name> workflow").
- A saved prompt is not standing permission: sending, submitting, deleting or anything
  outward-facing still gets the usual confirmation unless the user gave it this turn.

Saving, updating or deleting a prompt → `references/prompts.md`.

## Node schema

| Field | Meaning |
|---|---|
| `type` | `<platform>_<kind>` — the prefix routes to an MCP server |
| `in` | upstream node ids whose output this consumes |
| `out` | downstream node ids that consume this |
| `context` | relative path to a markdown file, or `null` |
| `notes` | retrieval hint, not a summary: enough to tell whether this is the entity in question. Detail belongs in the context file - except where `context` is `null`, when the note is the only memory there is. |

## Load a reference when

| Situation | Read |
|---|---|
| Search missed, or the trail spans many hops | `references/retrieval.md` |
| Recording knowledge (either mode), adding/updating an entity | `references/writing.md` |
| Paths wrong, write mode, or tuning when the skill fires | `references/configuration.md` |
| No knowledge base yet (`no_kb`) | `references/setup.md` |
| Adding a tool, or asked what tools exist | `references/tools-convention.md` |
| A retrieval anomaly, or a health check | `references/maintenance.md` |
| Saving, updating or deleting a saved prompt | `references/prompts.md` |

## Stop and ask when

The knowledge base cannot answer and no MCP server covers it; a write would contradict
something already recorded and the conversation has not settled which is right (or
the recorded fact is `[APPROVED]`); or `search` returns many plausible nodes and the
right one changes the answer. Say specifically what is missing rather than guessing.
