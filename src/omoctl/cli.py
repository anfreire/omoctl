from __future__ import annotations

import argparse
import sys

from omoctl import __version__
from omoctl.config import load_config
from omoctl.models import ModelCache, enrich_cache_with_omo, load_models
from omoctl.omo import fetch_omo_config
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
from omoctl.patching import apply_patches_to_config
from omoctl.paths import ACTIVE_CONFIG_PATH
from omoctl.store import (
    activate_profile,
    cleanup_stale,
    get_active_alias,
    get_profile_config,
    remove_profile,
    save_profile,
)
from omoctl.validate import print_validation_result, validate_config


def cmd_status(args: argparse.Namespace) -> None:
    # The state file (written on every activation) is the single source of
    # truth for what is active; the config's `active_profile` pin only
    # drives auto-activation after `update`.
    if getattr(args, "alias", False):
        active_alias = get_active_alias()
        if not active_alias:
            die("No active profile. Run 'omoctl use <profile>' first.")
        print(active_alias)
        return

    if getattr(args, "name", False):
        active_alias = get_active_alias()
        if not active_alias:
            die("No active profile. Run 'omoctl use <profile>' first.")
        config = load_config()
        profile = config.find_profile(active_alias)
        if profile is None:
            die(f"Active alias {active_alias!r} is not defined in config.yaml.")
        print(profile.name)
        return

    if getattr(args, "json", False):
        if not ACTIVE_CONFIG_PATH.exists():
            die(
                f"No active config at {ACTIVE_CONFIG_PATH}.\n"
                f"  Run 'omoctl use <profile>' or 'omoctl update' first."
            )
        print(ACTIVE_CONFIG_PATH.read_text())
        return

    config = load_config()
    active_alias = get_active_alias()

    if not active_alias:
        print(f"{DIM}No active profile.{RESET}")
        print(
            f"{DIM}Run 'omoctl update' to build profiles, "
            f"then 'omoctl use <profile>' to activate one.{RESET}"
        )
        return

    profile = config.find_profile(active_alias)
    if profile is None:
        print(
            f"{BOLD}Active profile:{RESET} {GREEN}{active_alias}{RESET} "
            f"{DIM}(not defined in config.yaml){RESET}"
        )
        print(
            f"{DIM}The active config still applies, but 'omoctl update' "
            f"will not rebuild it.{RESET}"
        )
        return

    print_profile_status(profile.name, profile.alias, profile.providers)


def cmd_list(_args: argparse.Namespace) -> None:
    config = load_config()
    active_alias = get_active_alias()

    profiles = [(p.name, p.alias, p.providers) for p in config.profiles]

    if not profiles:
        print(f"{DIM}No profiles defined in config.{RESET}")
        return

    print_profile_list(profiles, active_alias)


def cmd_use(args: argparse.Namespace) -> None:
    config = load_config()
    profile = config.find_profile(args.profile)

    if profile is None:
        die(
            f"Profile {args.profile!r} not found. Run 'omoctl list' to see available profiles."
        )

    stored_config = get_profile_config(profile.alias)
    if stored_config is None:
        die(
            f"Profile {profile.name!r} has no stored config.\n"
            f"  Run 'omoctl update {profile.alias}' first to fetch and build it."
        )

    activate_profile(profile.alias, stored_config)
    print(f"{GREEN}Switched to profile: {BOLD}{profile.name}{RESET}")


def cmd_update(args: argparse.Namespace) -> None:
    config = load_config()
    state_alias = get_active_alias()

    if args.profile:
        profile = config.find_profile(args.profile)
        if profile is None:
            die(f"Profile {args.profile!r} not found.")
        profiles = [profile]
    else:
        profiles = list(config.profiles)

    print(f"{DIM}Refreshing model list from opencode...{RESET}\n")
    provider_to_models = load_models(refresh=True)
    cache = ModelCache(provider_to_models=provider_to_models)

    for idx, profile in enumerate(profiles):
        if idx:
            print()
        print_section(profile.name)
        print()

        omo_config = fetch_omo_config(tuple(profile.providers))
        enriched_cache = enrich_cache_with_omo(cache, omo_config)

        curr_config = get_profile_config(profile.alias)

        patched_config, keys = apply_patches_to_config(
            enriched_cache,
            profile,
            omo_config,
            config,
        )

        save_profile(profile.alias, patched_config)

        print_diff(curr_config, patched_config, keys)

    # Auto-activate the pinned profile if set, else restore the previously
    # active one.
    to_activate = config.get_active_profile()
    if config.active_profile and to_activate is None:
        print(
            f"{DIM}Warning: active_profile {config.active_profile!r} does not "
            f"match any profile; skipping auto-activation.{RESET}"
        )
    if to_activate is None and state_alias:
        to_activate = config.find_profile(state_alias)
    if to_activate:
        stored = get_profile_config(to_activate.alias)
        if stored:
            activate_profile(to_activate.alias, stored)

    valid_aliases = {p.alias for p in config.profiles}
    cleanup_stale(valid_aliases)


def cmd_remove(args: argparse.Namespace) -> None:
    config = load_config()
    profile = config.find_profile(args.profile)

    if profile is None:
        die(f"Profile {args.profile!r} not found.")

    remove_profile(profile.alias)
    print(f"{GREEN}Removed profile: {BOLD}{profile.name}{RESET}")
    print(
        f"{DIM}Note: the profile definition is still in config.yaml. Edit it to remove permanently.{RESET}"
    )


def cmd_check(_args: argparse.Namespace) -> None:
    config = load_config()
    provider_to_models = load_models(refresh=False)
    cache = ModelCache(provider_to_models=provider_to_models)

    all_providers = set()
    for profile in config.profiles:
        all_providers.update(profile.providers)
    omo_config = fetch_omo_config(tuple(sorted(all_providers)), quiet=True)
    enriched_cache = enrich_cache_with_omo(cache, omo_config)

    errors = validate_config(config, enriched_cache)
    if not print_validation_result(errors):
        sys.exit(1)


def cmd_version(_args: argparse.Namespace) -> None:
    print(f"omoctl {__version__}")


def _add_status_flags(p: argparse.ArgumentParser) -> None:
    # SUPPRESS keeps a subparser from clobbering a flag already parsed at
    # the top level, so `omoctl -a show` behaves like `omoctl show -a`.
    group = p.add_mutually_exclusive_group()
    group.add_argument(
        "-a",
        "--alias",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Print only the active profile alias",
    )
    group.add_argument(
        "-n",
        "--name",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Print only the active profile name",
    )
    group.add_argument(
        "-j",
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Print only the raw JSON config",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="omoctl",
        description="Manage oh-my-openagent (OMO) profiles",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"omoctl {__version__}",
    )
    _add_status_flags(parser)
    parser.set_defaults(func=cmd_status)

    sub = parser.add_subparsers(dest="command")

    show_p = sub.add_parser(
        "show",
        aliases=["current", "status"],
        help="Show active profile (default)",
    )
    _add_status_flags(show_p)
    show_p.set_defaults(func=cmd_status)

    list_p = sub.add_parser("list", aliases=["ls"], help="List all profiles")
    list_p.set_defaults(func=cmd_list)

    use_p = sub.add_parser(
        "use",
        aliases=["apply", "switch"],
        help="Activate a profile",
    )
    use_p.add_argument("profile", help="Profile name or alias")
    use_p.set_defaults(func=cmd_use)

    update_p = sub.add_parser(
        "update",
        aliases=["build", "upgrade"],
        help="Update profiles (fetch + patch + save)",
    )
    update_p.add_argument(
        "profile",
        nargs="?",
        default=None,
        help="Profile name or alias (all if omitted)",
    )
    update_p.set_defaults(func=cmd_update)

    remove_p = sub.add_parser(
        "remove",
        aliases=["rm"],
        help="Remove a stored profile",
    )
    remove_p.add_argument("profile", help="Profile name or alias")
    remove_p.set_defaults(func=cmd_remove)

    check_p = sub.add_parser(
        "check",
        aliases=["validate", "verify"],
        help="Check config against available models/agents",
    )
    check_p.set_defaults(func=cmd_check)

    version_p = sub.add_parser("version", help="Print version")
    version_p.set_defaults(func=cmd_version)

    args = parser.parse_args()
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        sys.exit(130)
