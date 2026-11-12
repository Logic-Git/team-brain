# team-brain

Memory for Claude Code that a person, a team or a company can share: a knowledge graph
of the entities you work with, each linked to a markdown context file holding the
details, landmines and verbatim code that the code itself does not state.

The plugin ships **code only**. Every repo keeps its own knowledge base, in the repo.

## Getting started

Install the plugin, open a repo, and ask Claude something about your work. If the repo
has no knowledge base yet, Claude offers to set one up and does it for you — you only
approve the file writes. Nothing to type.

Setup creates the graph and context folder, adds a short block to `CLAUDE.md` so Claude
checks the knowledge base before answering, and turns off Claude Code's built-in auto
memory for that project so everything is remembered in one place.

## How it records knowledge

Set `write_mode` in `.claude/knowledge-base.yaml`:

- **`auto`** (default) — Claude records knowledge on its own once it is finalized: you
  confirmed it (the approach was right, the output worked), or it is a fact read from a
  trusted source such as a schema or a file. Every write is announced in one line, so
  you can say "undo that".
- **`manual`** — nothing is recorded until you say "record the learning". Claude then
  proposes what to add or change, and writes what you approve.

## Two things worth knowing

**Triggering lives in the repo's `CLAUDE.md`**, not in the plugin. The plugin's
description is domain-neutral because it serves every repo; the CLAUDE.md block is
where you name the things *your* repo contains. Ask: "add our Monday boards and Looker
dashboards as trigger keywords".

**Retrieval never reads the whole graph.** A mature graph is ~40k tokens; the skill
reads a ~3k-token index instead and pulls individual nodes with `search` and `show`.
Setup and other rarely needed instructions live in reference files that load only when
needed.

## Saved prompts

`prompts.md` at the repo root stores prompts you want to replay. Each one is a
`## Name` heading, a `> summary:` line, then the prompt. Say "run the daily standup
prompt" and the skill finds it by keywords and runs it. A saved prompt can call other
skills. Saved prompts work even in a repo with no knowledge graph.

## Moving from the old `memory` plugin

A repo set up with `memory:knowledge-context` keeps its knowledge base unchanged. After
installing team-brain (and removing the old plugin), ask Claude to run `kg.py doctor`;
it renames the old CLAUDE.md block in place (your trigger words are kept) and turns off
built-in auto memory.

## Commands (run by Claude; listed for reference)

| Command | Does |
|---|---|
| `kg.py locate [--index]` | resolve the knowledge base; `--index` adds the node index |
| `kg.py search <terms>` | find nodes by key, type, section or notes |
| `kg.py show <node> [--depth N]` | one node in full, plus its neighbours |
| `kg.py validate` | structural check: link symmetry, dangling refs, duplicates |
| `kg.py doctor` | diagnose triggering, old-name blocks, and the auto-memory setting |
| `kg.py init --root <repo>` | set up a knowledge base (`--claude-md-only`, `--settings-only`, `--keep-auto-memory`) |
| `prompts.py get <words>` | find one saved prompt by name or keywords and print it |
| `prompts.py find` / `list` | ranked keyword search / every saved prompt |
| `prompts.py save` / `update` / `delete` | edit prompts.md (`--dry-run` shows the diff; every write is backed up) |

Stdlib-only Python 3.9+. No `pip install`.

## What it never does

Write inside the plugin directory (a marketplace clone is hard-reset on update), edit
your knowledge base without a visible diff, record secrets, or guess a knowledge-base
location when an explicit one is wrong.
