"""Finding and rewriting every model reference in an OMO config.

Nothing here names a section. A key is a model reference if it is `model` or
ends in `models` (`fallback_models`, `models`, and whatever comes next), and
its value may be a bare `provider/id` string, a list of those, or a list of
objects. Walking on that rule alone means new sections, new harness blocks and
new list-shaped keys are covered the day OMO adds them.
"""

from __future__ import annotations

import copy
import dataclasses
import fnmatch
import json
import typing

from omoctl.config import Json, Match, Patch, deep_merge
from omoctl.models import Pool, filter_matches, parse_filter, resolve
from omoctl.render import die

MODEL_KEY: typing.Final = "model"
_KEEP: typing.Final = object()


def is_model_key(key: str) -> bool:
    return key == MODEL_KEY or key.endswith("models")


def is_reference(value: typing.Any) -> bool:
    """Model references are `provider/id`. A key that merely reads like one
    (a future `disabled_models: [sisyphus]`) holds names, not models."""
    return isinstance(value, str) and "/" in value


Apply = typing.Callable[[str, Json], None]


@dataclasses.dataclass(slots=True)
class Site:
    """One model reference, plus how to rewrite it in place."""

    path: str
    model: str
    _apply: Apply

    @property
    def provider(self) -> str:
        return self.model.partition("/")[0] if "/" in self.model else ""

    @property
    def name(self) -> str:
        return self.model.partition("/")[2] if "/" in self.model else self.model

    def write(self, model: str, extras: Json) -> None:
        self._apply(model, extras)


def _slot(container: typing.Any, key: typing.Any) -> Apply:
    """A bare `provider/id` string. Extra keys force it into object form."""

    def apply(model: str, extras: Json) -> None:
        assigned = {k: v for k, v in extras.items() if v is not None}
        container[key] = {MODEL_KEY: model, **assigned} if assigned else model

    return apply


def _entry(entry: Json) -> Apply:
    """An object that carries `model` alongside its own keys."""

    def apply(model: str, extras: Json) -> None:
        entry[MODEL_KEY] = model
        for key, value in extras.items():
            if value is None:
                entry.pop(key, None)
            else:
                entry[key] = value

    return apply


def sites(node: typing.Any, path: str = "") -> typing.Iterator[Site]:
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else key
            if key == MODEL_KEY and is_reference(value):
                yield Site(here, value, _entry(node))
            elif is_model_key(key):
                yield from _in_model_key(value, here, node, key)
            else:
                yield from sites(value, here)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            yield from sites(item, f"{path}.{index}")


def _in_model_key(value: typing.Any, path: str, owner: Json, key: str) -> typing.Iterator[Site]:
    if isinstance(value, str):
        if is_reference(value):
            yield Site(path, value, _slot(owner, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            here = f"{path}.{index}"
            if isinstance(item, str):
                if is_reference(item):
                    yield Site(here, item, _slot(value, index))
            else:
                yield from sites(item, here)
    else:
        yield from sites(value, path)


def entries(node: typing.Any, path: str = "") -> typing.Iterator[tuple[str, Json]]:
    """Objects that own a model reference, not descending into their lists.

    This is the unit the diff renders: `[opencode].agents.oracle`, with its
    `fallback_models` shown inline rather than as separate rows. An object with
    only a `models` list and no `model` of its own still counts, so nothing that
    was patched can go missing from the diff.
    """
    if isinstance(node, dict):
        if any(is_model_key(key) for key in node):
            yield path, node
            return
        for key, value in node.items():
            yield from entries(value, f"{path}.{key}" if path else key)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            yield from entries(item, f"{path}.{index}")


def matches(match: Match, path: str, model: str) -> bool:
    provider, slash, name = model.partition("/")
    if not slash:
        provider, name = "", provider
    if match.glob and not fnmatch.fnmatch(path, match.glob):
        return False
    if match.provider and match.provider != provider:
        return False
    return match.spec is None or filter_matches(match.spec, name)


def _model_of(item: typing.Any) -> str | None:
    if is_reference(item):
        return typing.cast(str, item)
    if isinstance(item, dict) and is_reference(item.get(MODEL_KEY)):
        return typing.cast(str, item[MODEL_KEY])
    return None


def _item_path(item: typing.Any, path: str) -> str:
    """The path `sites` would give this list item's model reference."""
    return f"{path}.{MODEL_KEY}" if isinstance(item, dict) else path


def drop(node: typing.Any, drops: list[Match], path: str = "") -> int:
    """Remove matching entries from every `*models` list. Returns the count.

    Descendants are visited at their original indexes, so removing one entry
    never shifts the path another rule is written against.
    """
    removed = 0
    if isinstance(node, dict):
        for key in list(node):
            value = node[key]
            here = f"{path}.{key}" if path else key
            if is_model_key(key) and key != MODEL_KEY and isinstance(value, list):
                kept = []
                for index, item in enumerate(value):
                    at = f"{here}.{index}"
                    model = _model_of(item)
                    if model is not None and any(
                        matches(d, _item_path(item, at), model) for d in drops
                    ):
                        removed += 1
                        continue
                    kept.append(item)
                    removed += drop(item, drops, at)
                node[key] = kept
            else:
                removed += drop(value, drops, here)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            removed += drop(item, drops, f"{path}.{index}")
    return removed


def _fingerprint(item: typing.Any) -> str:
    """Bare `provider/id` and `{"model": "provider/id"}` are the same entry."""
    fields = dict(item) if isinstance(item, dict) else {MODEL_KEY: item}
    return json.dumps(fields, sort_keys=True, default=str)


def dedupe(node: typing.Any) -> int:
    """Collapse repeats within each `*models` list, keeping the first.

    A patch scoped to a whole entry rewrites its fallbacks too, so several
    distinct fallbacks can land on the same model. Listing one model twice as
    its own backup is never what was meant.
    """
    removed = 0
    if isinstance(node, dict):
        for key, value in node.items():
            if is_model_key(key) and key != MODEL_KEY and isinstance(value, list):
                seen: set[str] = set()
                kept = []
                for item in value:
                    fingerprint = _fingerprint(item)
                    if fingerprint in seen:
                        removed += 1
                        continue
                    seen.add(fingerprint)
                    kept.append(item)
                node[key] = kept
            removed += dedupe(node[key])
    elif isinstance(node, list):
        for item in node:
            removed += dedupe(item)
    return removed


@dataclasses.dataclass(slots=True)
class Report:
    fired: dict[int, int] = dataclasses.field(default_factory=dict)
    dropped: int = 0
    deduped: int = 0
    inexact: list[tuple[str, str, str]] = dataclasses.field(default_factory=list)
    unlisted: set[str] = dataclasses.field(default_factory=set)


def build(
    source: Json,
    pool: Pool,
    patches: list[Patch],
    drops: list[Match],
    overrides: Json,
) -> tuple[Json, Report]:
    """Apply drops, then patches, then overrides. `source` is left untouched."""
    config = copy.deepcopy(source)
    report = Report()

    if drops:
        report.dropped = drop(config, drops)

    for site in list(sites(config)):
        index = next(
            (i for i, patch in enumerate(patches) if matches(patch.match, site.path, site.model)),
            None,
        )
        if index is None:
            continue
        report.fired[index] = report.fired.get(index, 0) + 1
        _rewrite(site, patches[index], pool, report)

    report.deduped = dedupe(config)
    return (deep_merge(config, overrides) if overrides else config), report


def _rewrite(site: Site, patch: Patch, pool: Pool, report: Report) -> None:
    extras = dict(patch.set)
    provider = extras.pop("provider", None)
    want = extras.pop(MODEL_KEY, _KEEP)

    if provider is None and want is _KEEP:
        site.write(site.model, extras)
        return

    target = provider or site.provider
    if not target:
        die(f"{site.path}: {site.model!r} has no provider, so the patch must set one.")

    if target not in pool:
        report.unlisted.add(str(target))

    spec = None if want is _KEEP else parse_filter(want)
    model, exact = resolve(pool, str(target), spec, site.name or None)
    if not exact or (isinstance(want, str) and model != f"{target}/{want}"):
        asked = f"{target}/{want}" if isinstance(want, str) else f"{target} {want}"
        report.inexact.append((site.path, asked, model))
    site.write(model, extras)
