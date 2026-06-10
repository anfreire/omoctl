import pathlib
import typing


HOME_DIR: typing.Final[pathlib.Path] = pathlib.Path.home()

CONFIG_DIR: typing.Final[pathlib.Path] = HOME_DIR / ".config/omoctl"
CONFIG_PATH: typing.Final[pathlib.Path] = CONFIG_DIR / "config.yaml"
PROFILES_DIR: typing.Final[pathlib.Path] = CONFIG_DIR / "profiles"
ACTIVE_STATE_PATH: typing.Final[pathlib.Path] = CONFIG_DIR / "active"
ACTIVE_BACKUP_PATH: typing.Final[pathlib.Path] = CONFIG_DIR / "active-config.bak"

OPENCODE_DIR: typing.Final[pathlib.Path] = HOME_DIR / ".config/opencode"
ACTIVE_CONFIG_PATH: typing.Final[pathlib.Path] = OPENCODE_DIR / "oh-my-openagent.jsonc"
UPDATED_CONFIG_PATH: typing.Final[pathlib.Path] = OPENCODE_DIR / "oh-my-openagent.json"

BUNX_HOME_FALLBACK: typing.Final[pathlib.Path] = HOME_DIR / ".bun/bin/bunx"
