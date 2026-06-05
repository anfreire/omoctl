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
    def from_model_id(model_id: str) -> ModelProps | None:
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


@dataclasses.dataclass(frozen=True, slots=True)
class ModelFilter:
    words_include: tuple[str, ...] = ()
    words_exclude: tuple[str, ...] = ()
    numbers_include: tuple[str, ...] = ()
    numbers_exclude: tuple[str, ...] = ()

    @staticmethod
    def from_raw(
        raw: dict[str, list[str]] | list[str] | None,
    ) -> ModelFilter | None:
        if not raw:
            return None

        if isinstance(raw, list):
            words_include, numbers_include = split_words_numbers(
                tuple(str(w).lower() for w in raw)
            )
            return ModelFilter(
                words_include=words_include,
                numbers_include=numbers_include,
            )

        kwargs: dict[str, tuple[str, ...]] = {}
        for key in ("include", "exclude"):
            sub_raw = raw.get(key) or []
            if not isinstance(sub_raw, list):
                raise ValueError(
                    f"Malformed model filter: '{key}' must be a list of strings."
                )
            if not sub_raw:
                continue
            words, numbers = split_words_numbers(tuple(str(w).lower() for w in sub_raw))
            kwargs[f"words_{key}"] = words
            kwargs[f"numbers_{key}"] = numbers

        if not any(kwargs.values()):
            return None

        return ModelFilter(**kwargs)


_UNSET: typing.Final = object()


def parse_model_spec(raw: typing.Any) -> ModelFilter | str | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw
    return ModelFilter.from_raw(raw)
