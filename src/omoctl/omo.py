from __future__ import annotations

import functools
import json
import re
import shutil
import subprocess

from omoctl.output import DIM, RESET, die
from omoctl.paths import ACTIVE_CONFIG_PATH, BUNX_HOME_FALLBACK, UPDATED_CONFIG_PATH

_SKIP_FLAGS = {"no-tui", "skip-auth", "help", "h"}


@functools.cache
def _find_runner() -> tuple[str, ...]:
    bunx = shutil.which("bunx")
    if bunx:
        return (bunx,)
    if BUNX_HOME_FALLBACK.exists():
        return (str(BUNX_HOME_FALLBACK),)
    npx = shutil.which("npx")
    if npx:
        return (npx, "--yes")
    die(
        "No package runner found. Install one of:\n"
        "  - bun (recommended): https://bun.sh\n"
        "  - npm/npx: https://nodejs.org"
    )


@functools.cache
def get_available_providers() -> tuple[str, ...]:
    runner = _find_runner()

    try:
        result = subprocess.run(
            [*runner, "oh-my-opencode", "install", "--help"],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        die(f"Failed to query oh-my-opencode:\n  {e}")

    if result.returncode != 0:
        die(
            "Failed to query oh-my-opencode --help:\n"
            f"  {(result.stderr or result.stdout or '').strip()}"
        )

    providers: list[str] = []
    for match in re.finditer(r"--(\S+)\s+<value>", result.stdout):
        flag = match.group(1)
        if flag not in _SKIP_FLAGS:
            providers.append(flag)
    return tuple(providers)


@functools.cache
def fetch_omo_config(
    providers: tuple[str, ...],
    quiet: bool = False,
) -> dict:
    runner = _find_runner()

    UPDATED_CONFIG_PATH.unlink(missing_ok=True)

    active_backup: str | None = None
    if ACTIVE_CONFIG_PATH.exists():
        active_backup = ACTIVE_CONFIG_PATH.read_text()
        ACTIVE_CONFIG_PATH.unlink()

    all_flags = get_available_providers()
    kwargs = [f"--{f}={'yes' if f in providers else 'no'}" for f in all_flags]

    if not quiet:
        providers_str = (
            providers[0]
            if len(providers) == 1
            else ", ".join(providers[:-1]) + " and " + providers[-1]
        )
        print(f"{DIM}Fetching OMO config for {providers_str}...{RESET}")

    try:
        try:
            subprocess.run(
                [*runner, "oh-my-opencode", "install", "--no-tui", *kwargs],
                check=True, capture_output=True, text=True,
            )
        except subprocess.CalledProcessError as e:
            die(
                "Failed to fetch OMO config:\n"
                f"  {(e.stderr or e.stdout or '').strip()}"
            )
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            die(f"Failed to run oh-my-opencode: {e}")

        if not UPDATED_CONFIG_PATH.exists():
            die(f"Expected OMO config at {UPDATED_CONFIG_PATH} but it was not created.")

        try:
            return json.loads(UPDATED_CONFIG_PATH.read_text())
        except json.JSONDecodeError as e:
            die(f"OMO config at {UPDATED_CONFIG_PATH} is malformed:\n  {e}")
    finally:
        UPDATED_CONFIG_PATH.unlink(missing_ok=True)
        if active_backup is not None:
            ACTIVE_CONFIG_PATH.write_text(active_backup)
