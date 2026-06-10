from __future__ import annotations

import subprocess

import pytest

import omoctl.models as models
from omoctl.models import find_best_matching_model, load_models
from omoctl.types import ModelFilter


class TestLoadModels:
    def test_parses_models_and_filters_noise(self, monkeypatch):
        stdout = "\n".join(
            [
                "anthropic/claude-opus-4-7",
                "  openai/gpt-5.4  ",
                "openrouter/anthropic/claude-opus-4-7",
                "fetching models from models.dev ...",  # noise: whitespace
                "warning: stale cache at /home/x/.cache",  # noise: whitespace
                "https://models.dev/api",  # noise: model part starts with /
                "no-slash-line",
                "/leading",
                "trailing/",
                "",
            ]
        )
        monkeypatch.setattr(models.shutil, "which", lambda _: "/usr/bin/opencode")
        monkeypatch.setattr(
            models.subprocess,
            "run",
            lambda *a, **k: subprocess.CompletedProcess(
                [], 0, stdout=stdout, stderr=""
            ),
        )
        result = load_models()
        assert result == {
            "anthropic": ("claude-opus-4-7",),
            "openai": ("gpt-5.4",),
            "openrouter": ("anthropic/claude-opus-4-7",),
        }

    def test_nonzero_exit_dies(self, monkeypatch):
        monkeypatch.setattr(models.shutil, "which", lambda _: "/usr/bin/opencode")
        monkeypatch.setattr(
            models.subprocess,
            "run",
            lambda *a, **k: subprocess.CompletedProcess(
                [], 1, stdout="", stderr="boom"
            ),
        )
        with pytest.raises(SystemExit):
            load_models()

    def test_missing_opencode_dies(self, monkeypatch):
        monkeypatch.setattr(models.shutil, "which", lambda _: None)
        with pytest.raises(SystemExit):
            load_models()


PROVIDERS = {
    "anthropic": (
        "claude-opus-4-7",
        "claude-opus-4-7-20250101",
        "claude-haiku-4-5",
        "claude-opus-latest",
    ),
    "openai": ("gpt-5.4", "gpt-5.4-mini"),
}


class TestFindBestMatchingModel:
    def test_exact_target(self):
        assert (
            find_best_matching_model(PROVIDERS, None, None, "openai", "gpt-5.4")
            == "openai/gpt-5.4"
        )

    def test_exact_target_missing_dies(self):
        with pytest.raises(SystemExit):
            find_best_matching_model(PROVIDERS, None, None, "openai", "gpt-9")

    def test_unknown_provider_dies(self):
        with pytest.raises(SystemExit):
            find_best_matching_model(PROVIDERS, None, None, "nope", "gpt-5.4")

    def test_filter_match(self):
        result = find_best_matching_model(
            PROVIDERS, None, None, "anthropic", ModelFilter(words_include=("haiku",))
        )
        assert result == "anthropic/claude-haiku-4-5"

    def test_prefers_undated_and_unaliased(self):
        result = find_best_matching_model(
            PROVIDERS, None, None, "anthropic", ModelFilter(words_include=("opus",))
        )
        assert result == "anthropic/claude-opus-4-7"

    def test_same_model_kept_without_hint(self):
        result = find_best_matching_model(
            PROVIDERS, "anthropic", "claude-opus-4-7", "anthropic", None
        )
        assert result == "anthropic/claude-opus-4-7"

    def test_no_match_dies(self):
        with pytest.raises(SystemExit):
            find_best_matching_model(
                PROVIDERS, None, None, "openai", ModelFilter(words_include=("claude",))
            )

    def test_version_relaxation(self):
        # No gpt with number 9 — falls back to word-only matching.
        result = find_best_matching_model(
            PROVIDERS,
            None,
            None,
            "openai",
            ModelFilter(words_include=("gpt", "mini"), numbers_include=("9",)),
        )
        assert result == "openai/gpt-5.4-mini"
