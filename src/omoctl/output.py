from __future__ import annotations

import json
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

# Distinguishes "key absent" from "key explicitly null" when diffing.
_MISSING: typing.Final = object()


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


def _fmt(val: object) -> str:
    """Render a config value the way it appears in the stored JSON
    (null/true/false instead of Python's None/True/False)."""
    if isinstance(val, str):
        return val
    try:
        return json.dumps(val)
    except (TypeError, ValueError):
        return str(val)


def _format_model_variant(entry: dict) -> str:
    """Render an entry's model with its variant inline: `model (variant: x)`.

    Used for both the main model line and fallback entries so the two
    always present variants the same way.
    """
    model = entry.get("model", "?")
    variant = entry.get("variant")
    if variant is not None:
        return f"{_fmt(model)} (variant: {_fmt(variant)})"
    return _fmt(model)


def _model_variant_segments(
    entry: dict, model_changed: bool, variant_changed: bool, accent: str
) -> str:
    """Like _format_model_variant, but each segment is accent-colored only
    if it actually changed; the unchanged segment renders dim."""
    model_color = accent if model_changed else DIM
    text = f"{model_color}{_fmt(entry.get('model', '?'))}{RESET}"
    variant = entry.get("variant")
    if variant is not None:
        variant_color = accent if variant_changed else DIM
        text += f" {variant_color}(variant: {_fmt(variant)}){RESET}"
    return text


def _fb_key(fb: dict) -> str:
    try:
        return json.dumps(fb, sort_keys=True)
    except (TypeError, ValueError):
        return str(sorted(fb.items(), key=str))


def _print_fallbacks_dim(fallbacks: list[dict]) -> None:
    if not fallbacks:
        return
    print(f"    {DIM}fallback_models:{RESET}")
    for fb in fallbacks:
        print(f"        {DIM}{_format_model_variant(fb)}{RESET}")


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
        print(f"      {RED}- {_format_model_variant(fb)}{RESET}")
    for fb in added:
        print(f"      {GREEN}+ {_format_model_variant(fb)}{RESET}")
    for fb in kept:
        print(f"        {DIM}{_format_model_variant(fb)}{RESET}")


def _print_new_entry(label: str, name: str, patched_entry: dict) -> None:
    print(f"{GREEN}+  {BOLD}{label} {name!r}{RESET}")
    print(f"{GREEN}+    model: {_format_model_variant(patched_entry)}{RESET}")
    new_fb = patched_entry.get("fallback_models") or []
    if new_fb:
        print(f"{GREEN}+    fallback_models:{RESET}")
        for fb in new_fb:
            print(f"{GREEN}+      {_format_model_variant(fb)}{RESET}")
    for key, val in patched_entry.items():
        if key in ("model", "variant", "fallback_models"):
            continue
        print(f"{GREEN}+    {key}: {_fmt(val)}{RESET}")
    print()


def print_diff(
    curr_config: dict | None,
    patched_config: dict,
    keys: list[tuple[str, str]],
) -> None:
    if curr_config is None:
        curr_config = {}

    for section, name in keys:
        curr_section = curr_config.get(section)
        curr_entry = curr_section.get(name) if isinstance(curr_section, dict) else None
        patched_entry = patched_config[section][name]
        label = parse_section_label(section)

        if not isinstance(patched_entry, dict):
            # An override replaced the whole entry; show it verbatim.
            print(f"  {BOLD}{label} {name!r}{RESET}")
            print(f"    {GREEN}+ {_fmt(patched_entry)}{RESET}")
            print()
            continue

        if not isinstance(curr_entry, dict):
            _print_new_entry(label, name, patched_entry)
            continue

        # The model and its variant render as one unit, exactly like
        # fallback entries: `model (variant: x)`. Comparing via .get() means
        # an explicit-null variant and an absent one never report as churn.
        model_changed = curr_entry.get("model") != patched_entry.get("model")
        variant_changed = curr_entry.get("variant") != patched_entry.get("variant")

        # Diff the remaining keys over the union so removals are visible too.
        changes: list[tuple[str, object, object]] = []
        for key, new_val in patched_entry.items():
            if key in ("model", "variant"):
                continue
            if key not in curr_entry:
                changes.append((key, _MISSING, new_val))
            elif curr_entry[key] != new_val:
                changes.append((key, curr_entry[key], new_val))
        for key, old_val in curr_entry.items():
            if key in ("model", "variant"):
                continue
            if key not in patched_entry:
                changes.append((key, old_val, _MISSING))

        if not model_changed and not variant_changed and not changes:
            print(f"  {BOLD}{DIM}{label} {name!r}{RESET}")
            print(f"    {DIM}model: {_format_model_variant(patched_entry)}{RESET}")
            _print_fallbacks_dim(patched_entry.get("fallback_models") or [])
            print()
            continue

        print(f"  {BOLD}{label} {name!r}{RESET}")
        changed_keys = {key for key, _, _ in changes}

        # Within the -/+ model lines only the segment that changed gets the
        # accent color; the other is dim.
        if model_changed or variant_changed:
            if (
                curr_entry.get("model") is not None
                or curr_entry.get("variant") is not None
            ):
                print(
                    f"    {RED}- model: {RESET}"
                    + _model_variant_segments(
                        curr_entry, model_changed, variant_changed, RED
                    )
                )
            print(
                f"    {GREEN}+ model: {RESET}"
                + _model_variant_segments(
                    patched_entry, model_changed, variant_changed, GREEN
                )
            )
        else:
            print(f"    {DIM}model: {_format_model_variant(patched_entry)}{RESET}")

        old_fb = curr_entry.get("fallback_models") or []
        new_fb = patched_entry.get("fallback_models") or []
        if "fallback_models" in changed_keys:
            _print_fallbacks_diff(old_fb, new_fb)
        elif new_fb:
            _print_fallbacks_dim(new_fb)

        for key, old_val, new_val in changes:
            if key in ("model", "variant", "fallback_models"):
                continue
            if old_val is _MISSING:
                print(f"    {GREEN}+ {key}: {_fmt(new_val)}{RESET}")
            elif new_val is _MISSING:
                print(f"    {RED}- {key}: {_fmt(old_val)}{RESET}")
            else:
                print(f"    {RED}- {key}: {_fmt(old_val)}{RESET}")
                print(f"    {GREEN}+ {key}: {_fmt(new_val)}{RESET}")
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
