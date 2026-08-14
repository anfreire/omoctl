from __future__ import annotations

import os
import pathlib
import typing

HOME: typing.Final = pathlib.Path.home()

_XDG_CONFIG: typing.Final = os.environ.get("XDG_CONFIG_HOME")
CONFIG_DIR: typing.Final = (
    pathlib.Path(_XDG_CONFIG) if _XDG_CONFIG else HOME / ".config"
) / "omoctl"
CONFIG_PATH: typing.Final = CONFIG_DIR / "config.yaml"
PROFILES_DIR: typing.Final = CONFIG_DIR / "profiles"
ACTIVE_PATH: typing.Final = CONFIG_DIR / "active"
TARGET_PATH: typing.Final = CONFIG_DIR / "target"

# Where OMO put its config the last time we watched it install. 0.4.0 broke
# because it hardcoded the location OMO used at the time; `update` records what
# it actually observes, and this is only the starting guess.
FALLBACK_TARGET: typing.Final = ".omo/omo.jsonc"


def omo_config() -> pathlib.Path:
    """The file OpenCode reads, relative to the real home directory."""
    recorded = TARGET_PATH.read_text().strip() if TARGET_PATH.exists() else ""
    return HOME / (recorded or FALLBACK_TARGET)


BUNX_FALLBACK: typing.Final = HOME / ".bun" / "bin" / "bunx"
