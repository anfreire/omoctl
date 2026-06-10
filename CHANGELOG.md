# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2026-06-10

### Added

- Test suite (122 tests) covering the matcher, diff rendering, status display, config loading, validation, and the OMO fetch flow; GitHub Actions CI runs ruff, mypy, and pytest on Python 3.11–3.13.
- Malformed model specs (unknown filter keys like `includes:`, wrong value types, empty filters) are rejected at config load with the offending profile/patch named, so every command fails fast instead of `update` crashing mid-run with a traceback.
- `check` now also reports: filters that match no available model (catches typo'd terms that previously matched everything or nothing silently), malformed model specs, target models that exist in no provider, and an `active_profile` that names no defined profile.
- Crash-safe fetching: the active OpenCode config is backed up to disk (`~/.config/omoctl/active-config.bak`) while `oh-my-opencode` runs, and automatically recovered on the next run if a previous run was hard-killed. Previously the only backup lived in memory.
- `update` warns when the `active_profile` pin matches no profile instead of silently skipping auto-activation.
- Model filter terms accept a single scalar without list brackets (`include: opus`).

### Changed

- **BREAKING**: `show` and `list` now always report the actually active profile (the state file written on activation). Previously the `active_profile` pin shadowed reality: with `active_profile: Claude` pinned and `omoctl use default` run, bare `omoctl` claimed Claude was active while `-a`/`-n`/`-j` and OpenCode itself used Default. The pin keeps its documented role: auto-activation after `update`.
- **BREAKING**: agent/category-scoped patches now honor their `model` filter when `provider` is omitted. `{ agent: sisyphus, model: claude-opus-4-7 }` previously applied to sisyphus on *any* model; it now applies only when the model matches, as documented.
- **BREAKING**: patch selection is scored consistently for both patch kinds: exact model beats filter beats no constraint, more specific filters beat less specific ones, a `provider` constraint breaks ties for agent/category patches, and list order (profile before global) breaks complete ties. Agent/category patches previously used pure first-match-wins.
- Update diffs now show keys that were *removed* from an entry (e.g. a variant dropped via `variant: null`) as red `-` lines; previously removals were invisible and the entry rendered as "no changes".
- Update diffs no longer report explicitly-null values as `+ key: None` additions on every run; values are rendered in JSON style (`null`/`true`/`false`).
- A stale active alias (state file pointing at a profile no longer in config.yaml) is reported honestly by `show` instead of "No active profile".
- `omoctl -a show` (status flag before the subcommand) now works instead of silently ignoring the flag.
- The first-run message ("created a default config") is informational rather than an error-styled message.
- Internal: `store.save_profile`/`activate_profile` dropped their unused `name` parameter; `print_diff` accepts `None` for a first build.

### Fixed

- The `oh-my-opencode install` subprocess now has a timeout (300s) like every other subprocess; a hung fetch no longer hangs `update` forever with the active config deleted.
- `opencode models` output parsing ignores log/noise lines (anything with whitespace, empty halves, or a path-like model part) instead of polluting the provider list.

## [0.3.1] - 2026-06-06

### Changed

- `update` diff now uses set-based comparison for `fallback_models` instead of positional indexing. Removals, additions, and kept entries are determined by content, not list position — reordering the same set no longer produces spurious churn.
- Unchanged and kept fallback entries use space-aligned indentation (no marker) instead of numbered bullets. Only real changes get `- ` (removed) or `+ ` (added) markers, making diffs unambiguous in both color and no-color output.
- When an entry has changes, the `model` line and `fallback_models` are always shown for context — previously changing one would hide the other.
- New entries (first build) now display `variant` and other non-model keys alongside `model` and `fallback_models`.

## [0.3.0] - 2026-06-05

### Added
- `verify` alias for the `check` command (alongside the existing `validate` alias).
- `current` and `status` aliases for the default command, which is now `show`.
- `-v` short flag for `--version` (both `omoctl -v` and `omoctl --version` print the version).
- Progress indicator (`Refreshing model list from opencode...`) printed before the slow `opencode models --refresh` call during `update`.
- `remove_fallbacks` field (global and per-profile) for dropping specific entries from `fallback_models` lists before patches run. Uses the same `source` matcher syntax as patches, with the same scoping rules (provider/model/agent/category). Matching is done against the **original** OMO model, not the post-patch model, so the user-visible semantics are "remove this model from the fallbacks OMO listed".

### Changed

- The default command is now `show`. `status` is kept as an alias, so users on the released 0.2.0 who invoked `omoctl status` or bare `omoctl` see no behavior change.
- Models are now sourced from the `opencode models` CLI instead of the JSON cache at `~/.cache/opencode/models.json`. `update` calls `opencode models --refresh` to pull fresh data from models.dev; `check` skips the refresh for speed.
- Agents and categories continue to come from the fetched OMO config (unchanged).
- README prerequisites updated: `~/.cache/opencode/models.json` is no longer required; `opencode` must be on `PATH`.

### Removed

- Reading `~/.cache/opencode/models.json` and merging custom models from `~/.config/opencode/opencode.json` — both superseded by the live `opencode models` output.

## [0.2.0] - 2026-05-23

### Added

- argparse aliases for short forms and migration paths: `list` → `ls`, `use` → `apply` / `switch`, `update` → `build` / `upgrade`, `remove` → `rm`, `check` → `validate`.
- Top-level `-a` / `-n` / `-j` flags for scriptable active-profile output, so `omoctl -j` and `omoctl status -j` both work without invoking the subcommand.

### Changed

- **BREAKING**: The standalone `show` subcommand was removed. Its `-a` / `-n` / `-j` scriptable modes were folded into `status`, which is now also the default command. `omoctl` (no args) shows the active profile. (`show` returns as the default name in 0.3.0 with `status` kept as an alias.)
- `cmd_switch` was renamed to `cmd_use`, and `cmd_validate` was renamed to `cmd_check` (internal refactor; both old names remain available as argparse aliases).

### Fixed

- Tighter `dacite` type-checking (`check_types=True`) so mis-typed config values — e.g. `providers: claude` (a string instead of a list) — fail fast with a clear `WrongTypeError` instead of being silently coerced into a corrupt stringified generator that iterated character-by-character downstream.

## [0.1.1] - 2026-04-26

### Changed

- Renamed `Config.defaults` to `Config.overrides` for symmetry with `Profile.overrides` (both share the same deep-merge mechanism; matches the existing convention used for `patches`).

### Documentation

- Renamed README "Run" section to "Install" and presented both `uvx` (no install) and `uv tool install` (permanent) up front.
- Aligned example commands throughout the README: the bare `omoctl` form applies to both invocations with a `uvx` prefix.
- Updated prerequisites to reflect the bun OR npm discovery added to `omo.py` and the corrected cache-seed hint.

## [0.1.0] - 2026-04-25

### Added

- Initial release of `omoctl`.
- CLI for managing [oh-my-openagent](https://github.com/code-yeongyu/oh-my-openagent) profiles in [OpenCode](https://opencode.ai).
- Define profiles, patch models across providers, switch between configurations with a single command.
- Commands: `show` (default), `list`, `use`, `update`, `remove`, `check`, `version`.
- Profile definitions: `name`, `providers`, `patches`, `overrides`.
- Patches with `source` / `target`: match by `provider`, `model`, `agent`, or `category`; rewrite to a different `provider` / `model` / `variant`.
- Model filters: exact string, keyword list (AND), or include/exclude dict.
- Validation against the JSON model cache: providers, models, agents, and categories.
- File layout: `~/.config/omoctl/{config.yaml, active, profiles/<alias>.json}`; `~/.config/opencode/oh-my-openagent.jsonc` for the active profile.
