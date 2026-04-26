# omoctl

CLI tool for managing [oh-my-openagent](https://github.com/code-yeongyu/oh-my-openagent) profiles in [OpenCode](https://opencode.ai).

Define profiles, patch models across providers, and switch between configurations with a single command.

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

> Examples in this README use the bare `omoctl` form. If you prefer `uvx`, prefix every command (`uvx omoctl update`, `uvx omoctl switch claude`, ...).

### Prerequisites

- Python 3.11+
- [bun](https://bun.sh) or [npm](https://nodejs.org) (for fetching OMO configs via `oh-my-opencode`)
- OpenCode installed with a populated model cache (`~/.cache/opencode/models.json` — run `opencode` once to seed it)

## Quick Start

```bash
omoctl update          # fetch & build all profiles
omoctl list            # see what's available
omoctl switch claude   # activate a profile
omoctl                 # show active profile
omoctl validate        # check config against available models/agents
```

## Commands

| Command | Description |
|---|---|
| `omoctl` | Show active profile |
| `omoctl list` | List all profiles |
| `omoctl switch <profile>` | Switch to a profile (by name or alias) |
| `omoctl update [profile]` | Fetch fresh OMO configs, apply patches, save. All profiles if omitted |
| `omoctl remove <profile>` | Remove a stored profile |
| `omoctl validate` | Validate config against available models, agents, and categories |
| `omoctl show [-a\|-n\|-j]` | Show active profile: header + JSON by default; `-a` alias only, `-n` name only, `-j` JSON only |
| `omoctl version` | Print version |

## Config

Located at `~/.config/omoctl/config.yaml`. Created on first run.

### Minimal example

```yaml
profiles:
  - name: Claude
    providers: [claude]
```

That's it. One profile, one provider. Run `omoctl update` and you're done.

### Full example

```yaml
active_profile: no-copilot

overrides:
  disabled_hooks:
    - context-window-monitor

patches:
  - source: { provider: google }
    target: { provider: proxy }

profiles:
  - name: Claude
    providers: [claude]

  - name: Claude & OpenAI
    providers: [claude, openai]

  - name: No Copilot
    providers: [claude, gemini, openai]
    patches:
      - source: { provider: google, model: gemini-3.1-pro-preview }
        target: { provider: proxy, model: gemini-3-1-pro-xhigh, variant: null }
    overrides:
      disabled_hooks:
        - context-window-monitor
        - some-other-hook
```

### Fields

| Field | Type | Description |
|---|---|---|
| `active_profile` | string | Profile to auto-activate after `update`. Optional |
| `overrides` | dict | OMO config overrides applied to all profiles |
| `patches` | list | Global patches applied to all profiles (see [Patches](#patches)) |
| `profiles` | list | Profile definitions (at least one required) |

### Profile fields

| Field | Type | Description |
|---|---|---|
| `name` | string | **Required.** Display name. Also determines the alias (e.g. `"No Copilot"` -> `no-copilot`) |
| `providers` | list | **Required.** OMO providers to enable. Run `omoctl validate` to see available providers |
| `patches` | list | Profile-specific patches. Take priority over global patches |
| `overrides` | dict | OMO config overrides. Deep-merged on top of the global `overrides` |

## Patches

Patches rewrite models in the OMO config before saving. A patch has a `source` (what to match) and a `target` (what to replace it with).

### Source

The source specifies what to match. All fields are optional but at least one must be set.

| Field | Type | Description |
|---|---|---|
| `provider` | string | Match models from this provider (e.g. `google`, `anthropic`) |
| `model` | string, list, or dict | Filter which models to match (see [Model Filters](#model-filters)) |
| `agent` | string | Match a specific agent (e.g. `sisyphus`, `oracle`) |
| `category` | string | Match a specific category (e.g. `deep`, `quick`) |

These combine: `{ agent: sisyphus, provider: google }` matches sisyphus only when it uses a google model.

### Target

| Field | Type | Description |
|---|---|---|
| `provider` | string | Target provider. Falls back to source provider if omitted |
| `model` | string, list, or dict | Target model (see [Model Filters](#model-filters)) |
| `variant` | string or null | `"max"` sets variant, `null` removes it, omit to keep existing |

### Examples

```yaml
patches:
  # Redirect all google models to a proxy provider
  - source: { provider: google }
    target: { provider: proxy }

  # Redirect a specific model to a specific target
  - source: { provider: google, model: gemini-3.1-pro-preview }
    target: { provider: proxy, model: gemini-3-1-pro-xhigh, variant: null }

  # Override a specific agent
  - source: { agent: sisyphus }
    target: { provider: anthropic, model: claude-opus-4-7, variant: max }

  # Override a category
  - source: { category: ultrabrain }
    target: { provider: openai, model: gpt-5.4, variant: xhigh }
```

### Priority

1. Profile patches are checked before global patches
2. Agent/category patches take priority over provider-only patches
3. Exact model matches beat filter matches
4. More specific filters beat less specific ones

## Model Filters

The `model` field in source/target accepts three formats:

**Exact match** — a string:
```yaml
model: gemini-3.1-pro-preview
```

**Keyword filter** — a list of terms that must all match:
```yaml
model: [gemini, pro]
```

**Include/exclude filter** — fine-grained control:
```yaml
model:
  include: [gemini, pro]
  exclude: [flash]
```

Model IDs are split into words and numbers (e.g. `claude-opus-4-7` -> words: `[claude, opus]`, numbers: `[4, 7]`). Filters match against these parts.

## File Layout

```
~/.config/omoctl/
  config.yaml              # your config
  active                   # current active profile alias
  profiles/
    claude.json            # stored OMO config per profile
    no-copilot.json

~/.config/opencode/
  oh-my-openagent.jsonc    # active profile config (plain JSON, read by oh-my-openagent plugin)
```

## Validation

`omoctl validate` checks your config against live data:

- Patch source/target **providers** exist in the model cache
- Patch source/target **models** exist in their provider
- Patch **agent** names exist in the OMO config
- Patch **category** names exist in the OMO config

On failure, it prints each error with available options:

```
Validation failed with 2 error(s):

  • global patch [0]: source provider 'nonexistent' not found.
  • profile 'Test' patch [0]: source agent 'fake' not found. Available: atlas, explore, ...
```
