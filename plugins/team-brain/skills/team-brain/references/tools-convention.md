# The `tools/` convention

This skill ships **no tools**. `tools/` belongs to the consuming repo and holds its own
executables — scrapers, exporters, API clients, loaders.

## Layout

```
tools/
  README.md              index: one line per tool
  <tool-name>/
    README.md            invocation contract: commands, flags, auth, outputs
    requirements.txt     this tool's own dependencies
    <entrypoint>.py
```

Dependencies belong to the tool, not to this skill. `kg.py` itself is stdlib-only and
lives in the plugin, not here.

## Registering a tool — the load-bearing half

**A tool that is not a node in the knowledge graph does not exist to the agent**,
because the graph is what gets searched. Adding the directory is not enough.

```yaml
  infrastructure:
    <tool_name>:
      type: python_script
      in: []
      out: [<nodes that consume its output>]
      context: context/<tool_name>.md
      notes: "What it does, which credentials or scopes it needs, when to reach for it."
```

The node key should be recognisable from the directory name. `kg.py validate` warns
about any `tools/<name>/` that no node is named after.

## What the context file must carry

- **The verbatim invocation** — the exact command line, flags and all. This is the
  single most valuable thing in the file; never paraphrase it.
- **Auth and secrets** — which credential file or env var, how it is obtained, and
  that secrets are gitignored.
- **Where output lands** — the path or table it writes.
- **Landmines** — rate limits, encoding quirks, partial-failure modes, anything that
  has bitten someone before.

## Adding a tool

Create the directory and its README, add the node and context file through Edit (diff
approval as always), wire its `out` edges to whatever consumes the output, and add a
line to `tools/README.md`.
