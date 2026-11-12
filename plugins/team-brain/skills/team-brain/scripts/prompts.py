#!/usr/bin/env python3
"""prompts.py - the repo's saved-prompt library (prompts.md at the repo root).

A saved prompt is a named instruction the user replays: "run my daily standup prompt"
instead of retyping it. This script is how the agent reaches ONE prompt without
reading the whole file into context.

    prompts.py list                                    # cheap index: names + summaries
    prompts.py find <words...>                         # ranked keyword search, no bodies
    prompts.py get "<the user's words>"                # resolve to one prompt, print it
    prompts.py save --name N --summary S --text-file F [--tags a,b] [--dry-run]
    prompts.py update --name N (--text-file F | --append-file F | --summary S | --tags T)
                      --expect-hash H [--dry-run]
    prompts.py delete --name N --yes

`get` accepts the user's phrasing as-is: filler like "run", "my", "prompt", "again"
is stripped, and the rest is matched against names, tags and summaries.

Exit codes: 0 ok, 1 error, 2 needs the user (ambiguous, weak or missing match).
Stdlib only.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import promptsmd as pm            # noqa: E402
from lib import resolve as resolvelib      # noqa: E402

NEEDS_USER = 2


def _default_preamble():
    return (resolvelib.TEMPLATES_DIR / "prompts.md.template").read_text(encoding="utf-8")


def _load(args):
    info = resolvelib.resolve_prompts(explicit=args.file)
    doc = pm.read_doc(info["path"], _default_preamble())
    return info, doc, pm.parse(doc.lines)


def _brief(sec):
    tags = "  [%s]" % ", ".join(sec.tags) if sec.tags else ""
    return "%s - %s%s" % (sec.name, sec.index_line, tags)


def _read_text(args, attr):
    """Prompt bodies come from files: multi-line text with quotes and dashes gets
    mangled passing through a Windows shell."""
    name = getattr(args, attr, None)
    if not name:
        return None
    path = Path(name).expanduser()
    if not path.is_file():
        print("ERROR [not_found] no such text file: %s" % path)
        raise SystemExit(1)
    return path.read_text(encoding="utf-8-sig")


def _commit(info, doc, new_lines, action, name, dry_run):
    before, after = doc.text, "".join(new_lines)
    if dry_run:
        print("DRY RUN %s '%s' in %s - nothing written" % (action, name, info["path"]))
        print(pm.unified_diff(before, after, info["path"]) or "(no change)")
        return 0
    bak = pm.backup(info["path"], info["backups"])
    pm.write_doc(info["path"], new_lines, doc.bom)
    print("%s '%s' in %s" % (action.upper(), name, info["path"]))
    if bak:
        print("  backup: %s  (copy it back over prompts.md to undo)" % bak)
    fresh = pm.parse(pm.read_doc(info["path"]).lines)
    match = next((s for s in fresh if s.name == name), None)
    if match is not None:
        print("  section_hash: %s" % match.hash)
    return 0


def _resolve_or_report(args, query, sections, info, max_tier):
    """Resolve to exactly one prompt, or print what the user must choose and return
    None. Never picks between candidates on the agent's behalf."""
    if not sections:
        print("NO PROMPTS - %s has no saved prompts yet." % info["path"])
        print("Offer to save one when the user has a prompt worth replaying.")
        return None, None
    matches, tier = pm.resolve(query, sections, max_tier)
    if len(matches) == 1 and tier != "weak":
        return matches[0], tier
    if matches:
        if len(matches) == 1:
            print("WEAK MATCH - '%s' only matched this prompt's summary; confirm with "
                  "the user before running it:" % query)
        else:
            print("AMBIGUOUS - '%s' could be any of these; ask the user which one:"
                  % query)
        for s in matches[:8]:
            print("  %s" % _brief(s))
    else:
        print("NOT FOUND - no saved prompt matches '%s'." % query)
        print("Closest:")
        for s in pm.closest(query, sections):
            print("  %s" % _brief(s))
        print("Ask the user, or offer to save this as a new prompt.")
    return None, None


# -- commands ------------------------------------------------------------------

def cmd_list(args):
    info, doc, sections = _load(args)
    print("PROMPTS %s (%d saved)%s" % (info["path"], len(sections),
                                       "" if doc.exists else " - file not created yet"))
    for s in sections:
        print("  %s" % _brief(s))
    return 0


def cmd_find(args):
    info, _doc, sections = _load(args)
    query = " ".join(args.terms)
    ranked = pm.rank(sections, query)
    print("FIND %r in %s - %d match(es)" % (query, info["path"], len(ranked)))
    for sc, s in ranked[: args.limit]:
        print("  %.1f  %s" % (sc, _brief(s)))
    if not ranked:
        print("No prompt matched. Run `prompts.py list` to see every name.")
    return 0


def cmd_get(args):
    info, _doc, sections = _load(args)
    query = " ".join(args.query)
    sec, tier = _resolve_or_report(args, query, sections, info,
                                   max_tier=1 if args.exact else 5)
    if sec is None:
        return NEEDS_USER
    print("PROMPT %s" % sec.name)
    print("  matched: %s%s" % (tier, "" if tier == "exact"
                               else " - tell the user which saved prompt you are running"))
    print("  summary: %s" % sec.index_line)
    if sec.tags:
        print("  tags: %s" % ", ".join(sec.tags))
    if sec.updated:
        print("  updated: %s" % sec.updated)
    print("  section_hash: %s" % sec.hash)
    print("  file: %s" % info["path"])
    if not args.no_text:
        print("----- BEGIN SAVED PROMPT -----")
        print(sec.body)
        print("----- END SAVED PROMPT -----")
    return 0


def cmd_save(args):
    info, doc, sections = _load(args)
    existing, _ = pm.resolve(args.name, sections, max_tier=2)
    if existing and not args.force:
        print("ERROR [exists] a prompt called '%s' already exists (section_hash %s)."
              % (existing[0].name, existing[0].hash))
        print("Update it instead, or pass --force to replace it.")
        return 1
    body = _read_text(args, "text_file") or args.text
    if not body or not body.strip():
        print("ERROR [bad_args] provide the prompt with --text-file (preferred) or --text.")
        return 1
    tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]
    rendered = pm.render_section(args.name, args.summary, body, tags,
                                 date.today().isoformat(), doc.newline)
    if existing:
        sec = existing[0]
        new_lines, action = pm.splice(doc.lines, sec.start, sec.end, rendered), "replaced"
    else:
        new_lines, action = pm.append_section(doc, rendered), "created"
    return _commit(info, doc, new_lines, action, args.name.strip(), args.dry_run)


def cmd_update(args):
    info, doc, sections = _load(args)
    sec, _ = _resolve_or_report(args, args.name, sections, info, max_tier=3)
    if sec is None:
        return NEEDS_USER
    if args.expect_hash and args.expect_hash != sec.hash:
        print("ERROR [stale] '%s' changed since you read it (hand-edited?). Nothing "
              "was written. Re-base on the current text below and retry." % sec.name)
        print("  current_hash: %s" % sec.hash)
        print("----- CURRENT -----")
        print(sec.body)
        return 1

    replacement = _read_text(args, "text_file")
    addition = _read_text(args, "append_file")
    if replacement is None and addition is None and not args.summary and args.tags is None:
        print("ERROR [nothing_to_do] pass --text-file, --append-file, --summary or --tags.")
        return 1
    if replacement is not None:
        body, action = replacement, "updated"
    elif addition is not None:
        body, action = (sec.body.rstrip() + "\n\n" + addition.strip()).strip(), "appended"
    else:
        body, action = sec.body, "updated"
    summary = args.summary or sec.index_line
    tags = ([t.strip() for t in args.tags.split(",") if t.strip()]
            if args.tags is not None else sec.tags)
    rendered = pm.render_section(sec.name, summary, body, tags,
                                 date.today().isoformat(), doc.newline)
    new_lines = pm.splice(doc.lines, sec.start, sec.end, rendered)
    return _commit(info, doc, new_lines, action, sec.name, args.dry_run)


def cmd_delete(args):
    info, doc, sections = _load(args)
    sec, _ = _resolve_or_report(args, args.name, sections, info, max_tier=3)
    if sec is None:
        return NEEDS_USER
    if not args.yes and not args.dry_run:
        print("ERROR [needs_confirmation] deleting '%s' is permanent. Confirm with the "
              "user, then pass --yes." % sec.name)
        return 1
    new_lines = pm.splice(doc.lines, sec.start, sec.end, [])
    return _commit(info, doc, new_lines, "deleted", sec.name, args.dry_run)


# -- cli -----------------------------------------------------------------------

def main(argv=None):
    resolvelib.configure_stdio()
    parser = argparse.ArgumentParser(
        prog="prompts.py", description="Read and maintain the repo's saved prompts.")
    parser.add_argument("--file", help="explicit path to prompts.md")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list", help="names + one-line summaries")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("find", help="ranked keyword search over names, tags, summaries")
    p.add_argument("terms", nargs="+")
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=cmd_find)

    p = sub.add_parser("get", help="resolve the user's words to one prompt and print it")
    p.add_argument("query", nargs="+", help="a name, or the user's own phrasing")
    p.add_argument("--exact", action="store_true", help="require an exact name")
    p.add_argument("--no-text", action="store_true", help="metadata only")
    p.set_defaults(func=cmd_get)

    p = sub.add_parser("save", help="add a new prompt")
    p.add_argument("--name", required=True)
    p.add_argument("--summary", required=True, help="the one-line index entry")
    p.add_argument("--text-file", dest="text_file", help="file holding the prompt")
    p.add_argument("--text", help="inline prompt text (one-liners only)")
    p.add_argument("--tags", help="comma-separated")
    p.add_argument("--force", action="store_true", help="replace an existing prompt")
    p.add_argument("--dry-run", action="store_true", help="show the diff, write nothing")
    p.set_defaults(func=cmd_save)

    p = sub.add_parser("update", help="revise an existing prompt")
    p.add_argument("--name", required=True)
    p.add_argument("--summary")
    p.add_argument("--text-file", dest="text_file", help="replace the body")
    p.add_argument("--append-file", dest="append_file", help="add to the end of the body")
    p.add_argument("--tags", help="comma-separated; replaces existing tags")
    p.add_argument("--expect-hash", dest="expect_hash",
                   help="section_hash from the get this revision is based on")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_update)

    p = sub.add_parser("delete", help="remove a prompt permanently")
    p.add_argument("--name", required=True)
    p.add_argument("--yes", action="store_true", help="required: confirms the deletion")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_delete)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except OSError as err:
        print("ERROR [io] %s" % err)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
