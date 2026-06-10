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
                    "fallback_models": [{"model": "m/y"}],
                }
            }
        }
        out = diff_lines(capsys, None, patched, [("agents", "a")])
        assert "+  Agent 'a'" in out
        assert "+    model: m/x" in out
        assert "+    variant: max" in out
        assert any("m/y" in line for line in out)

    def test_removed_key_is_shown(self, capsys):
        """Regression: keys removed from an entry were invisible in the diff."""
        curr = {"agents": {"a": {"model": "m/x", "variant": "max"}}}
        patched = {"agents": {"a": {"model": "m/x"}}}
        out = diff_lines(capsys, curr, patched, [("agents", "a")])
        assert "    - variant: max" in out

    def test_null_to_null_is_not_a_change(self, capsys):
        """Regression: explicit nulls were reported as additions forever."""
        curr = {"agents": {"a": {"model": "m/x", "temperature": None}}}
        patched = {"agents": {"a": {"model": "m/x", "temperature": None}}}
        out = diff_lines(capsys, curr, patched, [("agents", "a")])
        assert not any(line.lstrip().startswith(("+", "-")) for line in out)

    def test_added_key_shown_as_plus(self, capsys):
        curr = {"agents": {"a": {"model": "m/x"}}}
        patched = {"agents": {"a": {"model": "m/x", "variant": "max"}}}
        out = diff_lines(capsys, curr, patched, [("agents", "a")])
        assert "    + variant: max" in out

    def test_changed_value_shows_both(self, capsys):
        curr = {"agents": {"a": {"model": "m/x", "variant": "low"}}}
        patched = {"agents": {"a": {"model": "m/x", "variant": "max"}}}
        out = diff_lines(capsys, curr, patched, [("agents", "a")])
        assert "    - variant: low" in out
        assert "    + variant: max" in out

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
