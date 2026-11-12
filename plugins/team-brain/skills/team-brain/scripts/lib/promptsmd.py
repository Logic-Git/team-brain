"""Parser, matcher and splice-writer for a repo's prompts.md saved-prompt library.

Same grammar as the job-search plugin's workflows.md, so a user who knows one knows
both. The file is hand-edited, so every write is a splice: the lines outside the one
section being changed pass through byte for byte, line endings and all.

Grammar:
    ## Name                       <- a prompt starts here (column 0, not in a fence)
    > summary: one line           <- the cheap index
    <!-- tags: a, b -->           <- optional
    <!-- updated: YYYY-MM-DD -->  <- optional
    ...anything else is the prompt body...

Everything before the first heading is preamble and is preserved verbatim.
"""

from __future__ import annotations

import difflib
import hashlib
import os
import re
from datetime import datetime
from pathlib import Path

HEADING_RE = re.compile(r"^##[ \t]+(.+?)[ \t]*$")
SUMMARY_RE = re.compile(r"^>[ \t]*summary[ \t]*:[ \t]*(.*)$", re.IGNORECASE)
TAGS_RE = re.compile(r"^<!--[ \t]*tags[ \t]*:[ \t]*(.*?)[ \t]*-->[ \t]*$", re.IGNORECASE)
UPDATED_RE = re.compile(r"^<!--[ \t]*updated[ \t]*:[ \t]*(.*?)[ \t]*-->[ \t]*$",
                        re.IGNORECASE)
FENCE_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")


class Section:
    __slots__ = ("name", "summary", "tags", "updated", "start", "end", "lines", "body")

    def __init__(self, name, summary, tags, updated, start, end, lines, body):
        self.name = name
        self.summary = summary
        self.tags = tags
        self.updated = updated
        self.start = start      # index of the '## ' line
        self.end = end          # exclusive
        self.lines = lines
        self.body = body

    @property
    def hash(self):
        return hashlib.sha256("".join(self.lines).encode("utf-8")).hexdigest()[:12]

    @property
    def words(self):
        return len(self.body.split())

    @property
    def index_line(self):
        return self.summary if self.summary else synth_summary(self.body)


class Doc:
    __slots__ = ("path", "lines", "bom", "newline", "exists")

    def __init__(self, path, lines, bom, newline, exists):
        self.path = path
        self.lines = lines      # WITH original line endings
        self.bom = bom
        self.newline = newline
        self.exists = exists

    @property
    def text(self):
        return "".join(self.lines)


def _strip_eol(line):
    return line.rstrip("\r\n")


def read_doc(path, default_preamble=""):
    """Read prompts.md, remembering how it was encoded so a write puts it back the
    same way (a Notepad BOM and CRLF endings both survive a round trip)."""
    path = Path(path)
    if not path.is_file():
        lines = default_preamble.splitlines(keepends=True)
        return Doc(path, lines, False, "\n", False)
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    if bom:
        raw = raw[3:]
    text = raw.decode("utf-8", errors="replace")
    crlf = text.count("\r\n")
    newline = "\r\n" if crlf > text.count("\n") - crlf else "\n"
    return Doc(path, text.splitlines(keepends=True), bom, newline, True)


def parse(lines):
    """Split the document into prompt sections.

    Fence-aware: a '## ' line inside a fenced code block is body text, not a new
    prompt. Saved prompts routinely contain fenced examples, so this is not optional.
    """
    starts = []
    fence_char, fence_len = "", 0
    for i, raw in enumerate(lines):
        line = _strip_eol(raw)
        m_fence = FENCE_RE.match(line)
        if m_fence:
            marker = m_fence.group(1)
            if not fence_char:
                fence_char, fence_len = marker[0], len(marker)
                continue
            if marker[0] == fence_char and len(marker) >= fence_len:
                fence_char, fence_len = "", 0
                continue
        if fence_char:
            continue
        m = HEADING_RE.match(line)
        if m:
            starts.append((i, m.group(1).strip()))

    sections = []
    for n, (idx, name) in enumerate(starts):
        end = starts[n + 1][0] if n + 1 < len(starts) else len(lines)
        sec_lines = lines[idx:end]
        summary, tags, updated, body = _parse_section_body(sec_lines)
        sections.append(Section(name, summary, tags, updated, idx, end, sec_lines, body))
    return sections


def _parse_section_body(sec_lines):
    summary = updated = None
    tags = []
    body_lines = []
    for raw in sec_lines[1:]:
        line = _strip_eol(raw)
        if summary is None:
            m = SUMMARY_RE.match(line)
            if m:
                summary = m.group(1).strip()
                continue
        m = TAGS_RE.match(line)
        if m:
            tags = [t.strip() for t in m.group(1).split(",") if t.strip()]
            continue
        m = UPDATED_RE.match(line)
        if m:
            updated = m.group(1).strip()
            continue
        body_lines.append(raw)
    return summary, tags, updated, "".join(body_lines).strip()


def synth_summary(body, limit=120):
    """Stand-in index line for a hand-added prompt with no `> summary:`."""
    for line in body.splitlines():
        s = line.strip()
        if not s or s.startswith(("<!--", "#", "```", "~~~")):
            continue
        s = re.sub(r"^[-*+]\s+", "", s)
        return s if len(s) <= limit else s[: limit - 1] + "…"
    return "(empty)"


# -- matching ------------------------------------------------------------------

# Words that say "run a saved prompt" without saying which one. Stripped from the
# query so "please rerun my daily standup prompt" matches a prompt named "Daily
# standup". Deliberately excludes cadence words like "daily" and "weekly": those are
# often the most distinctive part of a prompt's name.
FILLER = {
    "a", "again", "an", "and", "can", "could", "do", "execute", "for", "go", "it",
    "kick", "launch", "me", "my", "now", "of", "off", "on", "our", "please", "pls",
    "prompt", "prompts", "re", "rerun", "run", "saved", "start", "that", "the",
    "this", "to", "trigger", "use", "would", "you",
}


def norm(s):
    """Fold for matching: case, punctuation and spacing all ignored."""
    folded = (s or "").casefold()
    return " ".join("".join(ch if ch.isalnum() else " " for ch in folded).split())


def keywords(query):
    return [t for t in norm(query).split() if t not in FILLER]


def _tok_match(q, t):
    """Whole token, or a shared stem of 4+ characters ("applications" ~ "application")."""
    if q == t:
        return True
    if len(q) >= 4 and len(t) >= 4:
        return t.startswith(q) or q.startswith(t)
    return False


def score(section, terms):
    """Score one prompt against query keywords; None means no keyword matched.

    Each keyword counts once, at its best field: name 3, tag 2, summary 1. A small
    bonus for how much of the NAME the query covers breaks ties toward the prompt
    whose name the user actually said.
    """
    name_t = norm(section.name).split()
    tag_t = norm(" ".join(section.tags)).split()
    sum_t = norm(section.index_line).split()
    total, name_hits = 0.0, set()
    for q in terms:
        best = 0
        for i, t in enumerate(name_t):
            if _tok_match(q, t):
                best = 3
                name_hits.add(i)
        if best < 2 and any(_tok_match(q, t) for t in tag_t):
            best = 2
        if best < 1 and any(_tok_match(q, t) for t in sum_t):
            best = 1
        total += best
    if total == 0:
        return None
    if name_t:
        total += len(name_hits) / len(name_t)
    return total


def _named(section, terms):
    """True if some keyword hit the prompt's name or tags, not only its summary."""
    own = norm(section.name + " " + " ".join(section.tags)).split()
    return any(_tok_match(q, t) for q in terms for t in own)


def rank(sections, query):
    terms = keywords(query)
    scored = []
    for s in sections:
        sc = score(s, terms)
        if sc is not None:
            scored.append((sc, s))
    scored.sort(key=lambda t: (-t[0], t[1].name.casefold()))
    return scored


def resolve(query, sections, max_tier):
    """Match a user's words to one prompt. Returns (matches, tier).

    Tiers: exact, normalized, substring, keyword, fuzzy. `max_tier` caps how loose a
    match may be: mutating commands stop at substring, because editing the wrong
    prompt on a guess is worse than asking.
    """
    hits = [s for s in sections if s.name == query]
    if hits:
        return hits, "exact"

    nq = norm(query)
    stripped = " ".join(keywords(query))
    keys = [k for k in dict.fromkeys((nq, stripped)) if k]

    for key in keys:
        hits = [s for s in sections if norm(s.name) == key]
        if hits:
            return hits, "normalized"
    if max_tier < 3:
        return [], None

    for key in keys:
        hits = [s for s in sections if key in norm(s.name)]
        if hits:
            return hits, "substring"
    if max_tier < 4:
        return [], None

    ranked = rank(sections, query)
    if ranked:
        best = ranked[0][0]
        runner = ranked[1][0] if len(ranked) > 1 else 0.0
        # Confident only when the winner hit its name or tags (not just its summary)
        # and clearly beats the next one. Otherwise hand back the shortlist as
        # "weak": the caller must confirm with the user even if it holds one prompt.
        if _named(ranked[0][1], keywords(query)) and best - runner >= 1.5:
            return [ranked[0][1]], "keyword"
        return [s for sc, s in ranked if best - sc < 1.5], "weak"

    if stripped and sections:
        scored = sorted(((difflib.SequenceMatcher(None, stripped, norm(s.name)).ratio(), s)
                         for s in sections), key=lambda t: -t[0])
        best = scored[0][0]
        runner = scored[1][0] if len(scored) > 1 else 0.0
        if best >= 0.80 and best - runner >= 0.10:
            return [scored[0][1]], "fuzzy"
    return [], None


def closest(query, sections, n=3):
    key = " ".join(keywords(query)) or norm(query)
    scored = sorted(((difflib.SequenceMatcher(None, key, norm(s.name)).ratio(), s)
                     for s in sections), key=lambda t: -t[0])
    return [s for _, s in scored[:n]]


# -- writing -------------------------------------------------------------------

def render_section(name, summary, body, tags, updated, newline):
    """One prompt as lines ready to splice in; always ends with one blank line."""
    out = ["## %s" % name.strip(), "> summary: %s" % (summary or "").strip()]
    if tags:
        out.append("<!-- tags: %s -->" % ", ".join(t.strip() for t in tags if t.strip()))
    if updated:
        out.append("<!-- updated: %s -->" % updated.strip())
    out.append("")
    out.extend((body or "").strip().splitlines() or [""])
    out.append("")
    return [line + newline for line in out]


def splice(lines, start, end, new_lines):
    """Replace lines[start:end]; everything else passes through untouched."""
    return lines[:start] + list(new_lines) + lines[end:]


def append_section(doc, new_lines):
    lines = list(doc.lines)
    while lines and not _strip_eol(lines[-1]).strip():
        lines.pop()
    if lines:
        if not lines[-1].endswith(("\n", "\r")):
            lines[-1] += doc.newline
        lines.append(doc.newline)
    return lines + list(new_lines)


def write_doc(path, lines, bom):
    """Atomic replace: temp file then os.replace, so a killed process never leaves a
    half-written prompt library behind."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = "".join(lines).encode("utf-8")
    if bom:
        data = b"\xef\xbb\xbf" + data
    tmp = path.with_name(path.name + ".tmp-%d" % os.getpid())
    try:
        tmp.write_bytes(data)
        os.replace(str(tmp), str(path))
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def backup(path, backups_dir, keep=20):
    """Copy the current file aside before a write and prune old copies. Returns the
    backup path so the agent can tell the user exactly how to undo."""
    path = Path(path)
    if not path.is_file():
        return None
    backups_dir = Path(backups_dir)
    backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = backups_dir / ("prompts-%s.md" % stamp)
    n = 1
    while dest.exists():
        dest = backups_dir / ("prompts-%s-%d.md" % (stamp, n))
        n += 1
    dest.write_bytes(path.read_bytes())
    for old in sorted(backups_dir.glob("prompts-*.md"), reverse=True)[keep:]:
        try:
            old.unlink()
        except OSError:
            pass
    return dest


def unified_diff(before, after, path):
    name = Path(path).name
    return "".join(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile="a/%s" % name, tofile="b/%s" % name, n=3,
    ))
