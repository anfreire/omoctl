from __future__ import annotations

import os
import sys
import typing

_USE_COLOR: typing.Final[bool] = (
    sys.stdout.isatty() and "NO_COLOR" not in os.environ
)

BOLD: typing.Final[str] = "\033[1m" if _USE_COLOR else ""
DIM: typing.Final[str] = "\033[2m" if _USE_COLOR else ""
RED: typing.Final[str] = "\033[31m" if _USE_COLOR else ""
GREEN: typing.Final[str] = "\033[32m" if _USE_COLOR else ""
CYAN: typing.Final[str] = "\033[36m" if _USE_COLOR else ""
RESET: typing.Final[str] = "\033[0m" if _USE_COLOR else ""

SEPARATOR: typing.Final[str] = f"{DIM}{'─' * 50}{RESET}"


def die(msg: str) -> typing.NoReturn:
    print(f"{RED}Error: {msg}{RESET}", file=sys.stderr)
    sys.exit(1)


def print_section(
    text: str, color: str | None = CYAN, bold: bool = True, width: int = 50
) -> None:
    padding_right = (width - len(text)) // 2
    padding_left = width - len(text) - padding_right
    styled_text = f"{BOLD if bold else ''}{color if color else ''}{text}{RESET}"
    print(SEPARATOR)
    print(" " * padding_left + styled_text + " " * padding_right)
    print(SEPARATOR)


def parse_section_label(agent_type: str) -> str:
    return (
        (agent_type[:-3] + "y").capitalize()
        if agent_type.endswith("ies")
        else agent_type.rstrip("s").capitalize()
    )


def print_diff(
    curr_config: dict | None,
    patched_config: dict,
    keys: list[tuple[str, str]],
) -> None:
    if curr_config is None:
        curr_config = {section: {} for section, _ in keys}

    for section, name in keys:
        curr_entry = curr_config.get(section, {}).get(name)
        patched_entry = patched_config[section][name]
        label = parse_section_label(section)

        if curr_entry is None:
            print(f"{GREEN}+  {BOLD}{label} {name!r}{RESET}")
            print(f"{GREEN}+    model: {patched_entry.get('model', '?')}{RESET}")
            continue

        changes: list[tuple[str, str | None, str]] = []
        for key, new_val in patched_entry.items():
            old_val = curr_entry.get(key)
            if old_val is None:
                changes.append((key, None, new_val))
            elif old_val != new_val:
                changes.append((key, old_val, new_val))

        if not changes:
            print(f"  {DIM}{label} {name!r}{RESET}")
            print(f"    {DIM}model: {patched_entry.get('model', '?')}{RESET}")
            continue

        print(f"  {BOLD}{label} {name!r}{RESET}")
        for key, old_val, new_val in changes:
            if old_val is None:
                print(f"    {GREEN}+ {key}: {new_val}{RESET}")
            else:
                print(f"    {RED}- {key}: {old_val}{RESET}")
                print(f"    {GREEN}+ {key}: {new_val}{RESET}")


def print_profile_list(
    profiles: list[tuple[str, str, list[str]]],
    active_alias: str | None,
) -> None:
    for name, alias, providers in profiles:
        marker = f"{GREEN}● {RESET}" if alias == active_alias else "  "
        providers_str = ", ".join(providers)
        print(f"{marker}{BOLD}{name}{RESET} {DIM}({alias}){RESET}")
        print(f"    {DIM}providers: {providers_str}{RESET}")


def print_profile_status(
    name: str, alias: str, providers: list[str]
) -> None:
    print(f"{BOLD}Active profile:{RESET} {GREEN}{name}{RESET} {DIM}({alias}){RESET}")
    print(f"{DIM}Providers: {', '.join(providers)}{RESET}")
