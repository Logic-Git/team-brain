# Setting up a knowledge base in a new repo

Reached when `kg.py locate` reports `no_kb`. Setup is a conversation, not a command
the user has to know: you offer, they say yes, you run it.

## 1. Offer, and confirm the location

Never scaffold into whatever directory happens to be open. Say in one or two lines
what setup does and ask:

> "There's no knowledge base in `<repo>` yet. Set one up? I'll create the knowledge
> graph and context folder, add a short block to CLAUDE.md so I check it before
> answering, and turn off Claude Code's built-in memory for this project so everything
> is remembered in one place."

On yes:

```
python "<skill>/scripts/kg.py" init --root "<repo>"
```

`--root` is required on purpose. `init` is idempotent and refuses to overwrite: files
that already exist are reported as skipped.

It creates `inputs/memory/knowledge_graph.yaml` (schema documented in comments),
`inputs/memory/context/`, `tools/README.md`, `prompts.md`, `.claude/knowledge-base.yaml`
(fully commented, all defaults, `write_mode: auto`), the CLAUDE.md trigger block
(created, appended, or an old-name block renamed in place — never overwritten), and
sets `"autoMemoryEnabled": false` in `.claude/settings.json` (merged, other keys kept).
The user approves those file writes like any other.

If the user wants to keep Claude Code's built-in memory, add `--keep-auto-memory`.
If they want records only on request, set `write_mode: manual` in
`.claude/knowledge-base.yaml` afterwards.

`init` **prints** the `.gitignore` chain rather than writing it; relay it if `inputs/`
is ignored in this repo.

## 2. Bring over the built-in memory, if there is any

Turning off built-in auto memory means its notes stop loading. If this project already
has auto-memory notes (the memory directory named in your instructions, with a
`MEMORY.md` index), offer to migrate them: for each note worth keeping, find the entity
it is about, and add the fact to that entity's context file (or create the entity).
Skip notes that are stale, duplicated, or about how to talk to the user rather than
about the work. Propose the list briefly and migrate what the user approves; leave the
old directory in place — the user can delete it.

## 3. Seed the graph — the part that matters

An empty graph nobody fills is the usual failure mode, so do not stop at scaffolding.

Ask what this repo actually does and what it touches: which systems, data stores,
documents, dashboards, scripts and external services. Then propose **5–10 starting
entities**, each with a type, edges and a one-line note, and write them with Edit once
the user agrees. Aim for the things someone would ask about in week one.

Prefer a few well-connected nodes over many isolated ones — the `in`/`out` edges are
what make retrieval work.

## 4. Mention triggers once, then stop

Tell the user the CLAUDE.md block currently carries a generic directive and that they
can sharpen it any time by naming the words their team actually uses ("add our Monday
boards and Looker dashboards as trigger keywords"). Do not fill it in speculatively and
do not keep raising it.

## 5. Afterwards

`kg.py validate` confirms the seeded graph is structurally sound. From then on the
normal retrieval and recording paths apply, and this file is not needed again.

## Repos set up under the old name

A repo set up with the earlier `memory:knowledge-context` skill already has a knowledge
base, so it never reaches this file. `kg.py doctor` flags its old CLAUDE.md block and
missing auto-memory setting; fix both with
`kg.py init --root "<repo>" --claude-md-only` and
`kg.py init --root "<repo>" --settings-only`.
