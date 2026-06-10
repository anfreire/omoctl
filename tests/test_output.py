from __future__ import annotations

import pytest

from omoctl.output import print_diff


def diff_lines(capsys, curr, patched, keys) -> list[str]:
    print_diff(curr, patched, keys)
    return [line.rstrip() for line in capsys.readouterr().out.splitlines()]


class TestPrintDiff:
    def test_new_entry_shows_all_keys(self, capsys):
        patched = {
            "agents": {
                "a": {
                    "model": "m/x",
                    "variant": "max",
                    "temperature": 0.5,
                    "fallback_models": [{"model": "m/y"}],
                }
            }
        }
        out = diff_lines(capsys, None, patched, [("agents", "a")])
        assert "+  Agent 'a'" in out
        assert "+    model: m/x (variant: max)" in out
        assert "+    temperature: 0.5" in out
        assert any("m/y" in line for line in out)

    def test_removed_key_is_shown(self, capsys):
        """Regression: keys removed from an entry were invisible in the diff."""
        curr = {"agents": {"a": {"model": "m/x", "temperature": 0.5}}}
        patched = {"agents": {"a": {"model": "m/x"}}}
        out = diff_lines(capsys, curr, patched, [("agents", "a")])
        assert "    - temperature: 0.5" in out

    def test_null_to_null_is_not_a_change(self, capsys):
        """Regression: explicit nulls were reported as additions forever."""
        curr = {"agents": {"a": {"model": "m/x", "temperature": None}}}
        patched = {"agents": {"a": {"model": "m/x", "temperature": None}}}
        out = diff_lines(capsys, curr, patched, [("agents", "a")])
        assert not any(line.lstrip().startswith(("+", "-")) for line in out)

    def test_added_key_shown_as_plus(self, capsys):
        curr = {"agents": {"a": {"model": "m/x"}}}
        patched = {"agents": {"a": {"model": "m/x", "temperature": 0.5}}}
        out = diff_lines(capsys, curr, patched, [("agents", "a")])
        assert "    + temperature: 0.5" in out

    def test_changed_value_shows_both(self, capsys):
        curr = {"agents": {"a": {"model": "m/x", "temperature": 0.2}}}
        patched = {"agents": {"a": {"model": "m/x", "temperature": 0.5}}}
        out = diff_lines(capsys, curr, patched, [("agents", "a")])
        assert "    - temperature: 0.2" in out
        assert "    + temperature: 0.5" in out

    def test_values_rendered_as_json(self, capsys):
        curr = {"agents": {"a": {"model": "m/x", "flag": None}}}
        patched = {"agents": {"a": {"model": "m/x", "flag": True}}}
        out = diff_lines(capsys, curr, patched, [("agents", "a")])
        assert "    - flag: null" in out
        assert "    + flag: true" in out

    def test_model_change_renders_diff(self, capsys):
        curr = {"agents": {"a": {"model": "m/old"}}}
        patched = {"agents": {"a": {"model": "m/new"}}}
        out = diff_lines(capsys, curr, patched, [("agents", "a")])
        assert "    - model: m/old" in out
        assert "    + model: m/new" in out

    def test_fallback_reorder_is_not_churn(self, capsys):
        fb1 = {"model": "m/x"}
        fb2 = {"model": "m/y", "variant": "max"}
        curr = {"agents": {"a": {"model": "m/m", "fallback_models": [fb1, fb2]}}}
        patched = {"agents": {"a": {"model": "m/m", "fallback_models": [fb2, fb1]}}}
        out = diff_lines(capsys, curr, patched, [("agents", "a")])
        assert not any(line.lstrip().startswith(("+", "-")) for line in out)

    def test_fallback_add_remove(self, capsys):
        curr = {
            "agents": {"a": {"model": "m/m", "fallback_models": [{"model": "m/old"}]}}
        }
        patched = {
            "agents": {"a": {"model": "m/m", "fallback_models": [{"model": "m/new"}]}}
        }
        out = diff_lines(capsys, curr, patched, [("agents", "a")])
        assert "      - m/old" in out
        assert "      + m/new" in out

    def test_fallbacks_removed_entirely(self, capsys):
        curr = {
            "agents": {"a": {"model": "m/m", "fallback_models": [{"model": "m/old"}]}}
        }
        patched = {"agents": {"a": {"model": "m/m"}}}
        out = diff_lines(capsys, curr, patched, [("agents", "a")])
        assert "      - m/old" in out

    def test_non_dict_override_entry_does_not_crash(self, capsys):
        curr = {"agents": {"a": {"model": "m/x"}}}
        patched = {"agents": {"a": "replaced"}}
        out = diff_lines(capsys, curr, patched, [("agents", "a")])
        assert any("replaced" in line for line in out)

    @pytest.mark.parametrize(
        "section,label", [("agents", "Agent"), ("categories", "Category")]
    )
    def test_section_labels(self, capsys, section, label):
        patched = {section: {"x": {"model": "m/x"}}}
        out = diff_lines(capsys, None, patched, [(section, "x")])
        assert any(label in line for line in out)


class TestVariantOnModelLine:
    """The main model renders its variant inline — `model (variant: x)` —
    exactly like fallback entries, in every view."""

    def test_unchanged_variant_shown_inline(self, capsys):
        entry = {"model": "m/x", "variant": "max"}
        curr = {"agents": {"a": dict(entry)}}
        patched = {"agents": {"a": dict(entry)}}
        out = diff_lines(capsys, curr, patched, [("agents", "a")])
        assert "    model: m/x (variant: max)" in out
        assert not any(line.lstrip().startswith(("+", "-")) for line in out)

    def test_variant_change_diffs_on_model_line(self, capsys):
        curr = {"agents": {"a": {"model": "m/x", "variant": "low"}}}
        patched = {"agents": {"a": {"model": "m/x", "variant": "max"}}}
        out = diff_lines(capsys, curr, patched, [("agents", "a")])
        assert "    - model: m/x (variant: low)" in out
        assert "    + model: m/x (variant: max)" in out
        assert not any("variant:" in line and "model" not in line for line in out)

    def test_variant_removed_diffs_on_model_line(self, capsys):
        curr = {"agents": {"a": {"model": "m/x", "variant": "max"}}}
        patched = {"agents": {"a": {"model": "m/x"}}}
        out = diff_lines(capsys, curr, patched, [("agents", "a")])
        assert "    - model: m/x (variant: max)" in out
        assert "    + model: m/x" in out

    def test_variant_added_diffs_on_model_line(self, capsys):
        curr = {"agents": {"a": {"model": "m/x"}}}
        patched = {"agents": {"a": {"model": "m/x", "variant": "max"}}}
        out = diff_lines(capsys, curr, patched, [("agents", "a")])
        assert "    - model: m/x" in out
        assert "    + model: m/x (variant: max)" in out

    def test_model_change_keeps_variant_context(self, capsys):
        curr = {"agents": {"a": {"model": "m/old", "variant": "max"}}}
        patched = {"agents": {"a": {"model": "m/new", "variant": "max"}}}
        out = diff_lines(capsys, curr, patched, [("agents", "a")])
        assert "    - model: m/old (variant: max)" in out
        assert "    + model: m/new (variant: max)" in out

    def test_explicit_null_variant_to_absent_is_not_a_visible_change(self, capsys):
        curr = {"agents": {"a": {"model": "m/x", "variant": None}}}
        patched = {"agents": {"a": {"model": "m/x"}}}
        out = diff_lines(capsys, curr, patched, [("agents", "a")])
        assert "    model: m/x" in out
        assert not any(line.lstrip().startswith(("+", "-")) for line in out)

    @pytest.fixture
    def colors(self, monkeypatch):
        import omoctl.output as output_mod

        monkeypatch.setattr(output_mod, "RED", "<R>")
        monkeypatch.setattr(output_mod, "GREEN", "<G>")
        monkeypatch.setattr(output_mod, "DIM", "<D>")
        monkeypatch.setattr(output_mod, "RESET", "</>")

    def test_variant_only_change_dims_the_model_segment(self, capsys, colors):
        curr = {"agents": {"a": {"model": "m/x", "variant": "low"}}}
        patched = {"agents": {"a": {"model": "m/x", "variant": "max"}}}
        out = diff_lines(capsys, curr, patched, [("agents", "a")])
        minus = next(line for line in out if "- model:" in line)
        plus = next(line for line in out if "+ model:" in line)
        assert "<D>m/x</>" in minus and "<R>(variant: low)</>" in minus
        assert "<D>m/x</>" in plus and "<G>(variant: max)</>" in plus

    def test_model_only_change_dims_the_variant_segment(self, capsys, colors):
        curr = {"agents": {"a": {"model": "m/old", "variant": "max"}}}
        patched = {"agents": {"a": {"model": "m/new", "variant": "max"}}}
        out = diff_lines(capsys, curr, patched, [("agents", "a")])
        minus = next(line for line in out if "- model:" in line)
        plus = next(line for line in out if "+ model:" in line)
        assert "<R>m/old</>" in minus and "<D>(variant: max)</>" in minus
        assert "<G>m/new</>" in plus and "<D>(variant: max)</>" in plus

    def test_both_changed_accents_both_segments(self, capsys, colors):
        curr = {"agents": {"a": {"model": "m/old", "variant": "low"}}}
        patched = {"agents": {"a": {"model": "m/new", "variant": "max"}}}
        out = diff_lines(capsys, curr, patched, [("agents", "a")])
        minus = next(line for line in out if "- model:" in line)
        plus = next(line for line in out if "+ model:" in line)
        assert "<R>m/old</>" in minus and "<R>(variant: low)</>" in minus
        assert "<G>m/new</>" in plus and "<G>(variant: max)</>" in plus

    def test_null_variant_to_absent_renders_as_unchanged_entry(self, capsys, colors):
        curr = {"agents": {"a": {"model": "m/x", "variant": None}}}
        patched = {"agents": {"a": {"model": "m/x"}}}
        out = diff_lines(capsys, curr, patched, [("agents", "a")])
        assert "  <D>Agent 'a'</>" in out  # dim header = the unchanged block

    def test_main_and_fallback_variant_render_identically(self, capsys):
        entry = {
            "model": "m/x",
            "variant": "max",
            "fallback_models": [{"model": "m/y", "variant": "max"}],
        }
        curr = {"agents": {"a": dict(entry)}}
        patched = {"agents": {"a": dict(entry)}}
        out = diff_lines(capsys, curr, patched, [("agents", "a")])
        main = next(line for line in out if "m/x" in line)
        fb = next(line for line in out if "m/y" in line)
        assert main.strip() == "model: m/x (variant: max)"
        assert fb.strip() == "m/y (variant: max)"
