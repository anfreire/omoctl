from __future__ import annotations

import dataclasses
import itertools
import re
import typing


def split_words_numbers(
    parts: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    words: list[str] = []
    numbers: list[str] = []
    for part in parts:
        if not part:
            continue
        for is_alpha, group in itertools.groupby(part, key=str.isalpha):
            token = "".join(group)
            if is_alpha:
                words.append(token)
            elif token.isdigit():
                numbers.append(token)
    return tuple(words), tuple(numbers)


@dataclasses.dataclass(frozen=True, slots=True)
class ModelProps:
    provider_prefix: str | None
    words: tuple[str, ...]
    numbers: tuple[str, ...]

    @staticmethod
    def from_model_id(model_id: str) -> ModelProps:
        provider_prefix = None
        if "/" in model_id:
            provider_prefix, model_id = model_id.split("/", 1)
        parts = tuple(part.lower() for part in re.split(r"[-._]", model_id))
        words, numbers = split_words_numbers(parts)
        return ModelProps(
            provider_prefix=provider_prefix,
            words=words,
            numbers=numbers,
        )


_FILTER_KEYS: typing.Final = ("include", "exclude")


def _coerce_terms(raw: typing.Any, what: str) -> tuple[str, ...]:
    if isinstance(raw, (str, int, float)):
        raw = [raw]
    if not isinstance(raw, list):
        raise ValueError(
            f"Malformed model filter: {what} must be a term or a list of terms, "
            f"got {type(raw).__name__}."
        )
    terms: list[str] = []
    for term in raw:
        if not isinstance(term, (str, int, float)):
            raise ValueError(
                f"Malformed model filter: {what} contains a {type(term).__name__}; "
                f"terms must be strings or numbers."
            )
        terms.append(str(term).lower())
    return tuple(terms)


@dataclasses.dataclass(frozen=True, slots=True)
class ModelFilter:
    words_include: tuple[str, ...] = ()
    words_exclude: tuple[str, ...] = ()
    numbers_include: tuple[str, ...] = ()
    numbers_exclude: tuple[str, ...] = ()

    def matches(self, props: ModelProps) -> bool:
        return (
            all(w in props.words for w in self.words_include)
            and not any(w in props.words for w in self.words_exclude)
            and all(n in props.numbers for n in self.numbers_include)
            and not any(n in props.numbers for n in self.numbers_exclude)
        )

    @property
    def specificity(self) -> int:
        return (
            len(self.words_include)
            + len(self.words_exclude)
            + len(self.numbers_include)
            + len(self.numbers_exclude)
        )

    @staticmethod
    def from_raw(raw: dict | list) -> ModelFilter:
        if isinstance(raw, list):
            if not raw:
                raise ValueError(
                    "Malformed model filter: empty list matches nothing. "
                    "Omit 'model' to match all models."
                )
            words_include, numbers_include = split_words_numbers(
                _coerce_terms(raw, "a keyword filter")
            )
            if not words_include and not numbers_include:
                raise ValueError(
                    "Malformed model filter: no usable terms. "
                    "Omit 'model' to match all models."
                )
            return ModelFilter(
                words_include=words_include,
                numbers_include=numbers_include,
            )

        unknown = [key for key in raw if key not in _FILTER_KEYS]
        if unknown:
            raise ValueError(
                f"Malformed model filter: unknown key(s) {', '.join(map(repr, sorted(unknown)))}. "
                f"Expected 'include' and/or 'exclude'."
            )

        kwargs: dict[str, tuple[str, ...]] = {}
        for key in _FILTER_KEYS:
            sub_raw = raw.get(key)
            if sub_raw is None:
                continue
            words, numbers = split_words_numbers(_coerce_terms(sub_raw, f"'{key}'"))
            if words:
                kwargs[f"words_{key}"] = words
            if numbers:
                kwargs[f"numbers_{key}"] = numbers

        if not kwargs:
            raise ValueError(
                "Malformed model filter: no usable 'include'/'exclude' terms. "
                "Omit 'model' to match all models."
            )

        return ModelFilter(**kwargs)


_UNSET: typing.Final = object()


def parse_model_spec(raw: typing.Any) -> ModelFilter | str | None:
    """Parse a config 'model' value: exact string, keyword list, include/exclude
    dict, or None (match all). Raises ValueError on malformed input."""
    if raw is None:
        return None
    if isinstance(raw, str):
        if not raw.strip():
            raise ValueError(
                "Malformed model spec: empty string. Omit 'model' to match all models."
            )
        return raw
    if isinstance(raw, (list, dict)):
        return ModelFilter.from_raw(raw)
    raise ValueError(
        f"Malformed model spec: expected a string, list, or include/exclude dict, "
        f"got {type(raw).__name__}."
    )
