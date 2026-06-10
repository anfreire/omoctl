# omoctl

[![CI](https://github.com/anfreire/omoctl/actions/workflows/ci.yml/badge.svg)](https://github.com/anfreire/omoctl/actions/workflows/ci.yml)

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

> Examples in this README use the bare `omoctl` form. If you prefer `uvx`, prefix every command (`uvx omoctl update`, `uvx omoctl use claude`, ...).

### Prerequisites

- Python 3.11+
- [bun](https://bun.sh) or [npm](https://nodejs.org) (for fetching OMO configs via `oh-my-opencode`)
- [OpenCode](https://opencode.ai) installed and on `PATH` (used to list models)

## Quick Start

```bash
omoctl update          # fetch & build all profiles
omoctl list            # see what's available
omoctl use claude      # activate a profile
omoctl                 # show active profile
omoctl check           # check config against available models/agents
```

## Commands

| Command | Aliases | Description |
|---|---|---|
| `omoctl [show]` | `current`, `status` | Show active profile. Use `-a`/`-n`/`-j` to print only the alias, name, or JSON (e.g. `omoctl -j`) |
| `omoctl list` | `ls` | List all profiles |
| `omoctl use <profile>` | `apply`, `switch` | Activate a profile (by name or alias) |
| `omoctl update [profile]` | `build`, `upgrade` | Fetch fresh OMO configs, apply patches, save. All profiles if omitted |
| `omoctl remove <profile>` | `rm` | Remove a stored profile |
| `omoctl check` | `validate`, `verify` | Check config against available models, agents, and categories |
| `omoctl version` | — | Print version. Also available as `-v` |

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
| `active_profile` | string | Profile to auto-activate after `update`. Optional. Does not affect what `show`/`list` report — they always reflect the actually active profile |
| `overrides` | dict | OMO config overrides applied to all profiles |
| `patches` | list | Global patches applied to all profiles (see [Patches](#patches)) |
| `remove_fallbacks` | list | Global rules for dropping entries from `fallback_models` lists. Each entry is a source matcher (see [Removing Fallbacks](#removing-fallbacks)) |
| `profiles` | list | Profile definitions (at least one required) |

### Profile fields

| Field | Type | Description |
|---|---|---|
| `name` | string | **Required.** Display name. Also determines the alias (e.g. `"No Copilot"` -> `no-copilot`) |
| `providers` | list | **Required.** OMO providers to enable. Run `omoctl check` to see available providers |
| `patches` | list | Profile-specific patches. Take priority over global patches |
| `overrides` | dict | OMO config overrides. Deep-merged on top of the global `overrides` |
| `remove_fallbacks` | list | Profile-specific fallback-removal rules. Added to the global `remove_fallbacks` |

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

These combine: `{ agent: sisyphus, provider: google }` matches sisyphus only when it uses a google model, and `{ agent: sisyphus, model: [opus] }` matches sisyphus only when its model passes the filter.

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

1. Agent/category patches take priority over provider/model patches
2. Within each kind, the best-scoring source wins: an exact model match beats a filter, a filter beats no model constraint, and more specific filters beat less specific ones
3. For agent/category patches with equal model scores, having a `provider` constraint wins
4. On a complete tie, the earlier patch wins — profile patches are checked before global patches

## Removing Fallbacks

`remove_fallbacks` drops specific entries from the `fallback_models` lists that OMO ships with, before patches are applied. Each entry is a flat object with the same matcher fields used in [Patches](#patches):

| Field | Type | Description |
|---|---|---|
| `provider` | string | Match fallbacks from this provider (e.g. `openai`, `anthropic`) |
| `model` | string, list, or dict | Filter which models to match (see [Model Filters](#model-filters)) |
| `agent` | string | Only apply to fallbacks belonging to this agent (e.g. `sisyphus`) |
| `category` | string | Only apply to fallbacks belonging to this category (e.g. `deep`) |

At least one of `provider`, `agent`, or `category` must be set. Matching is done against the **original** OMO model — not the post-patch model. So a fallback that would have been rewritten by a patch is still removed if its original model matches.

### Examples

```yaml
# Remove a specific model from all fallback lists globally
remove_fallbacks:
  - provider: openai
    model: gpt-4-mini

# Remove all fallbacks for a specific agent matching a filter
profiles:
  - name: No Copilot
    providers: [claude, gemini, openai]
    remove_fallbacks:
      - agent: sisyphus
        provider: openai
```

### Priority

1. Profile `remove_fallbacks` are applied alongside global `remove_fallbacks` (any match removes the entry)
2. The first matching entry removes the fallback; remaining rules are not evaluated for that entry

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

Model IDs are split into words and numbers (e.g. `claude-opus-4-7` -> words: `[claude, opus]`, numbers: `[4, 7]`). Filters match against these parts. A single term may be given without list brackets (`include: opus`).

Malformed filters are rejected up front: unknown keys (e.g. `includes:`), wrong value types, and empty filters fail at config load with the offending patch named — they never silently match everything.

## File Layout

```
~/.config/omoctl/
  config.yaml              # your config
  active                   # active profile alias — the source of truth for `show`/`list`
  active-config.bak        # transient crash-safety backup, only present during `update`
  profiles/
    claude.json            # stored OMO config per profile
    no-copilot.json

~/.config/opencode/
  oh-my-openagent.jsonc    # active profile config (plain JSON, read by oh-my-openagent plugin)
```

## Validation

Structural problems — invalid YAML, unknown fields, wrong types, malformed model filters — are caught when the config is loaded, so every command fails fast with a pointed error.

`omoctl check` additionally checks your config against live data:

- Profile **providers** are valid OMO providers
- Patch source/target **providers** exist in the model cache
- Patch source/target **models** exist in their provider (exact strings), and **filters** match at least one available model
- Patch **agent** and **category** names exist in the OMO config
- `active_profile` names a defined profile

On failure, it prints each error with available options:

```
Validation failed with 2 error(s):

  • global patch [0]: source provider 'nonexistent' not found.
  • profile 'Test' patch [0]: source agent 'fake' not found. Available: atlas, explore, ...
```

## Development

```bash
uv sync --group dev      # install with dev dependencies
uv run pytest            # run the test suite
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/omoctl
```

CI runs all of the above on Python 3.11, 3.12, and 3.13.
