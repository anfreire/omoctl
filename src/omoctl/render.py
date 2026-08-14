"""Terminal output. A leaf module: it knows dicts and strings, nothing else."""

from __future__ import annotations

import json
import sys
import typing

import rich.console
import rich.markup

console: typing.Final = rich.console.Console(highlight=False, soft_wrap=True)
_err: typing.Final = rich.console.Console(stderr=True, highlight=False, soft_wrap=True)

Json = dict[str, typing.Any]

# OMO's harness blocks are literally named `[opencode]`, which rich would read
# as a style tag. Everything interpolated into markup goes through this.
esc = rich.markup.escape


def die(message: str) -> typing.NoReturn:
    _err.print(f"[red]Error:[/] {esc(message)}")
    raise SystemExit(1)


def emit(text: str) -> None:
    """Unstyled, unwrapped output for anything a script might read."""
    sys.stdout.write(text if text.endswith("\n") else text + "\n")


def heading(text: str) -> None:
    console.print(f"\n[bold cyan]{esc(text)}[/]")
    console.print("[dim]" + "─" * min(len(text), 60) + "[/]")


def _scalar(value: object) -> str:
    return value if isinstance(value, str) else json.dumps(value)


def describe(entry: object) -> str:
    """`anthropic/claude-opus-5 (variant: max)` for an entry or a bare id.

    Empty when the entry carries no model of its own — some only hold a
    `models` list, and those render as just that list.
    """
    if not isinstance(entry, dict):
        return _scalar(entry)
    if "model" not in entry:
        return ""
    attrs = [
        f"{key}: {_scalar(value)}"
        for key, value in entry.items()
        if key != "model"
        and not key.endswith("models")
        and not isinstance(value, (dict, list))
        and len(_scalar(value)) <= 40
    ]
    model = _scalar(entry["model"])
    return f"{model} ({', '.join(attrs)})" if attrs else model


def _lists(entry: Json) -> dict[str, list]:
    return {k: v for k, v in entry.items() if k.endswith("models") and isinstance(v, list)}


def _path(path: str) -> str:
    head, _, tail = path.rpartition(".")
    return f"[dim]{esc(head)}.[/][bold]{esc(tail)}[/]" if head else f"[bold]{esc(tail)}[/]"


def _entry_lines(entry: Json, marker: str, style: str) -> typing.Iterator[str]:
    if head := describe(entry):
        yield f"[{style}]{marker} model: {esc(head)}[/]"
    for key, items in _lists(entry).items():
        yield f"[{style}]{marker} {esc(key)}:[/]"
        for item in items:
            yield f"[{style}]{marker}     {esc(describe(item))}[/]"


def diff(before: dict[str, Json], after: dict[str, Json]) -> None:
    """Render `path -> entry` maps side by side."""
    for path in dict.fromkeys([*after, *before]):
        old, new = before.get(path), after.get(path)

        if new is None:
            console.print(f"  {_path(path)}")
            for line in _entry_lines(old or {}, "-", "red"):
                console.print(f"    {line}")
            console.print()
            continue

        if old is None:
            console.print(f"  {_path(path)}")
            for line in _entry_lines(new, "+", "green"):
                console.print(f"    {line}")
            console.print()
            continue

        if old == new:
            console.print(f"  [dim]{esc(path)}[/]")
            if head := describe(new):
                console.print(f"    [dim]model: {esc(head)}[/]")
            for key, items in _lists(new).items():
                console.print(f"    [dim]{esc(key)}:[/]")
                for item in items:
                    console.print(f"        [dim]{esc(describe(item))}[/]")
            console.print()
            continue

        console.print(f"  {_path(path)}")
        old_head, new_head = describe(old), describe(new)
        if old_head != new_head:
            if old_head:
                console.print(f"    [red]- model: {esc(old_head)}[/]")
            if new_head:
                console.print(f"    [green]+ model: {esc(new_head)}[/]")
        elif new_head:
            console.print(f"    [dim]model: {esc(new_head)}[/]")

        old_lists, new_lists = _lists(old), _lists(new)
        for key in dict.fromkeys([*new_lists, *old_lists]):
            _list_diff(key, old_lists.get(key, []), new_lists.get(key, []))
        console.print()


def _list_diff(key: str, old: list, new: list) -> None:
    was = [esc(describe(item)) for item in old]
    now = [esc(describe(item)) for item in new]
    if was == now:
        if now:
            console.print(f"    [dim]{esc(key)}:[/]")
            for item in now:
                console.print(f"        [dim]{item}[/]")
        return

    console.print(f"    [bold]{esc(key)}:[/]")
    for item in was:
        if item not in now:
            console.print(f"      [red]- {item}[/]")
    for item in now:
        console.print(f"      [green]+ {item}[/]" if item not in was else f"        [dim]{item}[/]")


def profile_list(rows: list[tuple[str, str, str]], active: str | None) -> None:
    for name, alias, summary in rows:
        marker = "[green]●[/] " if alias == active else "  "
        console.print(f"{marker}[bold]{esc(name)}[/] [dim]({esc(alias)})[/]")
        console.print(f"    [dim]{esc(summary)}[/]")


def profile_status(name: str, alias: str, summary: str) -> None:
    console.print(f"[bold]Active profile:[/] [green]{esc(name)}[/] [dim]({esc(alias)})[/]")
    console.print(f"[dim]{esc(summary)}[/]")
