from __future__ import annotations

import pytest

from omoctl.config import Config, Patch, PatchSource, PatchTarget, Profile
from omoctl.models import ModelCache
from omoctl.patching import apply_patches_to_config, patch_model
from omoctl.types import _UNSET

CACHE = ModelCache(
    provider_to_models={
        "anthropic": ("claude-opus-4-7", "claude-haiku-4-5", "claude-sonnet-4-6"),
        "openai": ("gpt-5.4", "gpt-5.4-mini"),
    }
)


def make_patch(source: dict, target: dict) -> Patch:
    return Patch(source=PatchSource(**source), target=PatchTarget(**target))


class TestAgentScopedPatches:
    def test_agent_match_rewrites(self):
        p = make_patch(
            {"agent": "sisyphus"}, {"provider": "openai", "model": "gpt-5.4"}
        )
        model, _ = patch_model(
            CACHE, "agents", "sisyphus", "anthropic/claude-opus-4-7", [p]
        )
        assert model == "openai/gpt-5.4"

    def test_other_agent_untouched(self):
        p = make_patch(
            {"agent": "sisyphus"}, {"provider": "openai", "model": "gpt-5.4"}
        )
        model, variant = patch_model(
            CACHE, "agents", "oracle", "anthropic/claude-opus-4-7", [p]
        )
        assert model == "anthropic/claude-opus-4-7"
        assert variant is _UNSET

    def test_model_filter_without_provider_is_honored(self):
        """Regression: `{agent: X, model: Y}` used to ignore the model filter."""
        p = make_patch(
            {"agent": "sisyphus", "model": "claude-opus-4-7"},
            {"model": "claude-sonnet-4-6"},
        )
        model, _ = patch_model(
            CACHE, "agents", "sisyphus", "anthropic/claude-haiku-4-5", [p]
        )
        assert model == "anthropic/claude-haiku-4-5", "haiku must not match opus filter"

        model, _ = patch_model(
            CACHE, "agents", "sisyphus", "anthropic/claude-opus-4-7", [p]
        )
        assert model == "anthropic/claude-sonnet-4-6"

    def test_keyword_filter_without_provider(self):
        p = make_patch(
            {"agent": "sisyphus", "model": ["opus"]},
            {"model": "claude-sonnet-4-6"},
        )
        model, _ = patch_model(
            CACHE, "agents", "sisyphus", "anthropic/claude-opus-4-7", [p]
        )
        assert model == "anthropic/claude-sonnet-4-6"

    def test_provider_constraint_respected(self):
        p = make_patch(
            {"agent": "sisyphus", "provider": "openai"},
            {"model": "gpt-5.4-mini"},
        )
        model, _ = patch_model(
            CACHE, "agents", "sisyphus", "anthropic/claude-opus-4-7", [p]
        )
        assert model == "anthropic/claude-opus-4-7"

    def test_exact_model_beats_generic_regardless_of_order(self):
        generic = make_patch({"agent": "sisyphus"}, {"model": "gpt-5.4"})
        exact = make_patch(
            {"agent": "sisyphus", "model": "claude-opus-4-7"},
            {"model": "claude-sonnet-4-6"},
        )
        for patches in ([generic, exact], [exact, generic]):
            model, _ = patch_model(
                CACHE, "agents", "sisyphus", "anthropic/claude-opus-4-7", patches
            )
            assert model == "anthropic/claude-sonnet-4-6"

    def test_filter_beats_no_constraint(self):
        generic = make_patch({"agent": "sisyphus"}, {"model": "gpt-5.4"})
        filtered = make_patch(
            {"agent": "sisyphus", "model": ["opus"]},
            {"model": "claude-sonnet-4-6"},
        )
        model, _ = patch_model(
            CACHE,
            "agents",
            "sisyphus",
            "anthropic/claude-opus-4-7",
            [generic, filtered],
        )
        assert model == "anthropic/claude-sonnet-4-6"

    def test_tie_resolved_by_list_order(self):
        first = make_patch({"agent": "sisyphus"}, {"model": "claude-sonnet-4-6"})
        second = make_patch({"agent": "sisyphus"}, {"model": "gpt-5.4"})
        model, _ = patch_model(
            CACHE, "agents", "sisyphus", "anthropic/claude-opus-4-7", [first, second]
        )
        assert model == "anthropic/claude-sonnet-4-6"

    def test_category_scoped(self):
        p = make_patch({"category": "deep"}, {"model": "gpt-5.4-mini"})
        model, _ = patch_model(CACHE, "categories", "deep", "openai/gpt-5.4", [p])
        assert model == "openai/gpt-5.4-mini"


class TestProviderModelPatches:
    def test_provider_only(self):
        p = make_patch(
            {"provider": "openai"},
            {"provider": "anthropic", "model": "claude-sonnet-4-6"},
        )
        model, _ = patch_model(CACHE, "agents", "a", "openai/gpt-5.4", [p])
        assert model == "anthropic/claude-sonnet-4-6"

    def test_exact_beats_filter(self):
        filtered = make_patch(
            {"provider": "openai", "model": ["gpt"]}, {"model": "gpt-5.4-mini"}
        )
        exact = make_patch(
            {"provider": "openai", "model": "gpt-5.4"},
            {"provider": "anthropic", "model": "claude-opus-4-7"},
        )
        model, _ = patch_model(
            CACHE, "agents", "a", "openai/gpt-5.4", [filtered, exact]
        )
        assert model == "anthropic/claude-opus-4-7"

    def test_no_provider_in_model_left_alone(self):
        p = make_patch({"provider": "openai"}, {"model": "gpt-5.4"})
        model, variant = patch_model(CACHE, "agents", "a", "bare-model", [p])
        assert model == "bare-model"
        assert variant is _UNSET

    def test_variant_only_target(self):
        p = make_patch({"provider": "anthropic"}, {"variant": "max"})
        model, variant = patch_model(
            CACHE, "agents", "a", "anthropic/claude-opus-4-7", [p]
        )
        assert model == "anthropic/claude-opus-4-7"
        assert variant == "max"


OMO_CONFIG = {
    "$schema": "schema",
    "agents": {
        "sisyphus": {
            "model": "anthropic/claude-opus-4-7",
            "variant": "max",
            "fallback_models": [
                {"model": "openai/gpt-5.4"},
                {"model": "anthropic/claude-haiku-4-5", "variant": "low"},
            ],
        },
    },
    "categories": {
        "deep": {"model": "openai/gpt-5.4"},
    },
}


class TestApplyPatchesToConfig:
    def test_no_patches_passthrough(self):
        profile = Profile(name="Test", providers=["claude"])
        patched, keys = apply_patches_to_config(CACHE, profile, OMO_CONFIG)
        assert patched["agents"]["sisyphus"]["model"] == "anthropic/claude-opus-4-7"
        assert ("agents", "sisyphus") in keys
        assert ("categories", "deep") in keys

    def test_variant_null_removes_variant(self):
        profile = Profile(
            name="Test",
            providers=["claude"],
            patches=[
                make_patch({"agent": "sisyphus", "model": ["opus"]}, {"variant": None})
            ],
        )
        patched, _ = apply_patches_to_config(CACHE, profile, OMO_CONFIG)
        assert "variant" not in patched["agents"]["sisyphus"]
        assert patched["agents"]["sisyphus"]["model"] == "anthropic/claude-opus-4-7"

    def test_fallbacks_are_patched_too(self):
        profile = Profile(
            name="Test",
            providers=["claude"],
            patches=[
                make_patch(
                    {"provider": "openai"},
                    {"provider": "anthropic", "model": "claude-sonnet-4-6"},
                )
            ],
        )
        patched, _ = apply_patches_to_config(CACHE, profile, OMO_CONFIG)
        fb_models = [
            fb["model"] for fb in patched["agents"]["sisyphus"]["fallback_models"]
        ]
        assert "anthropic/claude-sonnet-4-6" in fb_models
        assert patched["categories"]["deep"]["model"] == "anthropic/claude-sonnet-4-6"

    def test_remove_fallbacks_by_provider_and_filter(self):
        profile = Profile(
            name="Test",
            providers=["claude"],
            remove_fallbacks=[PatchSource(provider="anthropic", model=["haiku"])],
        )
        patched, _ = apply_patches_to_config(CACHE, profile, OMO_CONFIG)
        fb_models = [
            fb["model"] for fb in patched["agents"]["sisyphus"]["fallback_models"]
        ]
        assert fb_models == ["openai/gpt-5.4"]

    def test_remove_fallbacks_agent_scoped(self):
        profile = Profile(
            name="Test",
            providers=["claude"],
            remove_fallbacks=[PatchSource(agent="other", provider="openai")],
        )
        patched, _ = apply_patches_to_config(CACHE, profile, OMO_CONFIG)
        assert len(patched["agents"]["sisyphus"]["fallback_models"]) == 2

    def test_remove_fallbacks_matches_original_model_not_post_patch(self):
        profile = Profile(
            name="Test",
            providers=["claude"],
            patches=[
                make_patch(
                    {"provider": "openai"},
                    {"provider": "anthropic", "model": "claude-sonnet-4-6"},
                )
            ],
            remove_fallbacks=[PatchSource(provider="openai")],
        )
        patched, _ = apply_patches_to_config(CACHE, profile, OMO_CONFIG)
        fb_models = [
            fb["model"] for fb in patched["agents"]["sisyphus"]["fallback_models"]
        ]
        assert fb_models == ["anthropic/claude-haiku-4-5"]

    def test_global_and_profile_merge(self):
        profile = Profile(
            name="Test",
            providers=["claude"],
            overrides={"agents": {"sisyphus": {"note": "profile"}}},
        )
        config = Config(
            overrides={"disabled_hooks": ["x"]},
            patches=[
                make_patch(
                    {"provider": "openai"},
                    {"provider": "anthropic", "model": "claude-sonnet-4-6"},
                )
            ],
            profiles=[profile],
        )
        patched, _ = apply_patches_to_config(CACHE, profile, OMO_CONFIG, config)
        assert patched["categories"]["deep"]["model"] == "anthropic/claude-sonnet-4-6"
        assert patched["disabled_hooks"] == ["x"]
        assert patched["agents"]["sisyphus"]["note"] == "profile"

    def test_missing_omo_fields_die(self):
        profile = Profile(name="Test", providers=["claude"])
        with pytest.raises(SystemExit):
            apply_patches_to_config(CACHE, profile, {"agents": {}})
