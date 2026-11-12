# team-brain

A Claude Code plugin (and its own one-plugin marketplace) that gives a person, a team
or a company a shared, knowledge-graph memory. See
[plugins/team-brain/README.md](plugins/team-brain/README.md) for what it does.

## Install

```
claude plugin marketplace add Logic-Git/team-brain
claude plugin install team-brain@team-brain
```

Another marketplace can list it without copying it:

```json
{
  "name": "team-brain",
  "source": {
    "source": "git-subdir",
    "url": "Logic-Git/team-brain",
    "path": "plugins/team-brain",
    "ref": "v1.0.0"
  }
}
```

Pin `ref` to a release tag so only tagged releases reach that marketplace's users.

## Layout

```
.claude-plugin/marketplace.json     this repo as a marketplace
plugins/team-brain/                 the plugin
  .claude-plugin/plugin.json
  skills/team-brain/
    SKILL.md                        loaded when the skill triggers
    references/                     loaded only when needed
    scripts/                        kg.py, prompts.py, lib/, templates/
```

## Releasing

Bump `version` in `plugins/team-brain/.claude-plugin/plugin.json`, commit, and tag
`vX.Y.Z`.
