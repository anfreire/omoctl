from __future__ import annotations
import dataclasses
import itertools
import re
import shutil
import subprocess
import typing
from omoctl.output import die
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


def _find_opencode() -> str:
    opencode = shutil.which("opencode")
    if opencode:
        return opencode
    die("'opencode' binary not found in PATH. Install it from https://opencode.ai")


def load_models(refresh: bool = False) -> dict[str, tuple[str, ...]]:
    """Run `opencode models [--refresh]` and parse `<provider>/<model>` lines."""
    opencode = _find_opencode()

    cmd = [opencode, "models"]
    if refresh:
        cmd.append("--refresh")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        die(f"Failed to query opencode models:\n  {e}")

    if result.returncode != 0:
        die(
            "Failed to query opencode models:\n"
            f"  {(result.stderr or result.stdout or '').strip()}"
        )

    provider_to_models: dict[str, set[str]] = {}
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line or "/" not in line:
            continue
        provider, _, model = line.partition("/")
        provider_to_models.setdefault(provider, set()).add(model)

    return {p: tuple(sorted(models)) for p, models in provider_to_models.items()}


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
