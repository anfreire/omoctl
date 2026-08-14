"""Running oh-my-openagent's installer to obtain a config.

omoctl knows no OMO flag names or values. Whatever `install:` holds is
rendered into `--flag=value` and handed over; OMO validates it and its own
error is what the user sees. That is the whole reason a new provider or a new
subscription tier needs no change here.

The installer resolves its config directory from $HOME, so pointing $HOME at a
temporary directory yields a pristine config for a given flag set and touches
nothing the user owns. Which file it wrote there is then discovered, not
assumed — that is how omoctl learns where OpenCode reads.
"""

from __future__ import annotations

import functools
import os
import pathlib
import shutil
import subprocess
import tempfile
import typing

import json5

from omoctl.paths import BUNX_FALLBACK, omo_config
from omoctl.render import console, die

# The npm package has been renamed once already (oh-my-opencode ->
# oh-my-openagent, both still published). An env var beats waiting for a release.
PACKAGE: typing.Final = os.environ.get("OMOCTL_PACKAGE") or "oh-my-opencode"

# omoctl's own invocation mode rather than profile config, but listing either in
# `install:` overrides it.
MODE: typing.Final[dict[str, typing.Any]] = {"no-tui": None, "skip-auth": None}

Flags = tuple[tuple[str, typing.Any], ...]


@functools.cache
def _runner() -> tuple[str, ...]:
    bunx = shutil.which("bunx")
    if bunx:
        return (bunx,)
    if BUNX_FALLBACK.exists():
        return (str(BUNX_FALLBACK),)
    npx = shutil.which("npx")
    if npx:
        return (npx, "--yes")
    die("No package runner found. Install bun (https://bun.sh) or npm (https://nodejs.org).")


def token(value: typing.Any) -> str:
    # YAML turns the bare words `yes`/`no` a user typed into booleans; turn
    # them back into the tokens they wrote. Everything else passes through, so
    # values omoctl has never heard of (`max20`, `both`, ...) just work.
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return str(value)


def render(flags: Flags) -> list[str]:
    """`{"claude": "max20", "skip-x": None}` -> `["--claude=max20", "--skip-x"]`."""
    return [f"--{name}" if value is None else f"--{name}={token(value)}" for name, value in flags]


def _argv(flags: Flags) -> list[str]:
    return ["install", *render(tuple((MODE | dict(flags)).items()))]


def _run(args: list[str], home: str) -> subprocess.CompletedProcess[str]:
    env = os.environ | {"HOME": home, "USERPROFILE": home}
    try:
        return subprocess.run(
            [*_runner(), PACKAGE, *args], capture_output=True, text=True, timeout=600, env=env
        )
    except subprocess.TimeoutExpired:
        die(f"`{PACKAGE} {' '.join(args)}` timed out after 10 minutes.")
    except (OSError, subprocess.SubprocessError) as exc:
        die(f"Could not run `{PACKAGE}`:\n  {exc}")


def _preflight() -> None:
    """The installer finds its migration sources through the account's real
    home directory, which $HOME cannot redirect. So a broken config there fails
    every fetch, however well isolated the run is. Say so plainly rather than
    letting the installer's stack trace explain it."""
    current = omo_config()
    if not current.exists():
        return
    try:
        json5.loads(current.read_text())
    except ValueError as exc:
        backups = sorted(current.parent.glob(f"{current.name}.bak.*"))
        recover = (
            f"\n  {PACKAGE} keeps backups; the newest is {backups[-1].name}" if backups else ""
        )
        die(f"{current} does not parse, and {PACKAGE} reads it on every run:\n  {exc}{recover}")


# A user config sits near the top of a home directory and is small. Bounding
# the search on both keeps it away from the package-manager caches an install
# leaves behind, which run to tens of thousands of unrelated JSON files.
_MAX_DEPTH: typing.Final = 4
_MAX_BYTES: typing.Final = 1 << 20


def _candidates(root: pathlib.Path) -> typing.Iterator[pathlib.Path]:
    for parent, directories, files in os.walk(root):
        here = pathlib.Path(parent)
        if len(here.relative_to(root).parts) >= _MAX_DEPTH:
            directories.clear()
        for name in sorted(files):
            path = here / name
            if ".json" in name and path.stat().st_size <= _MAX_BYTES:
                yield path


def _produced(home: str) -> tuple[dict[str, typing.Any], str] | None:
    """Find the config the installer just wrote, and where it put it.

    Identified by content rather than by name: of everything that appeared in
    the sandbox, the config is the JSON carrying the most model references.
    That is what lets omoctl follow OMO if it relocates the file again — the
    mistake that made 0.4.0 write to a path nothing had read for two versions.
    """
    from omoctl.patch import sites

    best: tuple[int, int, str, dict[str, typing.Any]] | None = None
    root = pathlib.Path(home)
    for candidate in _candidates(root):
        try:
            parsed = json5.loads(candidate.read_text())
        except (ValueError, OSError, UnicodeDecodeError):
            continue
        if not isinstance(parsed, dict):
            continue
        found = sum(1 for _ in sites(parsed))
        relative = candidate.relative_to(root)
        # Most references wins; the shallowest path breaks ties.
        rank = (-found, len(relative.parts), str(relative))
        if found and (best is None or rank < (-best[0], best[1], best[2])):
            best = (found, len(relative.parts), str(relative), parsed)
    return (best[3], best[2]) if best else None


@functools.cache
def fetch(flags: Flags) -> tuple[dict[str, typing.Any], str]:
    """The config oh-my-openagent generates for `flags`, and its path in $HOME."""
    _preflight()
    with tempfile.TemporaryDirectory(prefix="omoctl-") as home:
        args = _argv(flags)
        result = _run(args, home)
        produced = _produced(home) if result.returncode == 0 else None

        if produced is None:
            reported = (result.stdout + result.stderr).strip()
            console.print(f"[red]`{PACKAGE} {' '.join(args)}` failed.[/]\n")
            console.print(reported or "(no output)", markup=False, highlight=False)
            raise SystemExit(1)
        return produced


def install_help() -> str:
    """OMO's own `install --help`, verbatim."""
    with tempfile.TemporaryDirectory(prefix="omoctl-") as home:
        result = _run(["install", "--help"], home)
    return (result.stdout or result.stderr).strip()


__all__ = ["MODE", "PACKAGE", "fetch", "install_help", "render", "token"]
