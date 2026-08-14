# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] - 2026-08-15

Rewritten against oh-my-openagent 4.19. The config file OMO reads moved, its
shape changed, and `--claude` grew a third value — all of which 0.4.0 was blind
to. Rather than teach omoctl the new vocabulary, this release removes its
knowledge of OMO's vocabulary entirely, so the next provider, subscription tier
or config section needs no omoctl release at all.

**`config.yaml` is not backward compatible.** There is no migration path;
rewrite it against the README. The full 0.4.0 vocabulary — `providers`,
`source`/`target`, `agent`, `category`, `remove_fallbacks`, `active_profile` —
is gone.

### Changed

- **BREAKING**: the active config is written to `~/.omo/omo.jsonc`. OMO moved there; `~/.config/opencode/oh-my-openagent.jsonc` now appears only in OMO's legacy-migration list and is never read at runtime, so 0.4.0 has been writing to a dead file since OMO 4.x. Top-level keys omoctl did not produce (`_migrations`, anything OMO adds later) are carried through untouched.
- **The location is observed rather than assumed.** `update` notes which file the installer wrote inside its sandbox — identified by carrying model references, not by name — and `use` writes to the same place in the real home. Hardcoding that path is what broke 0.4.0; omoctl now follows OMO the next time it moves.
- **BREAKING**: `providers: [claude, openai]` becomes `install: {claude: yes, openai: yes}`. omoctl no longer discovers OMO's flags by scraping `install --help`, and no longer assumes every flag is a yes/no switch — the map is passed through verbatim as `--flag=value`, so `claude: max20`, `platform: both`, and flags that do not exist yet all work. OMO validates them and its own error, listing the values it accepts, is what you see. This is what made a Max 20x subscription unreachable in 0.4.0.
- **BREAKING**: `source`/`target` become `match`/`set`. `set` assigns *any* key onto the matched entry — `variant` was the only writable field before — and `null` deletes one. `set: {variant: max, temperature: 0.3}` is a patch, not a feature request. It will not assign a model list (`fallback_models`, `models`): replacing a list wholesale is `overrides`' job, and excluding it means one patch can never invalidate another's target.
- **BREAKING**: `agent:` and `category:` become `where:`, a glob over the reference's path (`[opencode].agents.oracle.model`). Two hardcoded section names become one expression that also reaches `models` arrays, harness blocks, and sections that do not exist yet. `*` and `?` are the only glob syntax and brackets are literal, so a path copied out of a diff works as written; a pattern with neither is a plain word matched anywhere in the path.
- **BREAKING**: `remove_fallbacks` becomes `drop`, and applies to `models` lists as well as `fallback_models`.
- **BREAKING**: `overrides` mirrors `omo.jsonc`'s real shape, which is now harness-scoped. What was `disabled_hooks: [...]` becomes `"[opencode]": {disabled_hooks: [...]}`.
- **BREAKING**: `check` is now `update --dry-run` (`-n`). It builds every profile, writes nothing, and reports how many models each patch rewrote — including patches that matched nothing, which the old checker could not detect.
- **BREAKING**: `active_profile` is now `activate`. The old name read like a statement of what is live, which it never was — `omoctl show` reports that, and the two disagreeing was already a bug in 0.4.0.
- Model references are found by walking the config for keys named `model` or ending in `models`, rather than iterating a literal `("agents", "categories")`. Bare `provider/id` strings inside those lists are patchable too, and are promoted to objects when a patch gives them keys to hold.
- A `set.model` that names a retired model now resolves to its closest surviving sibling instead of aborting the update, and `update` says when it did.
- Patches on a provider missing from `opencode models` no longer abort. That list only covers providers you are signed in to, so an id spelled out in full is taken as written; `update` notes that it went unchecked.
- Repeats within a `models` list are collapsed after patching. A patch scoped to a whole entry rewrites its fallbacks too, and a model listed as its own backup is never what was meant.
- Rewritten on cyclopts, rich and pydantic. Config errors now name the exact path (`patches.0.match: unknown filter key(s) 'includes'`), and unknown keys are rejected rather than ignored.

### Removed

- The move-aside/restore dance around the installer, and the `active-config.bak` crash-recovery file it needed. Builds now run the installer with `$HOME` pointed at a temporary directory, which cannot touch anything you own.
- Provider, agent and category validation. OMO validates its own flags better than omoctl could, and `where` globs are not a closed set.
- The test suite, and pytest from CI and dev dependencies.

### Added

- `omoctl providers` prints `oh-my-opencode install --help` verbatim — the authoritative flag list, uninterpreted.
- `use` also writes every profile to `omo.jsonc`'s `profiles` block, so `OMO_PROFILE=<alias> opencode` overrides the active profile for one shell.
- `OMOCTL_PACKAGE` runs a different npm package than `oh-my-opencode`, which has already been renamed once.
- `--no-tui` and `--skip-auth` are defaults rather than fixed argv; listing either in `install:` overrides it.
- A clear error when the OMO config does not parse. The installer reaches it through the account's real home directory, which `$HOME` cannot redirect, so a broken file there fails every build however well isolated it is.

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
- The main model's `variant` renders inline on the model line (`model: anthropic/claude-opus-4-7 (variant: max)`), exactly like fallback entries. Previously an unchanged entry hid its variant entirely, and a variant change printed as a detached property line below the fallbacks; it now diffs on the model line itself.
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
