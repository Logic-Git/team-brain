"""Knowledge-base discovery and configuration.

The skill's CODE lives inside an installed plugin directory; the project's MEMORY
lives in the repo the user is working in. These must never be confused: the plugin
directory is a git clone that ``/plugin marketplace update`` hard-resets, so anything
written there is destroyed without warning.

Resolution is first-hit-wins with **no silent fall-through**: if an explicit location
is given and is wrong, that is an error, never a reason to guess somewhere else. A
mistyped KNOWLEDGE_BASE_GRAPH quietly creating a second knowledge_graph.yaml somewhere
nobody looks is the worst failure this module could have.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ENV_VAR = "KNOWLEDGE_BASE_GRAPH"
CONFIG_REL = Path(".claude") / "knowledge-base.yaml"

# Tried in order, relative to the repo root.
CONVENTIONS = (
    "inputs/memory/knowledge_graph.yaml",
    "memory/knowledge_graph.yaml",
    ".claude/memory/knowledge_graph.yaml",
    "knowledge_graph.yaml",
)

GLOB_EXCLUDE = {".git", ".venv", "venv", "node_modules", "outputs", "__pycache__",
                ".pytest_cache", "site-packages"}

ROOT_MARKERS = (".git", "CLAUDE.md", ".claude")

# scripts/lib/resolve.py -> scripts/ -> team-brain/ (skill) -> skills/ -> team-brain/ (plugin)
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
SKILL_DIR = SCRIPTS_DIR.parent
PLUGIN_ROOT = SKILL_DIR.parents[1]
TEMPLATES_DIR = SCRIPTS_DIR / "templates"

CLAUDE_MD_BEGIN = "<!-- BEGIN team-brain -->"
CLAUDE_MD_END = "<!-- END team-brain -->"
# Blocks written by the skill's earlier name. Recognised so init never appends a
# second block, and migrated in place so custom trigger nouns survive.
LEGACY_CLAUDE_MD = (
    ("<!-- BEGIN memory:knowledge-context -->", "<!-- END memory:knowledge-context -->"),
)
LEGACY_SKILL_REFS = ("/memory:knowledge-context",)
SKILL_REF = "/team-brain:team-brain"

WRITE_MODES = ("auto", "manual")
WRITE_MODE_DEFAULT = "auto"
NOUN_PLACEHOLDER = "<!-- Add this repo's own trigger nouns here"


class ResolveError(Exception):
    def __init__(self, code, message, **extra):
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra


def configure_stdio():
    """Force UTF-8. Windows consoles default to cp1252, which mangles the arrows and
    em-dashes that turn up in notes fields."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# -- tiny YAML reader ----------------------------------------------------------
# The config file is deliberately shallow (scalars plus one level of nesting), so it
# parses without PyYAML. If PyYAML is installed it is used instead.

def _mini_yaml(text):
    data = {}
    current = None
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        match = re.match(r"^(?P<indent> *)(?P<key>[A-Za-z0-9_.-]+):(?P<rest>.*)$", raw)
        if not match:
            continue
        indent = len(match.group("indent"))
        key = match.group("key")
        value = match.group("rest").split(" #", 1)[0].strip()
        if indent == 0:
            if value:
                data[key] = _scalar(value)
                current = None
            else:
                data[key] = {}
                current = key
        elif indent >= 2 and current and isinstance(data.get(current), dict):
            data[current][key] = _scalar(value)
    return data


def _scalar(value):
    value = value.strip().strip('"').strip("'")
    low = value.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if low in ("null", "none", "~", ""):
        return None
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def load_config(path):
    text = Path(path).read_text(encoding="utf-8")
    try:
        import yaml
        loaded = yaml.safe_load(text)
        return loaded if isinstance(loaded, dict) else {}
    except ImportError:
        return _mini_yaml(text)
    except Exception:
        # A malformed config should degrade to defaults, not crash retrieval.
        return _mini_yaml(text)


# -- discovery -----------------------------------------------------------------

def find_root(start=None):
    """Nearest ancestor holding a repo marker; falls back to the starting dir."""
    start = Path(start or os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd()).resolve()
    if start.is_file():
        start = start.parent
    for candidate in (start, *start.parents):
        if any((candidate / marker).exists() for marker in ROOT_MARKERS):
            return candidate
    return start


def _find_config(start):
    start = Path(start).resolve()
    for candidate in (start, *start.parents):
        config = candidate / CONFIG_REL
        if config.is_file():
            return config
    project = os.environ.get("CLAUDE_PROJECT_DIR")
    if project:
        config = Path(project) / CONFIG_REL
        if config.is_file():
            return config
    return None


def _bounded_glob(root, max_depth=4):
    hits = []
    root = Path(root)
    for path in root.rglob("knowledge_graph.yaml"):
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        if len(rel.parts) > max_depth:
            continue
        if any(part in GLOB_EXCLUDE for part in rel.parts):
            continue
        hits.append(path)
    return hits


def resolve(explicit=None, start=None):
    """Locate the knowledge base. Returns a dict; raises ResolveError if ambiguous
    or absent."""
    start = Path(start or Path.cwd()).resolve()
    root = find_root(start)
    config_path = _find_config(start)
    config = load_config(config_path) if config_path else {}
    if config_path:
        root = config_path.parent.parent

    source = None
    graph = None

    if explicit:
        graph = Path(explicit).expanduser()
        source = "--graph flag"
        if not graph.is_file():
            raise ResolveError(
                "bad_explicit_graph",
                "--graph points at {0}, which does not exist. Fix the path or drop the "
                "flag to use the configured/convention location.".format(graph),
            )
    elif os.environ.get(ENV_VAR):
        graph = Path(os.environ[ENV_VAR]).expanduser()
        source = "{0} env var".format(ENV_VAR)
        if not graph.is_file():
            raise ResolveError(
                "bad_env_graph",
                "{0} is set to {1}, which does not exist. Unset it or point it at a real "
                "knowledge_graph.yaml - refusing to guess a different location.".format(
                    ENV_VAR, graph),
            )
    elif config.get("graph"):
        graph = (root / str(config["graph"])).resolve()
        source = "config {0}".format(config_path)
        if not graph.is_file():
            raise ResolveError(
                "bad_config_graph",
                "{0} sets graph: {1}, which resolves to {2} and does not exist.".format(
                    config_path, config["graph"], graph),
            )
    else:
        for rel in CONVENTIONS:
            candidate = root / rel
            if candidate.is_file():
                graph = candidate
                source = "convention ({0})".format(rel)
                break
        if graph is None:
            hits = _bounded_glob(root)
            if len(hits) == 1:
                graph = hits[0]
                source = "search ({0})".format(hits[0].relative_to(root))
            elif len(hits) > 1:
                raise ResolveError(
                    "ambiguous_kb",
                    "Found {0} knowledge_graph.yaml files and no config to choose between "
                    "them. Set graph: in {1}, or pass --graph.".format(
                        len(hits), CONFIG_REL),
                    candidates=[str(h) for h in hits],
                )
            else:
                raise ResolveError(
                    "no_kb",
                    "No knowledge base found under {0}. Run kg.py init --root {0} to "
                    "create one.".format(root),
                    root=str(root),
                )

    graph = graph.resolve()

    if config.get("context_dir"):
        context_dir = (root / str(config["context_dir"])).resolve()
    else:
        context_dir = (graph.parent / "context").resolve()

    tools_dir = (root / str(config.get("tools_dir") or "tools")).resolve()

    instructions = None
    if config.get("instructions"):
        candidate = (root / str(config["instructions"])).resolve()
        instructions = candidate if candidate.is_file() else None

    platforms = config.get("platforms") or {}
    if not isinstance(platforms, dict):
        platforms = {}

    index_cfg = config.get("index") or {}
    if not isinstance(index_cfg, dict):
        index_cfg = {}

    naming = config.get("naming") or {}
    if not isinstance(naming, dict):
        naming = {}

    write_mode = str(config.get("write_mode") or WRITE_MODE_DEFAULT).strip().lower()
    if write_mode not in WRITE_MODES:
        write_mode = WRITE_MODE_DEFAULT

    return {
        "root": root,
        "graph": graph,
        "context_dir": context_dir,
        # `context:` values are relative to the dir that HOLDS the context folder.
        "context_base": context_dir.parent,
        "tools_dir": tools_dir,
        "config_path": config_path,
        "config": config,
        "platforms": platforms,
        "instructions": instructions,
        "index_inject": index_cfg.get("inject", True),
        "index_max_nodes": index_cfg.get("max_nodes", 600),
        "type_format": naming.get("type_format", "<platform>_<kind>"),
        "write_mode": write_mode,
        "source": source,
    }


PROMPTS_ENV_VAR = "MEMORY_PROMPTS_FILE"
PROMPTS_DEFAULT = "prompts.md"
PROMPT_BACKUPS_REL = Path(".claude") / "prompt-backups"


def resolve_prompts(explicit=None, start=None):
    """Locate the repo's saved-prompt library.

    Independent of the knowledge graph on purpose: a repo can keep saved prompts
    before it has any graph at all. The file need not exist yet (the first `save`
    creates it), so unlike resolve() a missing file is not an error - but an explicit
    location is still honoured exactly, never swapped for a guess.
    """
    start = Path(start or Path.cwd()).resolve()
    root = find_root(start)
    config_path = _find_config(start)
    config = load_config(config_path) if config_path else {}
    if config_path:
        root = config_path.parent.parent

    if explicit:
        path, source = Path(explicit).expanduser(), "--file flag"
    elif os.environ.get(PROMPTS_ENV_VAR):
        path = Path(os.environ[PROMPTS_ENV_VAR]).expanduser()
        source = "{0} env var".format(PROMPTS_ENV_VAR)
    elif config.get("prompts"):
        path = root / str(config["prompts"])
        source = "config {0}".format(config_path)
    else:
        path, source = root / PROMPTS_DEFAULT, "convention (repo root)"

    return {
        "root": root,
        "path": path.resolve(),
        "backups": root / PROMPT_BACKUPS_REL,
        "source": source,
    }


def claude_md_state(root):
    """Report how the repo's CLAUDE.md relates to this skill's trigger block."""
    path = Path(root) / "CLAUDE.md"
    if not path.is_file():
        return {"path": path, "exists": False, "has_block": False, "placeholder": False,
                "legacy": False}
    text = path.read_text(encoding="utf-8", errors="replace")
    legacy = any(b in text and e in text for b, e in LEGACY_CLAUDE_MD)
    has_block = (CLAUDE_MD_BEGIN in text and CLAUDE_MD_END in text) or legacy
    return {
        "path": path,
        "exists": True,
        "has_block": has_block,
        "placeholder": has_block and NOUN_PLACEHOLDER in text,
        "legacy": legacy,
    }


def migrate_legacy_block(text):
    """Rename an old-name trigger block in place. Returns (new_text, changed)."""
    new = text
    for (old_b, old_e) in LEGACY_CLAUDE_MD:
        new = new.replace(old_b, CLAUDE_MD_BEGIN).replace(old_e, CLAUDE_MD_END)
    for ref in LEGACY_SKILL_REFS:
        new = new.replace(ref, SKILL_REF)
    return new, new != text
