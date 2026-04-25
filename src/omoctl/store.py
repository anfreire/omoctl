from __future__ import annotations

import json

from omoctl.output import die
from omoctl.paths import ACTIVE_CONFIG_PATH, ACTIVE_STATE_PATH, PROFILES_DIR


def save_profile(alias: str, name: str, config: dict) -> None:
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    (PROFILES_DIR / f"{alias}.json").write_text(json.dumps(config, indent=2))


def activate_profile(alias: str, name: str, config: dict) -> None:
    ACTIVE_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_CONFIG_PATH.write_text(json.dumps(config, indent=2))

    ACTIVE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_STATE_PATH.write_text(alias)


def remove_profile(alias: str) -> None:
    path = PROFILES_DIR / f"{alias}.json"
    if path.exists():
        path.unlink()


def get_profile_config(alias: str) -> dict | None:
    path = PROFILES_DIR / f"{alias}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        die(f"Stored profile at {path} is malformed:\n  {e}")


def get_active_alias() -> str | None:
    if ACTIVE_STATE_PATH.exists():
        alias = ACTIVE_STATE_PATH.read_text().strip()
        if alias:
            return alias
    return None


def cleanup_stale(valid_aliases: set[str]) -> None:
    if not PROFILES_DIR.exists():
        return
    for path in PROFILES_DIR.glob("*.json"):
        if path.stem not in valid_aliases:
            path.unlink()
