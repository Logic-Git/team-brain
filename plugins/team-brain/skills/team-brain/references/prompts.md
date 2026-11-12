# Saved prompts — prompts.md

A saved prompt is a **named instruction the user replays**: a daily report, a weekly
refresh, a long multi-skill routine. They save it once and say "run the <name> prompt".

## The file

`prompts.md` at the repo root (override with `prompts:` in
`.claude/knowledge-base.yaml`, the `MEMORY_PROMPTS_FILE` env var, or `--file`). It does
not need to exist before the first save; `kg.py init` creates it with a short preamble.

````markdown
## Daily standup
> summary: Summarise yesterday's commits and open PRs into standup notes.
<!-- tags: daily, git -->
<!-- updated: 2026-09-27 -->

Look at my commits since yesterday morning and my open PRs, and write three
bullet points: done, doing, blocked.
````

- A prompt starts with `## Name` at the start of a line. The name is what gets
  searched, so it should be what the user would say out loud.
- `> summary:` directly under it is the one-line index entry.
- `<!-- tags -->` and `<!-- updated -->` are optional and written by the script.
- Everything else is the prompt. A `## ` inside a fenced code block is body text.
- The format is the same as the job-search plugin's `workflows.md`.

**Never `Read` prompts.md.** Every access goes through `scripts/prompts.py`.

## Finding and running

| Command | Use |
|---|---|
| `prompts.py get <user's words>` | resolve to one prompt and print its text |
| `prompts.py find <words>` | ranked shortlist with scores, no bodies — when unsure |
| `prompts.py list` | every name and summary |

`get` matches in tiers — exact name, then case/punctuation-insensitive, then a
substring of the name, then keyword scoring (name 3, tag 2, summary 1 per keyword,
shared stems like "application"/"applications" count). It returns a prompt only when
one clearly wins **and** a keyword hit its name or tags. Otherwise it prints
`AMBIGUOUS`, `WEAK MATCH` or `NOT FOUND` with candidates and exits 2: ask the user.

## Saving a new prompt

The user says "save this as a prompt" / "I want to rerun this every day".

1. **Draft and generalise.** Strip what was specific to this session — today's date,
   one file, one ticket number — and keep the standing instructions: what to do,
   which skills or tools to use, when to stop and ask. If the prompt depends on
   another skill, say so explicitly ("Use the job-search skill to…") so the replay
   reaches it every time.
2. **Write the draft to a file**, not an inline argument — multi-line text with quotes
   gets mangled by shells, especially on Windows. The session scratchpad is a good
   place; never inside this plugin's directory.
3. **Propose** the name, summary and text, and ask.
4. **Show the diff, then write:**

```
python "<skill>/scripts/prompts.py" save --name "Daily standup" \
  --summary "Summarise yesterday's commits and open PRs into standup notes." \
  --tags "daily, git" --text-file "<draft>" --dry-run
python "<skill>/scripts/prompts.py" save ...same arguments without --dry-run...
```

If the name exists the script refuses with `[exists]` — offer to update that one
rather than passing `--force`.

## Updating

1. `get` it and keep the `section_hash`.
2. Propose only what actually changed — the correction the user made this session.
   Do not rewrite a hand-tuned prompt to tidy it. Prefer `--append-file` for
   additions; `--text-file` replaces the whole body.
3. `--dry-run`, show the diff, then write with `--expect-hash <hash>`. On `[stale]`
   the user edited it meanwhile: re-base on the current text it prints, and retry.

`update` and `delete` never use keyword or fuzzy matching — a guess is not good
enough to write on. `delete` also requires `--yes`, after the user confirms.

## Undo

Every write first copies prompts.md to `.claude/prompt-backups/` (last 20 kept) and
prints the path. Copying that file back over prompts.md undoes the change.

## Prompts versus the knowledge graph

| prompts.md | knowledge graph / context files |
|---|---|
| An instruction to replay: "every morning, summarise…" | A fact to apply: "the sales table is refreshed at 06:00" |
| Changes only when the user asks | Updated as learnings come up, via reviewed diffs |
