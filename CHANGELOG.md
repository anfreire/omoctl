# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
