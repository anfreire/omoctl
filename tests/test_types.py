from __future__ import annotations

import pytest

from omoctl.types import (
    ModelFilter,
    ModelProps,
    parse_model_spec,
    split_words_numbers,
)


class TestSplitWordsNumbers:
    def test_basic_split(self):
        words, numbers = split_words_numbers(("claude", "opus", "4", "7"))
        assert words == ("claude", "opus")
        assert numbers == ("4", "7")

    def test_mixed_token(self):
        words, numbers = split_words_numbers(("gpt5",))
        assert words == ("gpt",)
        assert numbers == ("5",)

    def test_empty_and_symbol_parts_dropped(self):
        words, numbers = split_words_numbers(("", "-", "x"))
        assert words == ("x",)
        assert numbers == ()


class TestModelProps:
    def test_plain_model_id(self):
        props = ModelProps.from_model_id("claude-opus-4-7")
        assert props.provider_prefix is None
        assert props.words == ("claude", "opus")
        assert props.numbers == ("4", "7")

    def test_provider_prefix(self):
        props = ModelProps.from_model_id("anthropic/claude-opus-4-7")
        assert props.provider_prefix == "anthropic"
        assert props.words == ("claude", "opus")

    def test_dots_and_underscores(self):
        props = ModelProps.from_model_id("gpt-5.4_mini")
        assert props.words == ("gpt", "mini")
        assert props.numbers == ("5", "4")


class TestModelFilterMatches:
    PROPS = ModelProps.from_model_id("claude-opus-4-7")

    def test_include_words(self):
        assert ModelFilter(words_include=("opus",)).matches(self.PROPS)
        assert not ModelFilter(words_include=("haiku",)).matches(self.PROPS)

    def test_exclude_words(self):
        assert not ModelFilter(words_exclude=("opus",)).matches(self.PROPS)

    def test_numbers(self):
        assert ModelFilter(numbers_include=("4", "7")).matches(self.PROPS)
        assert not ModelFilter(numbers_include=("8",)).matches(self.PROPS)
        assert not ModelFilter(numbers_exclude=("7",)).matches(self.PROPS)

    def test_specificity(self):
        f = ModelFilter(words_include=("a", "b"), numbers_exclude=("1",))
        assert f.specificity == 3


class TestModelFilterFromRaw:
    def test_keyword_list(self):
        f = ModelFilter.from_raw(["claude", "opus", 4])
        assert f.words_include == ("claude", "opus")
        assert f.numbers_include == ("4",)

    def test_include_exclude_dict(self):
        f = ModelFilter.from_raw({"include": ["claude"], "exclude": ["haiku", 3]})
        assert f.words_include == ("claude",)
        assert f.words_exclude == ("haiku",)
        assert f.numbers_exclude == ("3",)

    def test_scalar_values_coerced(self):
        f = ModelFilter.from_raw({"include": "opus"})
        assert f.words_include == ("opus",)

    def test_unknown_key_rejected(self):
        with pytest.raises(ValueError, match="unknown key"):
            ModelFilter.from_raw({"includes": ["opus"]})

    def test_empty_list_rejected(self):
        with pytest.raises(ValueError, match="empty"):
            ModelFilter.from_raw([])

    def test_empty_dict_rejected(self):
        with pytest.raises(ValueError, match="include"):
            ModelFilter.from_raw({})

    def test_useless_terms_rejected(self):
        with pytest.raises(ValueError, match="no usable terms"):
            ModelFilter.from_raw(["-"])

    def test_wrong_value_type_rejected(self):
        with pytest.raises(ValueError, match="must be a term or a list"):
            ModelFilter.from_raw({"include": {"x": 1}})

    def test_non_scalar_term_rejected(self):
        with pytest.raises(ValueError, match="terms must be strings or numbers"):
            ModelFilter.from_raw([{"x": 1}])


class TestParseModelSpec:
    def test_none_means_match_all(self):
        assert parse_model_spec(None) is None

    def test_string_passthrough(self):
        assert parse_model_spec("claude-opus-4-7") == "claude-opus-4-7"

    def test_empty_string_rejected(self):
        with pytest.raises(ValueError, match="empty string"):
            parse_model_spec("  ")

    def test_unsupported_type_rejected(self):
        with pytest.raises(ValueError, match="got int"):
            parse_model_spec(5)
