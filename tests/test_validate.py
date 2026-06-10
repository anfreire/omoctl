from __future__ import annotations

import pytest

import omoctl.validate as validate_mod
from omoctl.config import Config, Patch, PatchSource, PatchTarget, Profile
from omoctl.models import ModelCache
from omoctl.validate import validate_config

CACHE = ModelCache(
    provider_to_models={
        "anthropic": ("claude-opus-4-7", "claude-haiku-4-5"),
        "openai": ("gpt-5.4",),
    },
    agent_names=("sisyphus", "oracle"),
    category_names=("deep",),
)


@pytest.fixture(autouse=True)
def fake_omo_providers(monkeypatch):
    monkeypatch.setattr(
        validate_mod, "get_available_providers", lambda: ("claude", "openai", "gemini")
    )


def make_config(**kwargs) -> Config:
    kwargs.setdefault("profiles", [Profile(name="Test", providers=["claude"])])
    return Config(**kwargs)


class TestValidateConfig:
    def test_valid_config_no_errors(self):
        config = make_config(
            active_profile="Test",
            patches=[
                Patch(
                    source=PatchSource(provider="anthropic", model=["opus"]),
                    target=PatchTarget(provider="openai", model="gpt-5.4"),
                )
            ],
            remove_fallbacks=[PatchSource(provider="openai")],
        )
        assert validate_config(config, CACHE) == []

    def test_dangling_active_profile(self):
        config = make_config(active_profile="Ghost")
        errors = validate_config(config, CACHE)
        assert any("active_profile 'Ghost'" in e for e in errors)

    def test_invalid_omo_provider(self):
        config = make_config(profiles=[Profile(name="Test", providers=["nope"])])
        errors = validate_config(config, CACHE)
        assert any("not a valid OMO provider" in e for e in errors)

    def test_unknown_source_provider(self):
        config = make_config(
            patches=[
                Patch(
                    source=PatchSource(provider="nope"),
                    target=PatchTarget(model="gpt-5.4"),
                )
            ]
        )
        errors = validate_config(config, CACHE)
        assert any("source provider 'nope' not found" in e for e in errors)

    def test_unknown_agent_and_category(self):
        config = make_config(
            patches=[
                Patch(
                    source=PatchSource(agent="ghost"),
                    target=PatchTarget(model="gpt-5.4"),
                ),
                Patch(
                    source=PatchSource(category="ghost"),
                    target=PatchTarget(model="gpt-5.4"),
                ),
            ]
        )
        errors = validate_config(config, CACHE)
        assert any("source agent 'ghost' not found" in e for e in errors)
        assert any("source category 'ghost' not found" in e for e in errors)

    def test_source_without_scope(self):
        config = make_config(
            patches=[Patch(source=PatchSource(), target=PatchTarget(model="gpt-5.4"))]
        )
        errors = validate_config(config, CACHE)
        assert any("source must specify at least" in e for e in errors)

    def test_empty_target_rejected_but_variant_only_ok(self):
        config = make_config(
            patches=[
                Patch(source=PatchSource(provider="openai"), target=PatchTarget()),
                Patch(
                    source=PatchSource(provider="openai"),
                    target=PatchTarget(variant=None),
                ),
            ]
        )
        errors = validate_config(config, CACHE)
        assert sum("target must specify at least" in e for e in errors) == 1

    def test_exact_model_not_in_provider(self):
        config = make_config(
            patches=[
                Patch(
                    source=PatchSource(provider="openai", model="gpt-9"),
                    target=PatchTarget(model="gpt-5.4"),
                )
            ]
        )
        errors = validate_config(config, CACHE)
        assert any("'gpt-9' not found in provider 'openai'" in e for e in errors)

    def test_filter_matching_no_models(self):
        """Regression: typo'd filter terms passed validation silently."""
        config = make_config(
            patches=[
                Patch(
                    source=PatchSource(provider="anthropic", model=["opsu"]),
                    target=PatchTarget(model="gpt-5.4"),
                )
            ]
        )
        errors = validate_config(config, CACHE)
        assert any("matches no models in provider 'anthropic'" in e for e in errors)

    def test_malformed_filter_reported_not_crash(self):
        """Regression: malformed filters crashed with a raw traceback."""
        config = make_config(
            patches=[
                Patch(
                    source=PatchSource(
                        provider="anthropic", model={"includes": ["opus"]}
                    ),
                    target=PatchTarget(model={"include": "gpt"}),
                )
            ]
        )
        errors = validate_config(config, CACHE)
        assert any("source model" in e and "unknown key" in e for e in errors)

    def test_target_model_without_provider_checked_against_all(self):
        config = make_config(
            patches=[
                Patch(
                    source=PatchSource(provider="anthropic"),
                    target=PatchTarget(model="not-a-model-anywhere"),
                )
            ]
        )
        errors = validate_config(config, CACHE)
        assert any("not found in any provider" in e for e in errors)

    def test_remove_fallbacks_requires_scope(self):
        config = make_config(remove_fallbacks=[PatchSource(model=["opus"])])
        errors = validate_config(config, CACHE)
        assert any(
            "remove_fallbacks [0]: source must specify at least" in e for e in errors
        )

    def test_remove_fallbacks_filter_zero_match(self):
        config = make_config(
            remove_fallbacks=[PatchSource(provider="openai", model=["claude"])]
        )
        errors = validate_config(config, CACHE)
        assert any("matches no models in provider 'openai'" in e for e in errors)

    def test_profile_scoped_errors_have_context(self):
        config = make_config(
            profiles=[
                Profile(
                    name="Test",
                    providers=["claude"],
                    patches=[
                        Patch(
                            source=PatchSource(provider="nope"),
                            target=PatchTarget(model="gpt-5.4"),
                        )
                    ],
                )
            ]
        )
        errors = validate_config(config, CACHE)
        assert any(e.startswith("profile 'Test' patch [0]") for e in errors)
