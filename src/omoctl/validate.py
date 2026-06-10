from __future__ import annotations

from omoctl.config import Config, Patch, PatchSource
from omoctl.models import ModelCache
from omoctl.omo import get_available_providers
from omoctl.output import BOLD, GREEN, RED, RESET
from omoctl.types import ModelFilter, ModelProps, _UNSET, parse_model_spec


def validate_config(config: Config, cache: ModelCache) -> list[str]:
    errors: list[str] = []

    omo_providers = set(get_available_providers())
    model_providers = set(cache.provider_to_models.keys())
    known_agents = set(cache.agent_names)
    known_categories = set(cache.category_names)

    if config.active_profile and config.get_active_profile() is None:
        errors.append(
            f"active_profile {config.active_profile!r} does not match any profile. "
            f"Defined: {', '.join(p.name for p in config.profiles)}"
        )

    if config.patches:
        for i, patch in enumerate(config.patches):
            _validate_patch(
                patch,
                f"global patch [{i}]",
                model_providers,
                known_agents,
                known_categories,
                cache,
                errors,
            )

    if config.remove_fallbacks:
        for i, source in enumerate(config.remove_fallbacks):
            _validate_remove_fallback(
                source,
                f"global remove_fallbacks [{i}]",
                model_providers,
                known_agents,
                known_categories,
                cache,
                errors,
            )

    for profile in config.profiles:
        if not profile.name:
            errors.append("Profile missing 'name' field.")
            continue

        ctx = f"profile {profile.name!r}"

        for prov in profile.providers:
            if prov not in omo_providers:
                errors.append(
                    f"{ctx}: provider {prov!r} is not a valid OMO provider. "
                    f"Available: {', '.join(sorted(omo_providers))}"
                )

        if profile.patches:
            for i, patch in enumerate(profile.patches):
                _validate_patch(
                    patch,
                    f"{ctx} patch [{i}]",
                    model_providers,
                    known_agents,
                    known_categories,
                    cache,
                    errors,
                )

        if profile.remove_fallbacks:
            for i, source in enumerate(profile.remove_fallbacks):
                _validate_remove_fallback(
                    source,
                    f"{ctx} remove_fallbacks [{i}]",
                    model_providers,
                    known_agents,
                    known_categories,
                    cache,
                    errors,
                )

    return errors


def _model_spec_matches_any(
    spec: ModelFilter | str,
    provider: str | None,
    cache: ModelCache,
) -> bool:
    """True if the spec matches at least one available model.

    Scoped to one provider's models when given, otherwise all providers.
    """
    if provider is not None:
        pools = [cache.provider_to_models.get(provider, ())]
    else:
        pools = list(cache.provider_to_models.values())
    for models in pools:
        for model_id in models:
            if isinstance(spec, str):
                if spec == model_id:
                    return True
            elif spec.matches(ModelProps.from_model_id(model_id)):
                return True
    return False


def _validate_model_spec(
    raw: object,
    provider: str | None,
    what: str,
    ctx: str,
    cache: ModelCache,
    errors: list[str],
) -> None:
    """Validate one source/target model spec: parseable, and matching at
    least one available model (within its provider when one is given)."""
    try:
        spec = parse_model_spec(raw)
    except ValueError as e:
        errors.append(f"{ctx}: {what} model: {e}")
        return

    if spec is None or not cache.provider_to_models:
        return

    if not _model_spec_matches_any(spec, provider, cache):
        scope = f"provider {provider!r}" if provider else "any provider"
        if isinstance(spec, str):
            errors.append(f"{ctx}: {what} model {spec!r} not found in {scope}.")
        else:
            errors.append(f"{ctx}: {what} model filter matches no models in {scope}.")


def _validate_patch(
    patch: Patch,
    ctx: str,
    model_providers: set[str],
    known_agents: set[str],
    known_categories: set[str],
    cache: ModelCache,
    errors: list[str],
) -> None:
    src = patch.source
    tgt = patch.target

    if src.provider and src.provider not in model_providers:
        errors.append(f"{ctx}: source provider {src.provider!r} not found.")

    if src.agent and known_agents and src.agent not in known_agents:
        errors.append(
            f"{ctx}: source agent {src.agent!r} not found. "
            f"Available: {', '.join(sorted(known_agents))}"
        )

    if src.category and known_categories and src.category not in known_categories:
        errors.append(
            f"{ctx}: source category {src.category!r} not found. "
            f"Available: {', '.join(sorted(known_categories))}"
        )

    if src.model is not None:
        _validate_model_spec(src.model, src.provider, "source", ctx, cache, errors)

    if not src.provider and not src.agent and not src.category:
        errors.append(
            f"{ctx}: source must specify at least provider, agent, or category."
        )

    if not tgt.provider and not tgt.model and tgt.variant is _UNSET:
        errors.append(
            f"{ctx}: target must specify at least provider, model, or variant."
        )

    if tgt.provider and tgt.provider not in model_providers:
        errors.append(f"{ctx}: target provider {tgt.provider!r} not found.")

    if tgt.model is not None:
        _validate_model_spec(tgt.model, tgt.provider, "target", ctx, cache, errors)


def _validate_remove_fallback(
    source: PatchSource,
    ctx: str,
    model_providers: set[str],
    known_agents: set[str],
    known_categories: set[str],
    cache: ModelCache,
    errors: list[str],
) -> None:
    if not source.provider and not source.agent and not source.category:
        errors.append(
            f"{ctx}: source must specify at least provider, agent, or category."
        )

    if source.provider and source.provider not in model_providers:
        errors.append(f"{ctx}: source provider {source.provider!r} not found.")

    if source.agent and known_agents and source.agent not in known_agents:
        errors.append(
            f"{ctx}: source agent {source.agent!r} not found. "
            f"Available: {', '.join(sorted(known_agents))}"
        )

    if source.category and known_categories and source.category not in known_categories:
        errors.append(
            f"{ctx}: source category {source.category!r} not found. "
            f"Available: {', '.join(sorted(known_categories))}"
        )

    if source.model is not None:
        _validate_model_spec(
            source.model, source.provider, "source", ctx, cache, errors
        )


def print_validation_result(errors: list[str]) -> bool:
    if not errors:
        print(f"{GREEN}Config is valid.{RESET}")
        return True

    print(f"{RED}{BOLD}Validation failed with {len(errors)} error(s):{RESET}\n")
    for err in errors:
        print(f"  {RED}• {err}{RESET}")
    return False
