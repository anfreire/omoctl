"""Built profiles on disk, and the one file OpenCode actually reads."""

from __future__ import annotations

import datetime
import json
import os
import typing

import json5

from omoctl.paths import ACTIVE_PATH, PROFILES_DIR, TARGET_PATH, omo_config
from omoctl.render import console, die

Json = dict[str, typing.Any]

HEADER: typing.Final = (
    "// Written by omoctl from ~/.config/omoctl/config.yaml.\n"
    "// Switch with `omoctl use <profile>`, or per shell with OMO_PROFILE=<alias>.\n"
)


def _write(path: typing.Any, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text)
    os.replace(temporary, path)


def save(alias: str, config: Json) -> None:
    _write(PROFILES_DIR / f"{alias}.json", json.dumps(config, indent=2) + "\n")


def load(alias: str) -> Json | None:
    path = PROFILES_DIR / f"{alias}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except ValueError as exc:
        die(f"Stored profile {path} is malformed:\n  {exc}")


def remove(alias: str) -> None:
    (PROFILES_DIR / f"{alias}.json").unlink(missing_ok=True)


def prune(keep: set[str]) -> list[str]:
    if not PROFILES_DIR.exists():
        return []
    stale = [p for p in PROFILES_DIR.glob("*.json") if p.stem not in keep]
    for path in stale:
        path.unlink()
    return [path.stem for path in stale]


def active() -> str | None:
    if ACTIVE_PATH.exists():
        return ACTIVE_PATH.read_text().strip() or None
    return None


def remember_target(relative: str) -> None:
    """Record where the installer put its config, so `use` writes there too."""
    _write(TARGET_PATH, relative)


def _existing() -> Json:
    """Whatever is in omo.jsonc now, so unmanaged keys can be carried over."""
    current = omo_config()
    if not current.exists():
        return {}
    try:
        parsed = json5.loads(current.read_text())
    except ValueError:
        stamp = datetime.datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        backup = current.with_name(f"{current.name}.bak.{stamp}")
        backup.write_text(current.read_text())
        console.print(f"[yellow]{current} did not parse; kept a copy at {backup.name}.[/]")
        return {}
    return parsed if isinstance(parsed, dict) else {}


def activate(alias: str, profiles: dict[str, Json]) -> None:
    """Write `alias`'s config to omo.jsonc, with every profile alongside it.

    OMO merges `profiles.<name>` over the base config when OMO_PROFILE names
    one, so shipping them all makes `OMO_PROFILE=<alias> opencode` a free
    per-shell override. Top-level keys omoctl did not produce — OMO's own
    migration bookkeeping, anything it adds later — are carried through
    untouched.
    """
    chosen = profiles[alias]
    managed: Json = {**chosen, "profiles": dict(profiles)}

    merged = dict(managed)
    for key, value in _existing().items():
        merged.setdefault(key, value)

    _write(omo_config(), HEADER + json.dumps(merged, indent=2) + "\n")
    _write(ACTIVE_PATH, alias)
