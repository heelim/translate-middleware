"""Tests for preservation module."""

import pytest
from ko_translate.preservation import (
    PreservationResult,
    preserve_code_blocks,
    restore_code_blocks,
    should_preserve_token,
)


class TestPreserveCodeBlocks:
    def test_markdown_code_block_preserved(self):
        text = '```python\ndef hello():\n    print("hi")\n```'
        result = preserve_code_blocks(text)

        assert len(result.preserved) == 1
        assert result.preserved[0] == text
        assert "\x00MEDIATOR_CODE_MARKER_0\x00" in result.processed_text

    def test_inline_code_preserved(self):
        text = "Use `print()` function"
        result = preserve_code_blocks(text)

        assert len(result.preserved) == 1
        assert result.preserved[0] == "`print()`"
        assert "\x00MEDIATOR_CODE_MARKER_0\x00" in result.processed_text

    def test_multiple_code_blocks_preserved(self):
        text = 'First `code1` then ```python code2``` and finally $var'
        result = preserve_code_blocks(text)

        assert len(result.preserved) == 3
        assert "code1" in result.preserved[0]
        assert "python code2" in result.preserved[1]

    def test_mathematical_expressions_preserved(self):
        text = "The variable $count and function $sum are here"
        result = preserve_code_blocks(text)

        assert len(result.preserved) >= 2
        assert "$count" in result.preserved[0] or "$sum" in result.preserved[0]

    def test_function_calls_preserved(self):
        text = "Call processData(){} now"
        result = preserve_code_blocks(text)

        assert len(result.preserved) >= 1

    def test_no_code_blocks_unchanged(self):
        text = "Just plain text here"
        result = preserve_code_blocks(text)

        assert len(result.preserved) == 0
        assert result.processed_text == text

    def test_mixed_content(self):
        text = "Hello 안녕하세요, use `code` here, and $var too"
        result = preserve_code_blocks(text)

        assert len(result.preserved) >= 2
        assert "안녕하세요" in result.processed_text


class TestRestoreCodeBlocks:
    def test_restores_single_code_block(self):
        original = '```python\ndef hello():\n    pass\n```'
        preserved = {0: original}
        processed = "\x00MEDIATOR_CODE_MARKER_0\x00"

        result = restore_code_blocks(processed, preserved)
        assert result == original

    def test_restores_multiple_code_blocks(self):
        preserved = {
            0: '```python\ncode1\n```',
            1: "`inline`",
            2: "$var",
        }
        processed = "text \x00MEDIATOR_CODE_MARKER_0\x00 more \x00MEDIATOR_CODE_MARKER_1\x00 end \x00MEDIATOR_CODE_MARKER_2\x00"

        result = restore_code_blocks(processed, preserved)
        assert '```python\ncode1\n```' in result
        assert "`inline`" in result
        assert "$var" in result

    def test_unknown_marker_returns_original(self):
        preserved = {0: "known"}
        processed = "\x00MEDIATOR_CODE_MARKER_0\x00 \x00MEDIATOR_CODE_MARKER_99\x00"

        result = restore_code_blocks(processed, preserved)
        assert "known" in result
        assert "\x00MEDIATOR_CODE_MARKER_99\x00" in result

    def test_empty_preserved_dict(self):
        text = "Hello \x00MEDIATOR_CODE_MARKER_0\x00"
        result = restore_code_blocks(text, {})
        assert "\x00MEDIATOR_CODE_MARKER_0\x00" in result


class TestRoundTrip:
    def test_preserve_then_restore_returns_original(self):
        original = '```python\ndef test(): pass\n``` and `inline` plus $var'

        result = preserve_code_blocks(original)
        restored = restore_code_blocks(result.processed_text, result.preserved)

        assert '```python\ndef test(): pass\n```' in restored
        assert "`inline`" in restored
        assert "$var" in restored

    def test_multiple_round_trips(self):
        text = "`code1` and ```code2``` and $var"

        result1 = preserve_code_blocks(text)
        restored1 = restore_code_blocks(result1.processed_text, result1.preserved)

        result2 = preserve_code_blocks(restored1)
        restored2 = restore_code_blocks(result2.processed_text, result2.preserved)

        assert "`code1`" in restored2
        assert "```code2```" in restored2
        assert "$var" in restored2


class TestShouldPreserveToken:
    def test_code_block_tokens_preserved(self):
        assert should_preserve_token("```python\ncode\n```") is True
        assert should_preserve_token("```javascript\ncode\n```") is True

    def test_inline_code_preserved(self):
        assert should_preserve_token("`print()`") is True
        assert should_preserve_token("`variable`") is True

    def test_math_variables_preserved(self):
        assert should_preserve_token("$count") is True
        assert should_preserve_token("$sum") is True

    def test_method_calls_with_semicolons_preserved(self):
        assert should_preserve_token("obj.method();") is True

    def test_import_statements_preserved(self):
        assert should_preserve_token("import os") is True
        assert should_preserve_token("from typing import List") is True

    def test_dict_assignment_preserved(self):
        assert should_preserve_token("data = {key: value}") is True

    def test_django_templates_preserved(self):
        assert should_preserve_token("{{ variable }}") is True
        assert should_preserve_token("{{ user.name }}") is True

    def test_plain_text_not_preserved(self):
        assert should_preserve_token("Hello") is False
        assert should_preserve_token("안녕하세요") is False
        assert should_preserve_token("This is plain text") is False

    def test_partial_matches(self):
        assert should_preserve_token("Use the `code` here") is True
        assert should_preserve_token("This $variable is used") is True
