# Configuration

**`CLAUDE.md` decides *when* the skill fires. `.claude/knowledge-base.yaml` and
`memory-instructions.md` decide *how it behaves* once it has.**

That split is forced by mechanics, not taste: the router only sees this skill's
frontmatter `description`, and any file in the consuming repo is read *after* the skill
is invoked — after the decision it would have influenced. The repo's `CLAUDE.md` is the
exception, because Claude Code auto-loads it into every session in that repo, so it is
already in context when the routing decision is made.

## Triggering (CLAUDE.md)

`kg.py init` writes a block wrapped in markers:

```
<!-- BEGIN team-brain -->  ...  <!-- END team-brain -->
```

It contains a generic standing directive plus a placeholder for this repo's own nouns.
**Filling in that noun list is what makes the skill fire on domain language.** The
plugin's description is deliberately domain-neutral — it has to serve every repo — so
words like "our forecast pipeline" or "the Monday boards" only reach it if this repo
says them.

When the user asks for trigger keywords ("make the skill trigger on X"), edit between
the markers and replace the placeholder comment. Nothing does this automatically.

**Never edit this skill's own `description`.** It lives in a plugin clone that
`/plugin marketplace update` hard-resets, and it is shared by every repo and user who
installed the plugin — one repo's nouns would leak into all the others.

*Advanced:* a repo needing a hard trigger rather than a persuasive one can keep a small
local skill whose description is its own vocabulary and whose body says "invoke
`/team-brain:team-brain`". That adds a second always-resident description; only
worth it if the CLAUDE.md block is proving unreliable.

## Behaviour (.claude/knowledge-base.yaml)

Every key optional; delete the file to accept all defaults. Paths are relative to the
repo root.

| Key | Default | Purpose |
|---|---|---|
| `graph` | `inputs/memory/knowledge_graph.yaml` | where the graph lives |
| `context_dir` | `<graph dir>/context` | where context files live |
| `tools_dir` | `tools` | the repo's own executables |
| `platforms` | — | MCP aliases the substring rule gets wrong; `none` = ask instead |
| `instructions` | — | path to extra repo rules, read on invoke |
| `naming.type_format` | `<platform>_<kind>` | set `free` to disable the type lint |
| `index.inject` | `true` | `false` = do not auto-print the index |
| `index.max_nodes` | `600` | above this, print section counts instead |
| `write_mode` | `auto` | `auto` records finalized knowledge on its own; `manual` records only on request (`references/writing.md`) |
| `prompts` | `prompts.md` | the saved-prompt library (`MEMORY_PROMPTS_FILE` env var or `prompts.py --file` override it) |

Resolution order, first hit wins, **no silent fall-through** — an explicit but wrong
value is an error, never a reason to guess:
`--graph` -> `KNOWLEDGE_BASE_GRAPH` -> config file (searched up from cwd) ->
convention paths -> bounded search -> `no_kb`.

## Repo conduct (memory-instructions.md)

Pointed at by `instructions:`, read on invoke, keep under ~40 lines. For rules about
*how to use* this particular repo's memory — how to treat its notes, which entities are
easy to confuse, what to check before making a claim. Not for triggering.

## Claude Code's built-in auto memory (.claude/settings.json)

`kg.py init` sets `"autoMemoryEnabled": false` in the project's `.claude/settings.json`,
so this knowledge base is the only memory in the repo and the two never hold
overlapping notes. `kg.py init --root <repo> --settings-only` applies it to a repo set up
earlier; `--keep-auto-memory` skips it at setup. Users can also switch auto memory off
for every project with the toggle in Claude Code's `/memory` panel, or with the
`CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` environment variable.
