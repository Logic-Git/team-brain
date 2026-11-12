# Maintenance

## When to run the validator

`kg.py validate` is **not** part of normal retrieval — it would cost tokens on every
question to catch a problem that appears rarely. Run it:

- when the user asks for a health check;
- **on anomaly** — retrieval hit a dangling `context:` path, an `in`/`out` id that is
  not a node, or a context file that will not open;
- **after writing** to the graph, since that is when link symmetry breaks.

The graph is maintained by the agent editing YAML, so drift is silent by construction.
That is exactly why the check exists — and why it does not need to run constantly.

## Findings and fixes

| Finding | What it means | Fix |
|---|---|---|
| `asymmetric-link` | A lists B in `out`, B does not list A in `in` | Add the missing side. Confirm the direction first — the fix is whichever side is true. |
| `unknown-ref` | An edge points at a node key that does not exist | The target was renamed or never added. Repoint the edge, or add the node. |
| `dangling-context` | `context:` names a file not on disk | Create the file, or set `context: null`. Never leave it pointing at nothing. |
| `orphan-context` | A file nothing references | Add a node for it, or delete the file. Usually a node was removed and the file was left. |
| `duplicate-key` | The same key defined in two sections | Merge into one node. Keys are global ids; edges to a duplicate are ambiguous. Keep the fuller definition and fold in the other's unique edges. |
| `type-format` | `type` is not `<platform>_<kind>` | Rename to the convention — the prefix is what routes to MCP. Set `naming.type_format: free` to opt out. |
| `parse-anomaly` | A line does not fit the expected shape | Usually hand-editing damage. Compare against a healthy node; the parser expects 2/4/6-space indents and exactly the five fields. |
| `unregistered-tool` | `tools/<name>/` with no node named after it | Add the node (`references/tools-convention.md`), or remove the directory. |

Fix findings, do not suppress them. An `orphan-context` file often holds real knowledge
that simply lost its node.

## Backfilling `context: null`

Half the nodes in a mature graph have no context file, which is normal — the `notes`
hint plus MCP covers most questions. Worth backfilling when an entity keeps coming up,
when its behaviour is surprising enough that notes cannot hold it, or when it carries
verbatim code someone will need again.

Do not bulk-generate context files. A file restating what MCP answers live is worse
than no file, because it goes stale and will be believed.

## Health check

`kg.py validate` for structure, then look at coverage: which heavily-connected nodes
still have `context: null`. Those are the highest-value gaps — a hub with no
documentation is where retrieval will fail first.
