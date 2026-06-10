from __future__ import annotations

from collections.abc import Sequence

from omoctl.config import Config, Patch, PatchSource, Profile, merge_dicts
from omoctl.models import ModelCache, find_best_matching_model
from omoctl.output import die
from omoctl.types import ModelFilter, ModelProps, _UNSET, parse_model_spec


def _split_provider_model(model: str) -> tuple[str | None, str]:
    if "/" in model:
        provider, model_id = model.split("/", 1)
        return provider, model_id
    return None, model


def _match_agent_or_category(patch: Patch, section: str, name: str) -> bool:
    src = patch.source
    if section == "agents" and src.agent:
        return src.agent == name
    if section == "categories" and src.category:
        return src.category == name
    return False


def _score_model_match(spec: ModelFilter | str | None, model_id: str) -> tuple | None:
    """Score how well a parsed model spec matches a model id.

    Returns None on no match. Scores order as: exact string > filter
    (by specificity, then presence of numbers, then version) > no constraint.
    """
    if isinstance(spec, str):
        return (3,) if spec == model_id else None
    if spec is None:
        return (0, 0, 0, ())
    props = ModelProps.from_model_id(model_id)
    if not spec.matches(props):
        return None
    version_key = (
        tuple(int(n) for n in spec.numbers_include) if spec.numbers_include else ()
    )
    return (1, spec.specificity, 1 if spec.numbers_include else 0, version_key)


def _score_scoped_patch(
    patch: Patch, provider: str | None, model_id: str
) -> tuple | None:
    """Score an agent/category-scoped patch against the current model.

    The source's provider and model constraints must both hold; among
    matches, exact models beat filters beat no constraint, and a provider
    constraint breaks remaining ties.
    """
    src = patch.source
    if src.provider:
        if provider is None or src.provider != provider:
            return None
    model_score = _score_model_match(parse_model_spec(src.model), model_id)
    if model_score is None:
        return None
    return (model_score, 1 if src.provider else 0)


def _match_provider_model(patch: Patch, provider: str, model_id: str) -> tuple | None:
    src = patch.source
    if src.provider is None or src.provider != provider:
        return None
    return _score_model_match(parse_model_spec(src.model), model_id)


def _resolve_target(
    cache: ModelCache,
    patch: Patch,
    original_provider: str | None,
    original_model: str | None,
) -> tuple[str, object]:
    tgt = patch.target
    target_provider = tgt.provider or original_provider
    if not target_provider:
        die("Patch target must specify a provider (or source must have one).")

    target_hint = parse_model_spec(tgt.model)

    matched_model = find_best_matching_model(
        cache.provider_to_models,
        original_provider,
        original_model,
        target_provider,
        target_hint,
    )
    return matched_model, tgt.variant


def patch_model(
    cache: ModelCache,
    section: str,
    name: str,
    model: str,
    patches: list[Patch],
) -> tuple[str, object]:
    provider, model_id = _split_provider_model(model)

    # 1. Agent/category-scoped patches (highest priority), scored so that
    #    more specific sources win; list order (profile first) breaks ties.
    best: tuple[tuple, Patch] | None = None
    for patch in patches:
        if not _match_agent_or_category(patch, section, name):
            continue
        score = _score_scoped_patch(patch, provider, model_id)
        if score is None:
            continue
        if best is None or score > best[0]:
            best = (score, patch)
    if best is not None:
        return _resolve_target(cache, best[1], provider, model_id)

    # 2. Provider/model patches, scored the same way.
    if provider is None:
        return model, _UNSET

    best = None
    for patch in patches:
        if patch.source.agent or patch.source.category:
            continue
        score = _match_provider_model(patch, provider, model_id)
        if score is None:
            continue
        if best is None or score > best[0]:
            best = (score, patch)

    if best is None:
        return model, _UNSET

    return _resolve_target(cache, best[1], provider, model_id)


def _fallback_matches_remove(
    fb: dict,
    section: str,
    name: str,
    remove_fallbacks: Sequence[PatchSource],
) -> bool:
    if "model" not in fb:
        return False
    fb_model = fb["model"]
    if "/" not in fb_model:
        return False
    fb_provider, _, fb_model_id = fb_model.partition("/")

    for source in remove_fallbacks:
        if source.agent is not None and not (
            section == "agents" and source.agent == name
        ):
            continue
        if source.category is not None and not (
            section == "categories" and source.category == name
        ):
            continue

        if source.provider is not None and source.provider != fb_provider:
            continue

        spec = parse_model_spec(source.model)

        if isinstance(spec, str):
            if spec == fb_model_id:
                return True
            continue

        if spec is None:
            return True

        if spec.matches(ModelProps.from_model_id(fb_model_id)):
            return True

    return False


def _patch_fallbacks(
    cache: ModelCache,
    section: str,
    name: str,
    fallbacks: list[dict],
    patches: list[Patch],
    remove_fallbacks: Sequence[PatchSource] = (),
) -> list[dict]:
    result = []
    for fb in fallbacks:
        if remove_fallbacks and _fallback_matches_remove(
            fb, section, name, remove_fallbacks
        ):
            continue
        if "model" not in fb:
            result.append(fb)
            continue
        patched_fb = fb.copy()
        patched_model, patched_variant = patch_model(
            cache,
            section,
            name,
            fb["model"],
            patches,
        )
        patched_fb["model"] = patched_model
        if patched_variant is not _UNSET:
            if patched_variant is None:
                patched_fb.pop("variant", None)
            else:
                patched_fb["variant"] = patched_variant
        result.append(patched_fb)
    return result


def apply_patches_to_config(
    cache: ModelCache,
    profile: Profile,
    omo_config: dict,
    config: Config | None = None,
) -> tuple[dict, list[tuple[str, str]]]:
    for field in ("$schema", "agents", "categories"):
        if field not in omo_config:
            die(f"OMO config missing '{field}' field.")

    patches = (
        config.get_effective_patches(profile) if config else (profile.patches or [])
    )
    remove_fallbacks = (
        config.get_effective_remove_fallbacks(profile)
        if config
        else (profile.remove_fallbacks or [])
    )
    overrides = config.get_effective_overrides(profile) if config else profile.overrides

    patched_config: dict = {
        "$schema": omo_config["$schema"],
        "agents": {},
        "categories": {},
    }

    keys: list[tuple[str, str]] = [
        (section, name)
        for section in ("agents", "categories")
        for name in omo_config[section]
    ]

    for section, name in keys:
        entry = omo_config[section].get(name)
        if entry is None:
            die(f"{section} {name!r} missing from OMO config.")
        if "model" not in entry:
            die(f"{section} {name!r} has no 'model' field.")

        patched_entry = entry.copy()
        patched_model, patched_variant = patch_model(
            cache,
            section,
            name,
            entry["model"],
            patches,
        )
        patched_entry["model"] = patched_model
        if patched_variant is not _UNSET:
            if patched_variant is None:
                patched_entry.pop("variant", None)
            else:
                patched_entry["variant"] = patched_variant

        if "fallback_models" in patched_entry:
            patched_entry["fallback_models"] = _patch_fallbacks(
                cache,
                section,
                name,
                patched_entry["fallback_models"],
                patches,
                remove_fallbacks,
            )

        patched_config[section][name] = patched_entry

    if overrides:
        patched_config = merge_dicts(patched_config, overrides)

    return patched_config, keys
