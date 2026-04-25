from __future__ import annotations

import argparse
import sys

from omoctl import __version__
from omoctl.config import load_config
from omoctl.models import enrich_cache_with_omo, load_model_cache
from omoctl.omo import fetch_omo_config
from omoctl.validate import print_validation_result, validate_config
from omoctl.output import (
    BOLD,
    DIM,
    GREEN,
    RESET,
    die,
    print_diff,
    print_profile_list,
    print_profile_status,
    print_section,
)
from omoctl.paths import ACTIVE_CONFIG_PATH
from omoctl.patching import apply_patches_to_config
from omoctl.store import (
    activate_profile,
    cleanup_stale,
    get_active_alias,
    get_profile_config,
    save_profile,
    remove_profile,
)


def cmd_status(_args: argparse.Namespace) -> None:
    config = load_config()
    active_alias = get_active_alias()

    profile = None
    if config.active_profile:
        profile = config.find_profile(config.active_profile)
    if profile is None and active_alias:
        profile = config.find_profile(active_alias)

    if profile is None:
        print(f"{DIM}No active profile.{RESET}")
        print(f"{DIM}Run 'omoctl list' to see available profiles.{RESET}")
        return

    print_profile_status(profile.name, profile.alias, profile.providers)


def cmd_list(_args: argparse.Namespace) -> None:
    config = load_config()
    active_profile = config.get_active_profile()
    active_alias = (
        active_profile.alias if active_profile else get_active_alias()
    )

    profiles = [
        (p.name, p.alias, p.providers) for p in config.profiles
    ]

    if not profiles:
        print(f"{DIM}No profiles defined in config.{RESET}")
        return

    print_profile_list(profiles, active_alias)


def cmd_switch(args: argparse.Namespace) -> None:
    config = load_config()
    profile = config.find_profile(args.profile)

    if profile is None:
        die(f"Profile {args.profile!r} not found. Run 'omoctl list' to see available profiles.")

    stored_config = get_profile_config(profile.alias)
    if stored_config is None:
        die(
            f"Profile {profile.name!r} has no stored config.\n"
            f"  Run 'omoctl update {profile.alias}' first to fetch and build it."
        )

    activate_profile(profile.alias, profile.name, stored_config)
    print(f"{GREEN}Switched to profile: {BOLD}{profile.name}{RESET}")


def cmd_update(args: argparse.Namespace) -> None:
    config = load_config()

    if args.profile:
        profile = config.find_profile(args.profile)
        if profile is None:
            die(f"Profile {args.profile!r} not found.")
        profiles = [profile]
    else:
        profiles = list(config.profiles)

    cache = load_model_cache()

    active_profile = config.get_active_profile()
    active_alias = active_profile.alias if active_profile else get_active_alias()

    for idx, profile in enumerate(profiles):
        if idx:
            print()
        print_section(profile.name)
        print()

        omo_config = fetch_omo_config(tuple(profile.providers))
        enriched_cache = enrich_cache_with_omo(cache, omo_config)

        curr_config = get_profile_config(profile.alias)

        patched_config, keys = apply_patches_to_config(
            enriched_cache, profile, omo_config, config,
        )

        save_profile(profile.alias, profile.name, patched_config)

        print_diff(curr_config, patched_config, keys)

    to_activate = config.get_active_profile()
    if not to_activate and active_alias:
        to_activate = config.find_profile(active_alias)
    if to_activate:
        stored = get_profile_config(to_activate.alias)
        if stored:
            activate_profile(to_activate.alias, to_activate.name, stored)

    valid_aliases = {p.alias for p in config.profiles}
    cleanup_stale(valid_aliases)


def cmd_remove(args: argparse.Namespace) -> None:
    config = load_config()
    profile = config.find_profile(args.profile)

    if profile is None:
        die(f"Profile {args.profile!r} not found.")

    remove_profile(profile.alias)
    print(f"{GREEN}Removed profile: {BOLD}{profile.name}{RESET}")
    print(f"{DIM}Note: the profile definition is still in config.yaml. Edit it to remove permanently.{RESET}")


def cmd_validate(_args: argparse.Namespace) -> None:
    config = load_config()
    cache = load_model_cache()

    all_providers = set()
    for profile in config.profiles:
        all_providers.update(profile.providers)
    omo_config = fetch_omo_config(tuple(sorted(all_providers)), quiet=True)
    enriched_cache = enrich_cache_with_omo(cache, omo_config)

    errors = validate_config(config, enriched_cache)
    if not print_validation_result(errors):
        sys.exit(1)


def cmd_show(args: argparse.Namespace) -> None:
    if args.alias:
        alias = get_active_alias()
        if not alias:
            die("No active profile. Run 'omoctl switch <profile>' first.")
        print(alias)
        return

    if args.name:
        alias = get_active_alias()
        if not alias:
            die("No active profile. Run 'omoctl switch <profile>' first.")
        config = load_config()
        profile = config.find_profile(alias)
        if profile is None:
            die(f"Active alias {alias!r} is not defined in config.yaml.")
        print(profile.name)
        return

    if not ACTIVE_CONFIG_PATH.exists():
        die(
            f"No active config at {ACTIVE_CONFIG_PATH}.\n"
            f"  Run 'omoctl switch <profile>' or 'omoctl update' first."
        )

    if args.json:
        print(ACTIVE_CONFIG_PATH.read_text())
        return

    alias = get_active_alias()
    config = load_config()
    profile = config.find_profile(alias) if alias else None

    if profile:
        print(
            f"{BOLD}Profile:{RESET} "
            f"{GREEN}{profile.name}{RESET} {DIM}({profile.alias}){RESET}"
        )
    elif alias:
        print(f"{BOLD}Profile:{RESET} {DIM}{alias}{RESET}")
    print()
    print(ACTIVE_CONFIG_PATH.read_text())


def cmd_version(_args: argparse.Namespace) -> None:
    print(f"omoctl {__version__}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="omoctl",
        description="Manage oh-my-openagent (OMO) profiles",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"omoctl {__version__}",
    )
    parser.set_defaults(func=cmd_status)

    sub = parser.add_subparsers(dest="command")

    list_p = sub.add_parser("list", help="List all profiles")
    list_p.set_defaults(func=cmd_list)

    switch_p = sub.add_parser("switch", help="Switch to a profile")
    switch_p.add_argument("profile", help="Profile name or alias")
    switch_p.set_defaults(func=cmd_switch)

    update_p = sub.add_parser("update", help="Update profiles (fetch + patch + save)")
    update_p.add_argument("profile", nargs="?", default=None, help="Profile name or alias (all if omitted)")
    update_p.set_defaults(func=cmd_update)

    remove_p = sub.add_parser("remove", help="Remove a stored profile")
    remove_p.add_argument("profile", help="Profile name or alias")
    remove_p.set_defaults(func=cmd_remove)

    validate_p = sub.add_parser("validate", help="Validate config against available models/agents")
    validate_p.set_defaults(func=cmd_validate)

    show_p = sub.add_parser(
        "show", help="Show the active profile (header + JSON by default)"
    )
    show_mode = show_p.add_mutually_exclusive_group()
    show_mode.add_argument(
        "-a", "--alias", action="store_true",
        help="Print only the active profile alias",
    )
    show_mode.add_argument(
        "-n", "--name", action="store_true",
        help="Print only the active profile name",
    )
    show_mode.add_argument(
        "-j", "--json", action="store_true",
        help="Print only the raw JSON config (no header)",
    )
    show_p.set_defaults(func=cmd_show)

    version_p = sub.add_parser("version", help="Print version")
    version_p.set_defaults(func=cmd_version)

    args = parser.parse_args()
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        sys.exit(130)
