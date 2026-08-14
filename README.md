# omoctl

[![CI](https://github.com/anfreire/omoctl/actions/workflows/ci.yml/badge.svg)](https://github.com/anfreire/omoctl/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/omoctl)](https://pypi.org/project/omoctl/)

CLI tool for managing [oh-my-openagent](https://github.com/code-yeongyu/oh-my-openagent) profiles in [OpenCode](https://opencode.ai).

OMO wires your agents to one fixed set of models — and the moment providers change (a plan runs dry, a subscription ends, a model has a bad day) you're hand-editing `~/.omo/omo.jsonc` again. omoctl makes it declarative: define profiles once, patch models across providers, and switch whole configurations with a single command.

## Install

Run on demand with no install:

```bash
uvx omoctl --help
```

Or install permanently:

```bash
uv tool install omoctl
omoctl --help
```

> Examples in this README use the bare `omoctl` form. If you prefer `uvx`, prefix every command (`uvx omoctl update`, `uvx omoctl use claude`, ...).

### Prerequisites

- Python 3.11+
- [bun](https://bun.sh) or [npm](https://nodejs.org) — used to run `oh-my-opencode`
- [OpenCode](https://opencode.ai) on `PATH` — used to list models

## Quick Start

```bash
omoctl providers       # what can `install:` say? (oh-my-openagent's own help)
omoctl update          # fetch & build all profiles
omoctl list            # see what's available
omoctl use claude      # activate a profile
omoctl                 # show active profile
```

## Commands

| Command | Aliases | Description |
|---|---|---|
| `omoctl [show]` | `current`, `status` | Show active profile. `-a`/`-n`/`-j` print only the alias, name, or active JSON |
| `omoctl list` | `ls` | List all profiles |
| `omoctl use <profile>` | `apply`, `switch` | Activate a profile (by name or alias) |
| `omoctl update [profile]` | `build`, `upgrade` | Fetch fresh OMO configs, apply patches, save. `--dry-run`/`-n` changes nothing |
| `omoctl remove <profile>` | `rm` | Delete a built profile |
| `omoctl providers` | — | Print `oh-my-opencode install --help`, verbatim |

## Design

omoctl hardcodes nothing about OMO's shape, so a new provider, a new subscription tier, or a new config section needs no new omoctl release.

- **Install flags are your data.** `install:` is passed straight through as `--flag=value`. omoctl never inspects the names or the values, so `claude: max20`, `platform: both`, and whatever ships next all work. OMO validates them and its own error is what you see.
- **Model references are found, not enumerated.** Any `provider/id` under a key named `model`, or ending in `models`, is a model reference — wherever it lives in the tree, whatever section it belongs to.
- **Fetching is isolated.** Each build runs the installer with `$HOME` pointed at a temporary directory, so it produces a pristine config for that flag set and cannot touch anything you own.
- **The config's location is observed, not assumed.** `update` notes which file the installer wrote inside that sandbox, and `use` writes to the same place in your real home. 0.4.0 broke precisely because it hardcoded a path OMO later moved.

## Config

Located at `~/.config/omoctl/config.yaml`. Created on first run.

### Minimal example

```yaml
install: { claude: yes, gemini: no, copilot: no }

profiles:
  - name: Claude
```

Run `omoctl update` and you're done.

### Full example

```yaml
# Flags every profile inherits. Profiles merge their own on top.
install:
  claude: no
  gemini: no
  copilot: no

# Switch to this profile after every `update`.
activate: Max

# Applied to every profile. Profile patches are tried first.
patches:
  - match: { provider: anthropic, model: [sonnet] }
    set:   { model: claude-opus-5 }

drop:
  - { provider: openai, model: gpt-5-nano }

overrides:
  "[opencode]":
    disabled_hooks: [context-window-monitor]

profiles:
  - name: Max
    install: { claude: max20, opencode-go: yes }
    patches:
      - match: { where: "*.agents.oracle.model" }
        set:   { provider: opencode-go, model: glm-5.2, variant: null }

  - name: Frugal
    install: { opencode-go: yes }
    drop:
      - { provider: anthropic }
```

### Fields

Every field except `profiles` may be set globally, per profile, or both.

| Field | Type | Description |
|---|---|---|
| `install` | dict | Flags for `oh-my-opencode install`. Profile values merge over global ones |
| `patches` | list | Model rewrites (see [Patches](#patches)). Profile patches are tried before global ones |
| `drop` | list | Entries to remove from `fallback_models` / `models` lists (see [Drop](#drop)) |
| `overrides` | dict | Deep-merged into the final `omo.jsonc`. Mirrors that file's real shape, harness block included |
| `activate` | string | Profile to switch to after every `update`. Global only |
| `profiles` | list | Profile definitions, each with a `name`. Global only, at least one required |

A profile's alias comes from its name: `"No Copilot"` -> `no-copilot`.

### install

`install:` is a plain map of `oh-my-opencode install` flags. Run `omoctl providers` to see the current set.

```yaml
install:
  claude: max20        # --claude=max20
  opencode-go: yes     # --opencode-go=yes
  platform: both       # --platform=both
  codex-autonomous:    # --codex-autonomous  (no value, so no `=`)
```

`--no-tui` and `--skip-auth` are supplied by default; list either in `install:` to override. OMO requires a value for some flags even when you don't want them (`--gemini`, `--copilot`); put those in the global `install:` once and forget about them.

Set `OMOCTL_PACKAGE` to run a different npm package than `oh-my-opencode`.

> YAML reads the bare words `yes` and `no` as booleans, and omoctl writes them back out as `yes`/`no`. Any other literal that YAML would eat — `on`, `off` — needs quoting.

## Patches

A patch has a `match` (which model references it applies to) and a `set` (what to assign). Every model reference in the config is offered to the patches in order; the first `match` that fits wins.

### match

All three fields are optional, at least one is required, and all given ones must hold.

| Field | Type | Description |
|---|---|---|
| `where` | string | Glob over the reference's path. A plain word matches anywhere in it |
| `provider` | string | The reference's current provider |
| `model` | string, list, or dict | The reference's current model. A bare string is an exact id, not a substring (see [Model Filters](#model-filters)) |

Paths look like `[opencode].agents.oracle.model` and `[opencode].categories.quick.fallback_models.1.model`, which is what `where` matches against:

```yaml
where: oracle                                # every oracle model, fallbacks included
where: "[opencode].agents.oracle.model"      # oracle's main model, pasted from a diff
where: "*.agents.*.model"                    # every agent's main model
where: "*.categories.*"                      # every category
where: "*.fallback_models.*"                 # every fallback, everywhere
```

`*` and `?` are the only glob syntax; a pattern using neither is a plain word, matched anywhere in the path. Brackets are literal, so a path copied out of a diff works as written.

### set

Every key in `set` is assigned onto the matched entry. `provider` and `model` together resolve the model id; `null` deletes a key; anything else is written as-is.

```yaml
set: { model: claude-opus-5 }                    # same provider, different model
set: { provider: opencode-go }                   # same model, different provider
set: { provider: openai, model: [gpt, mini] }    # both, by filter
set: { variant: null }                           # drop the variant, keep the model
set: { variant: max, temperature: 0.3 }          # any key the OMO schema allows
```

A bare `provider/id` string inside a `models` list becomes an object automatically when `set` gives it keys to hold.

`set` cannot assign `fallback_models`, `models`, or any other model list — replacing a list wholesale is `overrides`' job, and keeping it out of `set` means one patch can never invalidate another's target.

### Resolution

Model ids are read as words and numbers: `claude-opus-4-7` is words `claude`, `opus` and numbers `4`, `7`. A filter matches on those parts, and among the matches the version is honoured as far as you named it — `[opus, 4]` picks the newest `4.x`, `[opus]` picks the newest opus outright.

`set.model` takes an id verbatim when the provider has one. Otherwise it is read as a filter of its own words and numbers, so a pin that a provider has since retired lands on its nearest surviving sibling — `claude-opus-4-8` finds `claude-opus-4-7` — and `update` says so rather than failing.

Omitting `set.model` reuses the current model's words and numbers, which is what lets `set: {provider: opencode}` mean "the same model from somewhere else". That only works where the two providers name their models alike; when they don't, omoctl says so and you name the model yourself.

## Drop

`drop` removes entries from `fallback_models` and `models` lists before patches run, so matching is against the model OMO shipped, not the patched one. Entries use the same `match` fields:

```yaml
drop:
  - { provider: openai }                              # every openai fallback
  - { provider: anthropic, model: [haiku] }           # one model everywhere
  - { where: sisyphus, provider: opencode-go }        # scoped to one agent
```

After patching, repeats within a list are collapsed — a patch scoped to a whole entry rewrites its fallbacks too, and the same model listed twice as its own backup is never what was meant.

## Model Filters

The `model` field in `match` and `set` accepts three shapes:

```yaml
model: gemini-3.1-pro-preview        # exact id
model: [gemini, pro]                 # all terms must match
model:                               # fine-grained
  include: [gemini, pro]
  exclude: [flash]
```

A single term needs no brackets (`include: opus`). Malformed filters — unknown keys like `includes:`, wrong types, empty filters — are rejected when the config loads, with the offending patch named.

## Checking your config

Structural problems fail on load, on every command:

```
Error: ~/.config/omoctl/config.yaml:
  patches.0.match: Value error, unknown filter key(s) 'includes'; expected `include` and/or `exclude`
```

`omoctl update --dry-run` builds everything and writes nothing, reporting what each patch did:

```
  where=*.agents.oracle.model → 1 model
  provider=anthropic model=['sonnet'] → 3 models
  no match: where=nonexistent-agent
  drop → 2 entries
```

Bad install flags are reported by OMO itself, with the values it accepts:

```
[X] Validation failed:
  * Invalid --claude value: maybe (expected: no, yes, max20)
```

## File Layout

```
~/.config/omoctl/
  config.yaml        # your config
  active             # active profile alias
  target             # where the installer last put its config
  profiles/
    max.json         # built OMO config, one per profile

~/.omo/
  omo.jsonc          # what OpenCode reads — written by `use`
```

`use` writes the active profile to `omo.jsonc` and every profile to its `profiles` block, so `OMO_PROFILE=<alias> opencode` overrides the active one for a single shell. Top-level keys omoctl did not produce are carried through untouched.

## Development

```bash
uv sync --group dev
uv run ruff check src/
uv run ruff format --check src/
uv run mypy src/omoctl
```

CI runs all of the above on Python 3.11, 3.12, and 3.13.

---

**More agent tooling** — [patch-cc](https://github.com/anfreire/patch-cc): patch the Claude Code binary (live thinking, Codex models) · [summon-cc](https://github.com/anfreire/summon-cc): give your agent a crew of Claude Code workers · [cc-oc](https://github.com/anfreire/cc-oc): drive opencode from inside Claude Code · [wiki-spaces](https://github.com/anfreire/wiki-spaces): a wiki your AI agent keeps
