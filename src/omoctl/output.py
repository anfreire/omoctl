from __future__ import annotations

import os
import sys
import typing

_USE_COLOR: typing.Final[bool] = sys.stdout.isatty() and "NO_COLOR" not in os.environ

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


def _format_fallback_entry(fb: dict) -> str:
    model = fb.get("model", "?")
    variant = fb.get("variant")
    if variant is not None:
        return f"{model} (variant: {variant})"
    return model


def _fb_key(fb: dict) -> tuple:
    return tuple(sorted(fb.items()))


def _print_fallbacks_dim(fallbacks: list[dict]) -> None:
    if not fallbacks:
        return
    print(f"    {DIM}fallback_models:{RESET}")
    for fb in fallbacks:
        print(f"        {DIM}{_format_fallback_entry(fb)}{RESET}")


def _print_fallbacks_diff(
    old_fallbacks: list[dict],
    new_fallbacks: list[dict],
) -> None:
    old_keys = {_fb_key(fb) for fb in old_fallbacks}
    new_keys = {_fb_key(fb) for fb in new_fallbacks}

    removed = [fb for fb in old_fallbacks if _fb_key(fb) not in new_keys]
    added = [fb for fb in new_fallbacks if _fb_key(fb) not in old_keys]
    kept = [fb for fb in new_fallbacks if _fb_key(fb) in old_keys]

    if not removed and not added:
        _print_fallbacks_dim(new_fallbacks)
        return

    print(f"    {BOLD}fallback_models:{RESET}")
    for fb in removed:
        print(f"      {RED}- {_format_fallback_entry(fb)}{RESET}")
    for fb in added:
        print(f"      {GREEN}+ {_format_fallback_entry(fb)}{RESET}")
    for fb in kept:
        print(f"        {DIM}{_format_fallback_entry(fb)}{RESET}")


def print_diff(
    curr_config: dict,
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
            new_fb = patched_entry.get("fallback_models") or []
            if new_fb:
                print(f"{GREEN}+    fallback_models:{RESET}")
                for fb in new_fb:
                    print(f"{GREEN}+      {_format_fallback_entry(fb)}{RESET}")
            for key, val in patched_entry.items():
                if key in ("model", "fallback_models"):
                    continue
                print(f"{GREEN}+    {key}: {val}{RESET}")
            print()
            continue

        changes: list[tuple[str, object, object]] = []
        for key, new_val in patched_entry.items():
            old_val = curr_entry.get(key)
            if old_val is None:
                changes.append((key, None, new_val))
            elif old_val != new_val:
                changes.append((key, old_val, new_val))

        if not changes:
            print(f"  {BOLD}{DIM}{label} {name!r}{RESET}")
            print(f"    {DIM}model: {patched_entry.get('model', '?')}{RESET}")
            _print_fallbacks_dim(patched_entry.get("fallback_models") or [])
            print()
            continue

        print(f"  {BOLD}{label} {name!r}{RESET}")
        changed_keys = {key for key, _, _ in changes}

        old_model = curr_entry.get("model")
        new_model = patched_entry.get("model", "?")
        if "model" in changed_keys:
            if old_model is not None:
                print(f"    {RED}- model: {old_model}{RESET}")
            print(f"    {GREEN}+ model: {new_model}{RESET}")
        else:
            print(f"    {DIM}model: {new_model}{RESET}")

        old_fb = curr_entry.get("fallback_models") or []
        new_fb = patched_entry.get("fallback_models") or []
        if "fallback_models" in changed_keys:
            _print_fallbacks_diff(old_fb, new_fb)
        elif new_fb:
            _print_fallbacks_dim(new_fb)

        for key, old_val, new_val in changes:
            if key in ("model", "fallback_models"):
                continue
            if old_val is None:
                print(f"    {GREEN}+ {key}: {new_val}{RESET}")
            else:
                print(f"    {RED}- {key}: {old_val}{RESET}")
                print(f"    {GREEN}+ {key}: {new_val}{RESET}")
        print()


def print_profile_list(
    profiles: list[tuple[str, str, list[str]]],
    active_alias: str | None,
) -> None:
    for name, alias, providers in profiles:
        marker = f"{GREEN}● {RESET}" if alias == active_alias else "  "
        providers_str = ", ".join(providers)
        print(f"{marker}{BOLD}{name}{RESET} {DIM}({alias}){RESET}")
        print(f"    {DIM}providers: {providers_str}{RESET}")


def print_profile_status(name: str, alias: str, providers: list[str]) -> None:
    print(f"{BOLD}Active profile:{RESET} {GREEN}{name}{RESET} {DIM}({alias}){RESET}")
    print(f"{DIM}Providers: {', '.join(providers)}{RESET}")
