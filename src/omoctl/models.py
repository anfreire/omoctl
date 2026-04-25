from __future__ import annotations

import dataclasses
import itertools
import json
import re
import typing

from omoctl.output import die
from omoctl.paths import CACHED_MODELS_PATH, CUSTOM_MODELS_PATH
from omoctl.types import ModelFilter, ModelProps

DATED_MODEL_PATTERN: typing.Final[re.Pattern] = re.compile(
    r".*("
    r"\d{6,}"
    r"|20\d{2}[-]\d{2}([-]\d{2})?"
    r"|\d{2}[-]20\d{2}"
    r"|\d{2}[-]\d{2}"
    r")$"
)


@dataclasses.dataclass(frozen=True, slots=True)
class ModelCache:
    provider_to_models: dict[str, tuple[str, ...]]
    agent_names: tuple[str, ...] = ()
    category_names: tuple[str, ...] = ()


def load_model_cache() -> ModelCache:
    if not CACHED_MODELS_PATH.exists():
        die(
            f"Model cache not found at {CACHED_MODELS_PATH}.\n"
            f"  Run 'opencode' once to populate it."
        )

    try:
        with CACHED_MODELS_PATH.open() as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        die(f"Model cache at {CACHED_MODELS_PATH} is malformed:\n  {e}")

    custom_data: dict = {}
    if CUSTOM_MODELS_PATH.exists():
        try:
            with CUSTOM_MODELS_PATH.open() as f:
                custom_data = json.load(f).get("provider", {})
        except json.JSONDecodeError as e:
            die(f"Custom models at {CUSTOM_MODELS_PATH} is malformed:\n  {e}")

    providers = set(data.keys()) | set(custom_data.keys())

    provider_to_models: dict[str, tuple[str, ...]] = {}
    for provider in providers:
        models: set[str] = set()
        for source_data in (data, custom_data):
            if provider in source_data and "models" in source_data[provider]:
                provider_models = source_data[provider]["models"]
                if isinstance(provider_models, dict):
                    models.update(provider_models.keys())

        provider_to_models[provider] = tuple(
            sorted(
                models,
                key=lambda model_id: (
                    bool(DATED_MODEL_PATTERN.match(model_id)),
                    not model_id.endswith("latest"),
                    len(model_id),
                ),
            )
        )

    return ModelCache(
        provider_to_models=provider_to_models,
    )


def enrich_cache_with_omo(cache: ModelCache, omo_config: dict) -> ModelCache:
    return ModelCache(
        provider_to_models=cache.provider_to_models,
        agent_names=tuple(sorted(omo_config.get("agents", {}).keys())),
        category_names=tuple(sorted(omo_config.get("categories", {}).keys())),
    )


def _numbers_key(numbers: tuple[str, ...]) -> tuple[int, ...]:
    return tuple(int(n) for n in numbers) if numbers else ()


def find_best_matching_model(
    provider_to_models: dict[str, tuple[str, ...]],
    original_provider: str | None,
    original_model: str | None,
    target_provider: str,
    target_hint: ModelFilter | str | None,
) -> str:
    if target_provider not in provider_to_models:
        die(f"Target provider {target_provider!r} not found in cached models.")

    if isinstance(target_hint, str):
        if target_hint in provider_to_models[target_provider]:
            return f"{target_provider}/{target_hint}"
        die(
            f"Explicit model {target_hint!r} not found in provider {target_provider!r}."
        )

    original_props = (
        ModelProps.from_model_id(original_model) if original_model else None
    )

    if target_hint is not None:
        include_words = target_hint.words_include
        exclude_words = target_hint.words_exclude
        include_numbers = target_hint.numbers_include
        exclude_numbers = target_hint.numbers_exclude
    else:
        include_words = ()
        exclude_words = ()
        include_numbers = ()
        exclude_numbers = ()

    if not target_hint and original_props:
        include_words = original_props.words
        include_numbers = original_props.numbers

    version_specified = bool(include_numbers) or bool(
        original_props and original_props.numbers
    )

    def _matches(props: ModelProps) -> bool:
        return (
            all(w in props.words for w in include_words)
            and not any(w in props.words for w in exclude_words)
            and all(n in props.numbers for n in include_numbers)
            and not any(n in props.numbers for n in exclude_numbers)
        )

    candidates: list[tuple[str, ModelProps]] = []
    for model_id in provider_to_models[target_provider]:
        props = ModelProps.from_model_id(model_id)
        if props is not None and _matches(props):
            candidates.append((model_id, props))

    if not candidates and version_specified:
        for model_id in provider_to_models[target_provider]:
            props = ModelProps.from_model_id(model_id)
            if props is None:
                continue
            if all(w in props.words for w in include_words) and not any(
                w in props.words for w in exclude_words
            ):
                candidates.append((model_id, props))

    if not candidates:
        die(
            f"No matching model for {original_model!r} from "
            f"{original_provider!r} in provider {target_provider!r}."
        )

    original_words = set(original_props.words) if original_props else set()
    original_numbers = original_props.numbers if original_props else ()
    target_version = _numbers_key(include_numbers or original_numbers)

    def _sort_key(entry: tuple[str, ModelProps]) -> tuple:
        model_id, props = entry
        version = _numbers_key(props.numbers)
        word_overlap = -len(original_words & set(props.words)) if original_words else 0

        return (
            (props.provider_prefix or "") != (original_provider or ""),
            word_overlap,
            bool(DATED_MODEL_PATTERN.match(model_id)),
            "latest" in props.words,
            tuple(
                abs(a - b)
                for a, b in itertools.zip_longest(version, target_version, fillvalue=0)
            )
            if version_specified
            else tuple(-v for v in version),
            len(model_id),
        )

    candidates.sort(key=_sort_key)
    return f"{target_provider}/{candidates[0][0]}"
