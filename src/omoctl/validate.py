from __future__ import annotations

from omoctl.config import Config, Patch
from omoctl.models import ModelCache
from omoctl.omo import get_available_providers
from omoctl.output import BOLD, GREEN, RED, RESET
from omoctl.types import _UNSET


def validate_config(config: Config, cache: ModelCache) -> list[str]:
    errors: list[str] = []

    omo_providers = set(get_available_providers())
    model_providers = set(cache.provider_to_models.keys())
    known_agents = set(cache.agent_names)
    known_categories = set(cache.category_names)

    if config.patches:
        for i, patch in enumerate(config.patches):
            _validate_patch(
                patch, f"global patch [{i}]",
                model_providers, known_agents, known_categories, cache, errors,
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
                    patch, f"{ctx} patch [{i}]",
                    model_providers, known_agents, known_categories, cache, errors,
                )

    return errors


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

    if src.provider and isinstance(src.model, str):
        models = cache.provider_to_models.get(src.provider, ())
        if src.model not in models:
            errors.append(f"{ctx}: source model {src.model!r} not in provider {src.provider!r}.")

    if not src.provider and not src.agent and not src.category:
        errors.append(f"{ctx}: source must specify at least provider, agent, or category.")

    if not tgt.provider and not tgt.model and tgt.variant is _UNSET:
        errors.append(
            f"{ctx}: target must specify at least provider, model, or variant."
        )

    if tgt.provider and tgt.provider not in model_providers:
        errors.append(f"{ctx}: target provider {tgt.provider!r} not found.")

    if tgt.provider and isinstance(tgt.model, str):
        models = cache.provider_to_models.get(tgt.provider, ())
        if tgt.model not in models:
            errors.append(f"{ctx}: target model {tgt.model!r} not in provider {tgt.provider!r}.")


def print_validation_result(errors: list[str]) -> bool:
    if not errors:
        print(f"{GREEN}Config is valid.{RESET}")
        return True

    print(f"{RED}{BOLD}Validation failed with {len(errors)} error(s):{RESET}\n")
    for err in errors:
        print(f"  {RED}• {err}{RESET}")
    return False
