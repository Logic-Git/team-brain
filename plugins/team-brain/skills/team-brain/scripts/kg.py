#!/usr/bin/env python3
"""kg.py - read, search and check a project's knowledge graph.

This script is READ-ONLY over an existing knowledge base. It never edits
knowledge_graph.yaml and never edits a context file: those writes go through the
agent's Edit tool so the user keeps diff approval over their own memory. The one
exception is `init`, which scaffolds a NEW knowledge base into an empty repo.

Why a script at all, when the agent could just read the YAML? Because the YAML is
large (a mature graph runs to thousands of lines, most of it long `notes` strings)
and reading it whole costs more context than every context file the question will
actually need. `index`, `search` and `show` are the cheap ways in.

Stdlib only - no pip install, so it works the moment the plugin is installed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import graph as graphlib          # noqa: E402
from lib import promptsmd as promptslib    # noqa: E402
from lib import resolve as resolvelib      # noqa: E402

SNIPPET = 160


# -- shared helpers ------------------------------------------------------------

def _load(args):
    """Resolve the KB and parse it, or exit with a fixable message."""
    try:
        info = resolvelib.resolve(explicit=getattr(args, "graph", None))
    except resolvelib.ResolveError as err:
        print("ERROR [%s] %s" % (err.code, err.message))
        for candidate in err.extra.get("candidates", []):
            print("  candidate: %s" % candidate)
        raise SystemExit(1)
    return info, graphlib.parse(info["graph"])


def _context_files(info):
    context_dir = info["context_dir"]
    if not context_dir.is_dir():
        return []
    return sorted(p for p in context_dir.glob("*.md"))


def _mark(node):
    return " *" if node.has_context else ""


def _header(info, g):
    files = _context_files(info)
    no_context = sum(1 for n in g.nodes.values() if not n.has_context)
    print("KB: %s" % info["graph"])
    print("    %d nodes / %d sections / %d context files / %d without context"
          % (len(g.nodes), len(g.sections), len(files), no_context))
    print("    context: %s" % info["context_dir"])
    if info["config_path"]:
        print("    config: %s" % info["config_path"])
    else:
        print("    config: none (defaults)")
    print("    source: %s" % info["source"])
    print("    write mode: %s  (references/writing.md)" % info["write_mode"])
    if info["instructions"]:
        print("    repo instructions: %s  <- read this" % info["instructions"])
    problems = len(g.duplicates) + len(g.anomalies)
    if problems:
        print("    NOTE: %d structural problem(s) in the graph - run: kg.py validate"
              % problems)


# -- commands ------------------------------------------------------------------

def _print_prompts_index():
    """Saved-prompt names, so "run my X prompt" can be matched with no extra call.
    Independent of the graph: printed even when there is no knowledge base."""
    info = resolvelib.resolve_prompts()
    path = info["path"]
    if not path.is_file():
        print("PROMPTS none saved (%s does not exist yet)" % path)
        return
    sections = promptslib.parse(promptslib.read_doc(path).lines)
    print("PROMPTS %s (%d saved - fetch one with prompts.py get)" % (path, len(sections)))
    for sec in sections:
        print("  %s" % sec.name)


def cmd_locate(args):
    try:
        info, g = _load(args)
    except SystemExit:
        if args.index:
            print()
            _print_prompts_index()
        raise
    _header(info, g)
    if args.index:
        print()
        _print_index(info, g)
        print()
        _print_prompts_index()
    return 0


def _print_index(info, g):
    limit = info["index_max_nodes"]
    if len(g.nodes) > limit:
        print("INDEX suppressed: %d nodes exceeds index.max_nodes (%d)."
              % (len(g.nodes), limit))
        print("Sections (use `kg.py search <terms>` to find nodes):")
        for section, keys in g.sections.items():
            print("  %s (%d)" % (section, len(keys)))
        return
    print("INDEX (node: type; * = has a context file)")
    for section, keys in g.sections.items():
        if not keys:
            continue
        print("#%s" % section)
        for key in keys:
            node = g.nodes[key]
            print("  %s: %s%s" % (key, node.type or "?", _mark(node)))


def cmd_index(args):
    info, g = _load(args)
    _print_index(info, g)
    return 0


def _score(node, terms):
    """Rank a node against search terms. Lower is better; None means no match.

    Fields are ranked key > type > section > notes, so an exact entity name always
    beats an incidental mention inside somebody else's notes.
    """
    fields = (
        (node.key.lower(), 0),
        ((node.type or "").lower(), 2),
        (node.section.lower(), 3),
        ((node.notes or "").lower(), 4),
    )
    total = 0
    for term in terms:
        best = None
        for text, rank in fields:
            if term in text:
                if rank == 0 and text == term:
                    rank = -1          # exact key hit
                best = rank if best is None else min(best, rank)
        if best is None:
            return None
        total += best
    return total


def cmd_search(args):
    info, g = _load(args)
    terms = [t.lower() for t in args.terms if t.strip()]
    if not terms:
        print("Give at least one search term.")
        return 1

    hits = []
    for node in g.nodes.values():
        score = _score(node, terms)
        if score is not None:
            hits.append((score, node.key, node))
    hits.sort(key=lambda item: (item[0], item[1]))

    shown = hits[: args.limit]
    print('SEARCH %s - %d match(es)%s' % (
        " ".join(repr(t) for t in terms),
        len(hits),
        ", showing %d" % len(shown) if len(shown) < len(hits) else "",
    ))
    if not hits:
        print("No node matched. Try fewer or broader terms, or `kg.py index` to see "
              "the full node vocabulary.")
        return 0
    for _, key, node in shown:
        note = graphlib.snippet(node.notes, SNIPPET)
        print("%s/%s: %s%s%s" % (
            node.section, key, node.type or "?", _mark(node),
            " | " + note if note else "",
        ))
    if len(shown) < len(hits):
        print("... %d more; refine the terms or raise --limit."
              % (len(hits) - len(shown)))
    return 0


def _neighbour_line(g, key, indent="    "):
    node = g.nodes.get(key)
    if node is None:
        return "%s%s: MISSING - not a node in this graph" % (indent, key)
    note = graphlib.snippet(node.notes, SNIPPET)
    return "%s%s: %s%s%s" % (indent, key, node.type or "?", _mark(node),
                             " | " + note if note else "")


def cmd_show(args):
    info, g = _load(args)
    node = g.get(args.node)
    if node is None:
        print("No node named %r." % args.node)
        close = [k for k in g.nodes if args.node.lower() in k.lower()]
        if close:
            print("Did you mean: %s" % ", ".join(sorted(close)[:10]))
        else:
            print("Run `kg.py search %s` to look for it by content." % args.node)
        return 1

    context_path = g.context_path(node, info["context_base"])
    print("NODE %s" % node.key)
    print("  section  %s" % node.section)
    print("  type     %s  (platform: %s)" % (node.type or "?", node.platform or "?"))
    if context_path is None:
        print("  context  none - no context file yet; use notes + MCP")
    elif context_path.is_file():
        print("  context  %s" % context_path)
    else:
        print("  context  %s  [MISSING FILE - graph points at a file that is not on "
              "disk]" % context_path)
    print("  notes    %s" % (node.notes or "(none)"))

    for label, keys in (("in", node.in_), ("out", node.out)):
        if not keys:
            print("  %-3s (0): none" % label)
            continue
        print("  %-3s (%d):" % (label, len(keys)))
        for key in keys:
            print(_neighbour_line(g, key))

    if args.depth >= 2:
        frontier = set()
        for key in list(node.in_) + list(node.out):
            neighbour = g.nodes.get(key)
            if neighbour:
                frontier.update(neighbour.in_)
                frontier.update(neighbour.out)
        frontier.discard(node.key)
        frontier -= set(node.in_) | set(node.out)
        if frontier:
            print("  depth-2 (%d):" % len(frontier))
            if len(frontier) > 25:
                print("    (frontier is wide - showing 25 of %d; narrow the question "
                      "or inspect specific nodes)" % len(frontier))
            for key in sorted(frontier)[:25]:
                print(_neighbour_line(g, key))
    return 0


def cmd_validate(args):
    info, g = _load(args)
    files = _context_files(info)
    findings = []

    for key, first, dup in g.duplicates:
        findings.append((
            "duplicate-key",
            "%s is defined twice (line %d and line %d). Node keys are global ids - "
            "`in`/`out` reference them by bare name, so an edge pointing here is "
            "ambiguous. Merge the two definitions into one." % (key, first, dup),
        ))

    for lineno, text in g.anomalies:
        findings.append((
            "parse-anomaly",
            "line %d does not fit the expected shape: %s" % (lineno, text),
        ))

    known = set(g.nodes)
    for node in g.nodes.values():
        for label, keys in (("in", node.in_), ("out", node.out)):
            for key in keys:
                if key not in known:
                    findings.append((
                        "unknown-ref",
                        "%s.%s lists %r, which is not a node in this graph."
                        % (node.key, label, key),
                    ))

    for node in g.nodes.values():
        for key in node.out:
            other = g.nodes.get(key)
            if other is not None and node.key not in other.in_:
                findings.append((
                    "asymmetric-link",
                    "%s.out contains %s, but %s.in does not contain %s."
                    % (node.key, key, key, node.key),
                ))
        for key in node.in_:
            other = g.nodes.get(key)
            if other is not None and node.key not in other.out:
                findings.append((
                    "asymmetric-link",
                    "%s.in contains %s, but %s.out does not contain %s."
                    % (node.key, key, key, node.key),
                ))

    referenced = set()
    for node in g.nodes.values():
        path = g.context_path(node, info["context_base"])
        if path is None:
            continue
        referenced.add(path)
        if not path.is_file():
            findings.append((
                "dangling-context",
                "%s points at %s, which is not on disk. Either create the file or set "
                "context: null." % (node.key, node.context),
            ))

    for path in files:
        if path.resolve() not in referenced:
            findings.append((
                "orphan-context",
                "%s exists but no node references it. Add a node, or delete the file."
                % path.name,
            ))

    if info["type_format"] != "free":
        for node in g.nodes.values():
            if not node.type or "_" not in node.type:
                findings.append((
                    "type-format",
                    "%s has type %r, which is not <platform>_<kind>. The platform "
                    "prefix is what routes to an MCP server."
                    % (node.key, node.type),
                ))

    tools_dir = info["tools_dir"]
    if tools_dir.is_dir():
        keys_lower = {k.lower() for k in g.nodes}
        for child in sorted(tools_dir.iterdir()):
            if not child.is_dir() or child.name.startswith((".", "__")):
                continue
            name = child.name.lower().replace("-", "_")
            # A tool directory is registered if some node is named after it. The node
            # usually carries a suffix (tools/gmail/ -> gmail_read_tool), so match on
            # containment rather than equality.
            if any(name == key or name in key.split("_") or name in key
                   for key in keys_lower):
                continue
            findings.append((
                "unregistered-tool",
                "tools/%s/ exists but no node in the graph is named after it, so the "
                "agent will never find it. Add a node keyed %s."
                % (child.name, child.name),
            ))

    grouped = {}
    for kind, message in findings:
        grouped.setdefault(kind, []).append(message)

    no_context = sum(1 for n in g.nodes.values() if not n.has_context)
    print("VALIDATE %s" % info["graph"])
    print("  %d nodes / %d sections / %d context files" %
          (len(g.nodes), len(g.sections), len(files)))
    print("  coverage: %d of %d nodes have a context file (%d without)"
          % (len(g.nodes) - no_context, len(g.nodes), no_context))
    print()
    if not findings:
        print("No problems found.")
        return 0

    print("%d finding(s):" % len(findings))
    for kind in sorted(grouped):
        messages = grouped[kind]
        print("\n%s (%d)" % (kind.upper(), len(messages)))
        for message in messages[: args.limit]:
            print("  - %s" % message)
        if len(messages) > args.limit:
            print("  ... %d more (raise --limit to see them all)"
                  % (len(messages) - args.limit))
    print("\nFix guidance: references/maintenance.md")
    return 0


def cmd_doctor(args):
    """Diagnose why the skill did not fire when the user expected it to."""
    print("DOCTOR - why the team-brain skill may not have triggered\n")

    try:
        info = resolvelib.resolve(explicit=getattr(args, "graph", None))
    except resolvelib.ResolveError as err:
        print("[X] knowledge base: NOT RESOLVED (%s)" % err.code)
        print("    %s" % err.message)
        return 0

    g = graphlib.parse(info["graph"])
    print("[ok] knowledge base: %d nodes at %s" % (len(g.nodes), info["graph"]))

    state = resolvelib.claude_md_state(info["root"])
    if not state["exists"]:
        print("[X] CLAUDE.md: missing at %s" % state["path"])
        print("    This is the main reason the skill silently never fires. The")
        print("    plugin description alone is domain-neutral; the repo's CLAUDE.md is")
        print("    what names THIS repo's entities and tells the agent to look them up.")
        print("    Fix: kg.py init --root \"%s\" --claude-md-only" % info["root"])
    elif not state["has_block"]:
        print("[X] CLAUDE.md: exists but has no team-brain block")
        print("    Fix: kg.py init --root \"%s\" --claude-md-only  (appends, never"
              % info["root"])
        print("    overwrites - your existing CLAUDE.md content is preserved)")
    elif state["legacy"]:
        print("[X] CLAUDE.md: still carries the old memory:knowledge-context block, which")
        print("    invokes a skill name that no longer exists.")
        print("    Fix: kg.py init --root \"%s\" --claude-md-only  (renames it in place;"
              % info["root"])
        print("    your custom trigger nouns are kept)")
    elif state["placeholder"]:
        print("[!] CLAUDE.md: block present, but the trigger nouns are still the")
        print("    placeholder. The generic directive works, but the skill will miss")
        print("    questions that name this repo's entities in domain words.")
        print("    Fix: edit between the BEGIN/END markers in %s and list the things"
              % state["path"])
        print("    this repo actually contains. Sections in this graph: %s"
              % ", ".join(list(g.sections)[:8]) +
              (", ..." if len(g.sections) > 8 else ""))
    else:
        print("[ok] CLAUDE.md: trigger block present and customised")

    competing = [info["root"] / ".claude" / "skills" / name
                 for name in ("knowledge-context", "team-brain", "personal-memory")]
    competing = [p for p in competing if p.is_dir()]
    for local_skill in competing:
        print("[!] a local project skill still exists at %s" % local_skill)
        print("    It competes with the plugin for the same triggers and its copy of")
        print("    the instructions may be older. Remove it, or set")
        print("    disable-model-invocation: true in its frontmatter.")
    if not competing:
        print("[ok] no competing local memory skill")

    auto = _auto_memory_state(info["root"])
    if auto is False:
        print("[ok] Claude Code built-in auto memory: off for this project")
    else:
        print("[!] Claude Code built-in auto memory: not turned off for this project, so")
        print("    a second memory competes with this one.")
        print("    Fix: kg.py init --root \"%s\" --settings-only  (or set" % info["root"])
        print("    \"autoMemoryEnabled\": false in .claude/settings.local.json for just you)")

    if info["config_path"]:
        print("[ok] config: %s" % info["config_path"])
    else:
        print("[ok] config: none (defaults) - fine unless paths are non-standard")

    print("\nIf all of the above are ok and the skill still did not fire, the question")
    print("probably named no entity the description recognises. Add those words to the")
    print("CLAUDE.md block - that is the per-repo trigger surface.")
    return 0


# -- init ----------------------------------------------------------------------

def _read_template(name):
    path = resolvelib.TEMPLATES_DIR / name
    return path.read_text(encoding="utf-8")


def _write(path, text):
    """Write without newline translation.

    Python's text mode would rewrite every \\n as \\r\\n on Windows, which silently
    converts an existing file's line endings and turns a twenty-line append into a
    whole-file diff. Line endings are decided here, not by the platform.
    """
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


SETTINGS_REL = Path(".claude") / "settings.json"


def _auto_memory_state(root):
    """autoMemoryEnabled for the project: .claude/settings.local.json (personal,
    gitignored) wins over .claude/settings.json (shared). None if neither sets it."""
    for rel in (Path(".claude") / "settings.local.json", SETTINGS_REL):
        path = Path(root) / rel
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8") or "{}")
        except ValueError:
            continue
        if isinstance(data, dict) and "autoMemoryEnabled" in data:
            return data["autoMemoryEnabled"]
    return None


def _write_settings(root, created):
    """Turn off Claude Code's built-in auto memory for this project, so all memory
    goes through this skill. Merges into an existing settings.json; never removes
    other keys; refuses to touch a file it cannot parse."""
    path = Path(root) / SETTINGS_REL
    data = {}
    existed = path.is_file()
    if existed:
        text = path.read_text(encoding="utf-8")
        try:
            data = json.loads(text) if text.strip() else {}
        except ValueError:
            created.append(("NOT CHANGED (invalid JSON - add the key by hand)", path))
            return
        if not isinstance(data, dict):
            created.append(("NOT CHANGED (not a JSON object)", path))
            return
        if data.get("autoMemoryEnabled") is False:
            created.append(("skipped (auto memory already off)", path))
            return
    path.parent.mkdir(parents=True, exist_ok=True)
    data["autoMemoryEnabled"] = False
    _write(path, json.dumps(data, indent=2) + "\n")
    created.append(("set autoMemoryEnabled: false" if existed
                    else "created (auto memory off)", path))


def _write_claude_md(root, created):
    """Create CLAUDE.md with the trigger block, or append the block to an existing
    one. Never overwrites, never duplicates, never reflows what is already there."""
    path = Path(root) / "CLAUDE.md"
    block = _read_template("claude-md-block.md.template")

    if not path.is_file():
        _write(path, "# %s\n\n%s" % (Path(root).name, block))
        created.append(("created", path))
        return

    # newline="" keeps the file's own endings intact in the string we read back.
    with open(path, "r", encoding="utf-8", newline="") as handle:
        text = handle.read()

    if resolvelib.CLAUDE_MD_BEGIN in text:
        created.append(("skipped (block already present)", path))
        return

    migrated, changed = resolvelib.migrate_legacy_block(text)
    if changed:
        _write(path, migrated)
        created.append(("migrated old-name block in place", path))
        return

    # Match the file's existing convention rather than imposing ours.
    eol = "\r\n" if "\r\n" in text else "\n"
    block = block.replace("\r\n", "\n").replace("\n", eol)

    if text.endswith(eol * 2):
        separator = ""
    elif text.endswith(eol):
        separator = eol
    else:
        separator = eol * 2

    _write(path, text + separator + block)
    created.append(("appended block", path))


def cmd_init(args):
    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print("ERROR --root %s is not a directory. Create it first, or point at the "
              "repo you mean." % root)
        return 1

    created = []

    if args.claude_md_only:
        _write_claude_md(root, created)
    elif args.settings_only:
        _write_settings(root, created)
    else:
        memory = root / "inputs" / "memory"
        context = memory / "context"
        graph_path = memory / "knowledge_graph.yaml"

        context.mkdir(parents=True, exist_ok=True)
        keep = context / ".gitkeep"
        if not keep.exists():
            _write(keep, "")

        if graph_path.exists():
            created.append(("skipped (already exists)", graph_path))
        else:
            _write(graph_path, _read_template("knowledge_graph.yaml.template"))
            created.append(("created", graph_path))

        config = root / ".claude" / "knowledge-base.yaml"
        config.parent.mkdir(parents=True, exist_ok=True)
        if config.exists():
            created.append(("skipped (already exists)", config))
        else:
            _write(config, _read_template("knowledge-base.yaml.template"))
            created.append(("created", config))

        tools_readme = root / "tools" / "README.md"
        tools_readme.parent.mkdir(parents=True, exist_ok=True)
        if tools_readme.exists():
            created.append(("skipped (already exists)", tools_readme))
        else:
            _write(tools_readme, _read_template("tools-README.md.template"))
            created.append(("created", tools_readme))

        prompts = root / resolvelib.PROMPTS_DEFAULT
        if prompts.exists():
            created.append(("skipped (already exists)", prompts))
        else:
            _write(prompts, _read_template("prompts.md.template"))
            created.append(("created", prompts))

        _write_claude_md(root, created)
        if not args.keep_auto_memory:
            _write_settings(root, created)

    print("INIT %s" % root)
    for action, path in created:
        print("  %-32s %s" % (action, path))

    if not (args.claude_md_only or args.settings_only):
        print("\nAdd to .gitignore if inputs/ is ignored (git cannot re-include a path")
        print("under an ignored parent, so the whole chain is needed):\n")
        print("  inputs/*")
        print("  !inputs/memory/")
        print("  inputs/memory/*")
        print("  !inputs/memory/knowledge_graph.yaml")
        print("  !inputs/memory/context/")
        print("\nOptional - to offer this plugin to everyone who clones the repo, add to")
        print(".claude/settings.json (or use your organisation's own marketplace):\n")
        print('  "extraKnownMarketplaces": {"team-brain": {"source":')
        print('     {"source": "github", "repo": "Logic-Git/team-brain"}}},')
        print('  "enabledPlugins": {"team-brain@team-brain": true}')
        print("\nNext: seed the graph. Ask the user what this repo does, propose 5-10")
        print("starting entities, and write them with the Edit tool (see")
        print("references/setup.md). An empty graph nobody fills is the usual failure.")
    return 0


# -- cli -----------------------------------------------------------------------

def main(argv=None):
    resolvelib.configure_stdio()
    parser = argparse.ArgumentParser(
        prog="kg.py", description="Read and check a project knowledge graph.")
    parser.add_argument("--graph", help="explicit path to knowledge_graph.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("locate", help="resolve the knowledge base and report on it")
    p.add_argument("--index", action="store_true", help="also print the node index")
    p.set_defaults(func=cmd_locate)

    p = sub.add_parser("index", help="print the node index (cheap table of contents)")
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("search", help="find nodes by key, type, section or notes")
    p.add_argument("terms", nargs="+")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("show", help="print one node in full, plus its neighbours")
    p.add_argument("node")
    p.add_argument("--depth", type=int, default=1, help="1 = direct neighbours")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("validate", help="check the graph for structural problems")
    p.add_argument("--limit", type=int, default=20,
                   help="max findings to print per category")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("doctor", help="diagnose why the skill did not trigger")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("init", help="scaffold a knowledge base into a repo")
    p.add_argument("--root", required=True,
                   help="the repo to scaffold (explicit on purpose)")
    p.add_argument("--claude-md-only", action="store_true",
                   help="only add (or migrate) the CLAUDE.md trigger block")
    p.add_argument("--settings-only", action="store_true",
                   help="only turn off Claude Code's built-in auto memory for the repo")
    p.add_argument("--keep-auto-memory", action="store_true",
                   help="do not turn off Claude Code's built-in auto memory")
    p.set_defaults(func=cmd_init)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
