"""Model identifiers: how they are described, matched, and resolved.

A model id is treated as an unordered bag of words and numbers
(`claude-opus-4-8` -> words `claude`, `opus`; numbers `4`, `8`). Nothing here
knows any provider or model by name: filters are written by the user, and the
pool of real models comes from `opencode models`.
"""

from __future__ import annotations

import dataclasses
import functools
import itertools
import re
import shutil
import subprocess
import typing

from omoctl.render import die

# Snapshot suffixes (`-20260814`, `-2026-08`, `-08-14`). Ranked below the
# stable alias of the same model so `claude-opus-5` beats a dated build.
_DATED: typing.Final = re.compile(r".*(\d{6,}|20\d{2}-\d{2}(-\d{2})?|\d{2}-20\d{2}|\d{2}-\d{2})$")

Pool = dict[str, tuple[str, ...]]


def _split(parts: typing.Iterable[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    words: list[str] = []
    numbers: list[str] = []
    for part in parts:
        for is_alpha, group in itertools.groupby(part, key=str.isalpha):
            token = "".join(group)
            if is_alpha:
                words.append(token)
            elif token.isdigit():
                numbers.append(token)
    return tuple(words), tuple(numbers)


@dataclasses.dataclass(frozen=True, slots=True)
class Props:
    words: tuple[str, ...]
    numbers: tuple[str, ...]

    @staticmethod
    @functools.cache
    def of(model_id: str) -> Props:
        words, numbers = _split(p.lower() for p in re.split(r"[-._/]", model_id))
        return Props(words, numbers)


@dataclasses.dataclass(frozen=True, slots=True)
class Filter:
    words_include: tuple[str, ...] = ()
    words_exclude: tuple[str, ...] = ()
    numbers_include: tuple[str, ...] = ()
    numbers_exclude: tuple[str, ...] = ()

    def matches(self, props: Props) -> bool:
        return (
            all(w in props.words for w in self.words_include)
            and not any(w in props.words for w in self.words_exclude)
            and all(n in props.numbers for n in self.numbers_include)
            and not any(n in props.numbers for n in self.numbers_exclude)
        )


def _terms(raw: object, what: str) -> tuple[str, ...]:
    if isinstance(raw, (str, int, float)):
        raw = [raw]
    if not isinstance(raw, list):
        raise ValueError(f"{what} must be a term or a list of terms, got {type(raw).__name__}")
    for term in raw:
        if not isinstance(term, (str, int, float)):
            raise ValueError(
                f"{what} contains a {type(term).__name__}; terms must be strings or numbers"
            )
    return tuple(str(term).lower() for term in raw)


def parse_filter(raw: object) -> Filter | str | None:
    """A `model:` value: exact id, keyword list, include/exclude dict, or None."""
    if raw is None:
        return None
    if isinstance(raw, str):
        if not raw.strip():
            raise ValueError("empty model spec; omit `model` to match every model")
        return raw
    if isinstance(raw, list):
        words, numbers = _split(_terms(raw, "a keyword filter"))
        if not words and not numbers:
            raise ValueError("no usable terms; omit `model` to match every model")
        return Filter(words_include=words, numbers_include=numbers)
    if isinstance(raw, dict):
        unknown = sorted(set(raw) - {"include", "exclude"})
        if unknown:
            raise ValueError(
                f"unknown filter key(s) {', '.join(map(repr, unknown))}; expected `include` and/or `exclude`"
            )
        fields: dict[str, tuple[str, ...]] = {}
        for key in ("include", "exclude"):
            if raw.get(key) is None:
                continue
            words, numbers = _split(_terms(raw[key], f"`{key}`"))
            if words:
                fields[f"words_{key}"] = words
            if numbers:
                fields[f"numbers_{key}"] = numbers
        if not fields:
            raise ValueError("no usable include/exclude terms; omit `model` to match every model")
        return Filter(**fields)
    raise ValueError(f"expected a string, list, or include/exclude dict, got {type(raw).__name__}")


def filter_matches(spec: Filter | str, model_id: str) -> bool:
    if isinstance(spec, str):
        return spec == model_id
    return spec.matches(Props.of(model_id))


def load_pool(refresh: bool = False) -> Pool:
    """`opencode models` grouped by provider."""
    opencode = shutil.which("opencode")
    if not opencode:
        die("`opencode` was not found on PATH. Install it from https://opencode.ai")

    cmd = [opencode, "models"] + (["--refresh"] if refresh else [])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.SubprocessError) as exc:
        die(f"`opencode models` failed:\n  {exc}")
    if result.returncode != 0:
        die(f"`opencode models` failed:\n  {(result.stderr or result.stdout).strip()}")

    pool: dict[str, set[str]] = {}
    for line in result.stdout.splitlines():
        line = line.strip()
        # Model lines are a single `provider/model` token; anything with
        # whitespace or a missing half is log noise.
        if not line or "/" not in line or any(c.isspace() for c in line):
            continue
        provider, _, model_id = line.partition("/")
        if provider and model_id and not model_id.startswith("/"):
            pool.setdefault(provider, set()).add(model_id)
    return {provider: tuple(sorted(ids)) for provider, ids in pool.items()}


def resolve(
    pool: Pool, provider: str, want: Filter | str | None, like: str | None
) -> tuple[str, bool]:
    """Pick the best `provider/<id>` for `want`, staying close to `like`.

    Returns the id and whether it satisfied the request as written.

    With no `want`, the current model's own words and numbers become the
    filter, so a bare provider switch means "this model, from over there" —
    which only lands where the two providers name their models alike. An id the
    provider has since retired is retried without its version, finding its
    nearest surviving sibling; a filter the user wrote by hand is never relaxed
    that way, because its terms are a constraint rather than a guess.
    """
    if provider not in pool:
        # `opencode models` only lists providers the user is signed in to. An
        # id spelled out in full needs no catalogue; anything else does.
        if isinstance(want, str):
            return f"{provider}/{want}", True
        die(
            f"Cannot pick a model for provider {provider!r}: `opencode models` does not list it.\n"
            f"  Sign in to it, or name the model outright in `set`.\n"
            f"  Listed: {', '.join(sorted(pool))}"
        )
    ids = pool[provider]

    if isinstance(want, str) and want in ids:
        return f"{provider}/{want}", True

    like_props = Props.of(like) if like else None
    if isinstance(want, Filter):
        spec = want
    elif isinstance(want, str):
        # A named id the provider no longer has: read it as its own filter, so
        # the version it asked for still steers the choice.
        words, numbers = _split(p.lower() for p in re.split(r"[-._]", want))
        spec = Filter(words_include=words, numbers_include=numbers)
    elif like_props is not None:
        spec = Filter(words_include=like_props.words, numbers_include=like_props.numbers)
    else:
        spec = Filter()

    exact = True
    candidates = [i for i in ids if spec.matches(Props.of(i))]
    if not candidates and spec.numbers_include and not isinstance(want, Filter):
        relaxed = dataclasses.replace(spec, numbers_include=())
        candidates = [i for i in ids if relaxed.matches(Props.of(i))]
        exact = not candidates
    if not candidates:
        asked = (
            want if isinstance(want, str) else " ".join(spec.words_include + spec.numbers_include)
        )
        hint = (
            ""
            if want is not None
            else f"\n  {provider!r} does not name its models like {like!r}, so `set` has to say which one."
        )
        die(
            f"No model in provider {provider!r} matches {asked}.{hint}\n  Available: {', '.join(ids)}"
        )

    target = tuple(
        int(n) for n in (spec.numbers_include or (like_props.numbers if like_props else ()))
    )
    # Resemblance to the model being replaced guides the choice only when the
    # patch named none of its own; otherwise it would outweigh what was asked for.
    like_words = set(like_props.words) if like_props and want is None else set()
    width = max(len(Props.of(i).numbers) for i in candidates)

    def rank(model_id: str) -> tuple:
        version = tuple(int(n) for n in Props.of(model_id).numbers)
        # Honour the version as far as it was named, then take the newest of
        # what is left: `include: [opus, 4]` means the latest 4.x, not the first.
        # Both halves are padded so a shorter id never wins by running out of
        # components.
        rest = tuple(-v for v in version[len(target) :])
        return (
            -len(like_words & set(Props.of(model_id).words)),
            tuple(
                abs(a - b)
                for a, b in itertools.zip_longest(version[: len(target)], target, fillvalue=0)
            ),
            bool(_DATED.match(model_id)),
            "latest" in Props.of(model_id).words,
            rest + (0,) * max(width - len(target) - len(rest), 0),
            len(model_id),
            model_id,
        )

    return f"{provider}/{min(candidates, key=rank)}", exact
