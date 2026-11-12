"""Parser for knowledge_graph.yaml.

The graph is a rigidly shaped document -- sections at indent 2, node keys at indent 4,
exactly five fields at indent 6, and no block scalars -- so a line parser is safe and
lets this plugin run with zero third-party dependencies. PyYAML is used when it
happens to be installed, purely as a cross-check on the same file.

Any line that does not fit the expected shape is collected as an anomaly rather than
being skipped silently: a parser that quietly drops nodes would make the whole skill
lie about what the project knows.
"""

from __future__ import annotations

import re
from pathlib import Path

FIELDS = ("type", "in", "out", "context", "notes")

_FIELD_RE = re.compile(r"^(?P<indent> *)(?P<key>[A-Za-z0-9_.-]+):(?P<rest>.*)$")


class Node:
    __slots__ = ("key", "section", "line", "type", "in_", "out", "context", "notes")

    def __init__(self, key, section, line):
        self.key = key
        self.section = section
        self.line = line
        self.type = None
        self.in_ = []
        self.out = []
        self.context = None
        self.notes = ""

    @property
    def platform(self):
        """Leading token of `type`, used to route to an MCP server."""
        if not self.type or "_" not in self.type:
            return self.type
        return self.type.split("_", 1)[0]

    @property
    def has_context(self):
        return bool(self.context)


class Graph:
    def __init__(self, path):
        self.path = Path(path)
        self.nodes = {}          # key -> Node, insertion ordered
        self.sections = {}       # section name -> [node keys]
        self.anomalies = []      # (line number, text)
        self.duplicates = []     # (key, first line, duplicate line)

    # -- lookups ---------------------------------------------------------------

    def get(self, key):
        return self.nodes.get(key)

    def context_path(self, node, context_base):
        """Absolute path of a node's context file, or None.

        `context:` values are written relative to the directory that *holds* the
        context folder (e.g. `context/foo.md` under `inputs/memory/`), which is why
        this resolves against context_base rather than the context dir itself.
        """
        if not node.context:
            return None
        return (Path(context_base) / node.context).resolve()


def _unquote(value):
    """Turn a YAML scalar into a Python string."""
    value = value.strip()
    if not value:
        return ""
    if value in ("null", "~"):
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        body = value[1:-1]
        if value[0] == '"':
            body = (
                body.replace("\\\\", "\x00")
                .replace('\\"', '"')
                .replace("\n", "\n")
                .replace("\t", "\t")
                .replace("\x00", "\\")
            )
        else:
            body = body.replace("''", "'")
        return body
    return value


def _parse_list(value):
    """Parse a YAML flow sequence: [a, b, c] or []."""
    value = value.strip()
    if not value or value in ("null", "~"):
        return []
    if not (value.startswith("[") and value.endswith("]")):
        # A bare scalar where a list was expected -- tolerate, but treat as one item.
        return [value] if value else []
    inner = value[1:-1].strip()
    if not inner:
        return []
    return [item.strip().strip("'\"") for item in inner.split(",") if item.strip()]


def parse(path):
    """Parse the graph file into a Graph. Never raises on malformed content."""
    graph = Graph(path)
    text = Path(path).read_text(encoding="utf-8")

    section = None
    node = None

    for lineno, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue

        match = _FIELD_RE.match(raw)
        if not match:
            graph.anomalies.append((lineno, raw.rstrip()[:120]))
            continue

        indent = len(match.group("indent"))
        key = match.group("key")
        rest = match.group("rest")

        if indent == 0:
            # Only `sections:` belongs at the root.
            if key != "sections":
                graph.anomalies.append((lineno, raw.rstrip()[:120]))
            section = None
            node = None
        elif indent == 2:
            section = key
            node = None
            graph.sections.setdefault(section, [])
        elif indent == 4:
            if section is None:
                graph.anomalies.append((lineno, raw.rstrip()[:120]))
                continue
            if key in graph.nodes:
                graph.duplicates.append((key, graph.nodes[key].line, lineno))
                node = graph.nodes[key]          # keep the first definition
                continue
            node = Node(key, section, lineno)
            graph.nodes[key] = node
            graph.sections[section].append(key)
        elif indent == 6:
            if node is None or key not in FIELDS:
                graph.anomalies.append((lineno, raw.rstrip()[:120]))
                continue
            if key == "type":
                node.type = _unquote(rest)
            elif key == "in":
                node.in_ = _parse_list(rest)
            elif key == "out":
                node.out = _parse_list(rest)
            elif key == "context":
                node.context = _unquote(rest)
            elif key == "notes":
                node.notes = _unquote(rest) or ""
        else:
            graph.anomalies.append((lineno, raw.rstrip()[:120]))

    return graph


def snippet(text, width=160):
    """One-line, length-capped view of a notes field."""
    if not text:
        return ""
    flat = " ".join(str(text).split())
    if len(flat) <= width:
        return flat
    return flat[: width - 1].rstrip() + "\u2026"
