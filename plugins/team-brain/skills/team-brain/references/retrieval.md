# Retrieval — when the obvious lookup is not enough

## When search returns nothing

1. **Drop terms.** `search` requires *every* term to match somewhere. Two words that
   never co-occur return zero. Search the most distinctive word alone.
2. **Search the platform, not the thing.** `search bigquery returns` finds the family
   even when you do not know the table's name.
3. **Scan the index.** It is already in context. Node keys are usually snake_case and
   often near-miss the user's phrasing ("returns dashboard" -> `returns_looker_dashboard`).
4. **Search a section name** to sweep a whole area.
5. **Consider it genuinely absent.** The index lists everything, so if it is not there,
   the entity is undocumented. Say so — that is a real, useful answer — and offer to
   add it (`references/writing.md`).

## When search returns too much

Add a term, or filter by type (`search bigquery_view returns`). Prefer `--limit` low
and iterate; a wide result set is cheap to re-run and expensive to read.

## Multi-hop questions

"What breaks if X changes?" is `show X` then `show` each downstream node that looks
load-bearing. Do **not** reflexively `--depth 2`: it can pull a wide frontier for a
question that only needed one hop. Widen when a specific neighbour turns out to matter.

Follow edges, not sections. Two nodes in the same section may be unrelated; two nodes
in different sections may be directly coupled.

## When a node has no context file

Roughly half the nodes in a mature graph have `context: null`. In order:

1. **The `notes` field** — often carries the whole answer, including dated state and
   landmine markers.
2. **Connected entities** — the script that writes a table usually documents the
   table's quirks.
3. **MCP** — see the routing rule in SKILL.md. Match the platform token as a
   substring of the tool names you actually have; never assume `mcp__<platform>__*`.
4. **Say what is missing.** Name the entity, say no context file exists and no server
   covers it, and offer to record what the user tells you.

## Reading context files well

- They are freeform. Skim headings first; many are long.
- **Verbatim code is authoritative.** If a context file carries SQL or a formula, quote
  it rather than paraphrasing.
- Notes and files carry dated state ("as of 2026-07..."). Report the date alongside the
  fact rather than presenting stale state as current.
- If a file contradicts the graph, trust the file and flag the drift.

## Anomalies

If retrieval hits a dangling `context:` path, an `in`/`out` id that is not a node, or a
context file that will not open, run `kg.py validate` **then** — not routinely. See
`references/maintenance.md`.
