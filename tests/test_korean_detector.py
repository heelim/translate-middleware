"""Tests for korean_detector module."""

import pytest
from ko_translate.korean_detector import contains_korean, detect_korean_ratio


class TestContainsKorean:
    def test_pure_korean_returns_true(self):
        assert contains_korean("안녕하세요") is True
        assert contains_korean("한국어 텍스트") is True
        assert contains_korean("이것은 한국어입니다") is True

    def test_pure_english_returns_false(self):
        assert contains_korean("Hello") is False
        assert contains_korean("This is English") is False
        assert contains_korean("English text only") is False

    def test_mixed_text_with_high_korean_ratio_returns_true(self):
        assert contains_korean("Hello 안녕하세요") is True
        assert contains_korean("안녕하세요 Hello") is True
        assert contains_korean("이것은 test 입니다") is True

    def test_mixed_text_with_low_korean_ratio_returns_false(self):
        assert contains_korean("Hello world Korean here") is False
        assert contains_korean("Korean text in english sentence") is False

    def test_empty_string_returns_false(self):
        assert contains_korean("") is False

    def test_whitespace_only_returns_false(self):
        assert contains_korean("   ") is False
        assert contains_korean("\t\n") is False

    def test_numbers_and_symbols_returns_false(self):
        assert contains_korean("12345") is False
        assert contains_korean("!@#$%") is False

    def test_korean_threshold_boundary(self):
        from ko_translate.korean_detector import KOREAN_THRESHOLD
        ratio_just_below = "A 가"  # 1/2 = 0.5 > 0.3, so True
        ratio_just_above = "AAAAA 가"  # 1/6 < 0.3, so False
        assert contains_korean("AAAAA 가") is False


class TestDetectKoreanRatio:
    def test_pure_korean_returns_one(self):
        assert detect_korean_ratio("안녕하세요") == 1.0
        assert detect_korean_ratio("한국어") == 1.0

    def test_pure_english_returns_zero(self):
        assert detect_korean_ratio("Hello") == 0.0
        assert detect_korean_ratio("English") == 0.0
        assert detect_korean_ratio("ABC") == 0.0

    def test_mixed_text_returns_correct_ratio(self):
        ratio = detect_korean_ratio("Hello 안녕하세요")
        assert 0.0 < ratio < 1.0
        assert ratio == pytest.approx(0.5)

    def test_empty_string_returns_zero(self):
        assert detect_korean_ratio("") == 0.0

    def test_no_alpha_characters_returns_zero(self):
        assert detect_korean_ratio("12345") == 0.0
        assert detect_korean_ratio("!@#$%") == 0.0
        assert detect_korean_ratio("   \t\n") == 0.0

    def test_korean_only_alpha_characters(self):
        assert detect_korean_ratio("안녕123") == 1.0
        assert detect_korean_ratio("123한글456") == 1.0

    def test_even_mix(self):
        ratio = detect_korean_ratio("한글 English")
        expected = 2.0 / 9.0
        assert ratio == pytest.approx(expected)
