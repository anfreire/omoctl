from __future__ import annotations

import typing

import cyclopts

from omoctl import __version__, omo, patch, store
from omoctl.config import Config, Profile, load
from omoctl.models import load_pool
from omoctl.paths import omo_config
from omoctl.render import console, die, diff, emit, esc, heading, profile_list, profile_status

app = cyclopts.App(
    name="omoctl",
    help="Manage oh-my-openagent (OMO) profiles.",
    version=__version__,
    version_flags=["--version", "-v"],
)

Alias = typing.Annotated[bool, cyclopts.Parameter(name=["--alias", "-a"])]
Name = typing.Annotated[bool, cyclopts.Parameter(name=["--name", "-n"])]
AsJson = typing.Annotated[bool, cyclopts.Parameter(name=["--json", "-j"])]
DryRun = typing.Annotated[bool, cyclopts.Parameter(name=["--dry-run", "-n"])]


def _summary(config: Config, profile: Profile) -> str:
    flags = sorted(config.install_for(profile).items())
    return " ".join(k if v is None else f"{k}={omo.token(v)}" for k, v in flags)


def _stored(config: Config) -> dict[str, dict]:
    built = {p.alias: store.load(p.alias) for p in config.profiles}
    return {alias: cfg for alias, cfg in built.items() if cfg}


def _resolve(config: Config, name: str) -> Profile:
    profile = config.find(name)
    if profile is None:
        die(f"No profile named {name!r}. Run `omoctl list` to see them.")
    return profile


@app.default
@app.command(name="show", alias=["current", "status"])
def show(*, alias: Alias = False, name: Name = False, json: AsJson = False) -> None:
    """Show the active profile.

    Parameters
    ----------
    alias
        Print only the active profile's alias.
    name
        Print only the active profile's name.
    json
        Print only the config OpenCode is reading.
    """
    if json:
        live = omo_config()
        if not live.exists():
            die(f"Nothing at {live}. Run `omoctl update` first.")
        emit(live.read_text())
        return

    current = store.active()
    if alias:
        if not current:
            die("No active profile. Run `omoctl use <profile>` first.")
        emit(current)
        return

    config = load()  # also writes the starter config on a fresh machine
    if not current:
        if name:
            die("No active profile. Run `omoctl use <profile>` first.")
        console.print(
            "[dim]No active profile. Run `omoctl update`, then `omoctl use <profile>`.[/]"
        )
        return

    profile = config.find(current)
    if profile is None:
        if name:
            die(f"Active alias {current!r} is no longer defined in config.yaml.")
        console.print(
            f"[bold]Active profile:[/] [green]{current}[/] [dim](no longer in config.yaml)[/]"
        )
        return

    if name:
        emit(profile.name)
        return
    profile_status(profile.name, profile.alias, _summary(config, profile))


@app.command(name="list", alias="ls")
def list_() -> None:
    """List every profile."""
    config = load()
    profile_list(
        [(p.name, p.alias, _summary(config, p)) for p in config.profiles],
        store.active(),
    )


@app.command(alias=["apply", "switch"])
def use(profile: str) -> None:
    """Activate a profile.

    Parameters
    ----------
    profile
        Profile name or alias.
    """
    config = load()
    target = _resolve(config, profile)
    built = _stored(config)
    if target.alias not in built:
        die(f"{target.name!r} has not been built yet. Run `omoctl update {target.alias}` first.")

    store.activate(target.alias, built)
    console.print(f"[green]Switched to[/] [bold]{target.name}[/]")


@app.command(alias=["build", "upgrade"])
def update(profile: str | None = None, *, dry_run: DryRun = False) -> None:
    """Fetch fresh OMO configs, apply patches, and save.

    Parameters
    ----------
    profile
        Profile name or alias. Every profile if omitted.
    dry_run
        Show what would change without writing anything.
    """
    config = load()
    targets = [_resolve(config, profile)] if profile else list(config.profiles)

    console.print("[dim]Refreshing models from opencode...[/]")
    pool = load_pool(refresh=True)

    for target in targets:
        flags = tuple(sorted(config.install_for(target).items()))
        heading(target.name)
        console.print(f"[dim]{' '.join(omo.render(flags))}[/]\n")

        patches = config.patches_for(target)
        drops = config.drops_for(target)
        source, produced_at = omo.fetch(flags)
        result, report = patch.build(source, pool, patches, drops, config.overrides_for(target))

        diff(dict(patch.entries(store.load(target.alias) or {})), dict(patch.entries(result)))
        _report(report, patches, drops)

        if not dry_run:
            store.save(target.alias, result)
            store.remember_target(produced_at)

    if dry_run:
        console.print("[dim]Dry run — nothing written.[/]")
        return

    for stale in store.prune({p.alias for p in config.profiles}):
        console.print(f"[dim]Removed stale profile {stale!r}.[/]")

    built = _stored(config)
    keep = config.activate or store.active()
    chosen = config.find(keep) if keep else None
    if chosen and chosen.alias in built:
        store.activate(chosen.alias, built)
        console.print(f"[green]Active:[/] [bold]{chosen.name}[/]")


def _plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


def _report(report: patch.Report, patches: list, drops: list) -> None:
    printed = False
    for index, count in sorted(report.fired.items()):
        printed = True
        label = esc(patches[index].match.label)
        console.print(f"  [dim]{label} → {_plural(count, 'model', 'models')}[/]")
    for index, entry in enumerate(patches):
        if index not in report.fired:
            printed = True
            console.print(f"  [yellow]no match:[/] [dim]{esc(entry.match.label)}[/]")
    if drops:
        printed = True
        console.print(f"  [dim]drop → {_plural(report.dropped, 'entry', 'entries')}[/]")
    if report.deduped:
        printed = True
        console.print(f"  [dim]deduped → {_plural(report.deduped, 'entry', 'entries')}[/]")
    for path, wanted, got in report.inexact:
        printed = True
        console.print(f"  [yellow]{esc(wanted)} is gone;[/] {esc(path)} → [bold]{esc(got)}[/]")
    for provider in sorted(report.unlisted):
        printed = True
        console.print(
            f"  [yellow]{esc(provider)} is not in `opencode models`;[/] its ids went unchecked"
        )
    if printed:
        console.print()


@app.command(alias="rm")
def remove(profile: str) -> None:
    """Delete a built profile. Its definition stays in config.yaml.

    Parameters
    ----------
    profile
        Profile name or alias.
    """
    config = load()
    target = _resolve(config, profile)
    store.remove(target.alias)
    console.print(f"[green]Removed built profile[/] [bold]{target.name}[/]")


@app.command
def providers() -> None:
    """Show every flag `install:` accepts, straight from oh-my-openagent."""
    emit(omo.install_help())


def main() -> None:
    try:
        app()
    except KeyboardInterrupt:
        raise SystemExit(130) from None
