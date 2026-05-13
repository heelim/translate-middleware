"""Tests for context module."""

import pytest
from ko_translate.context import (
    ConversationContext,
    ConversationTurn,
    ContextManager,
)


class TestConversationTurn:
    def test_creates_turn_with_required_fields(self):
        turn = ConversationTurn(
            original="Hello",
            translated="안녕하세요",
            direction="en->ko",
        )
        assert turn.original == "Hello"
        assert turn.translated == "안녕하세요"
        assert turn.direction == "en->ko"

    def test_turn_with_default_timestamp(self):
        turn = ConversationTurn(
            original="Hi",
            translated="안녕",
            direction="en->ko",
        )
        assert turn.timestamp == 0.0

    def test_turn_with_custom_timestamp(self):
        turn = ConversationTurn(
            original="Hi",
            translated="안녕",
            direction="en->ko",
            timestamp=12345.678,
        )
        assert turn.timestamp == 12345.678


class TestConversationContext:
    def test_add_turn_appends_to_turns(self):
        ctx = ConversationContext()
        ctx.add_turn("Hello", "안녕하세요", "en->ko")

        assert len(ctx.turns) == 1
        assert ctx.turns[0].original == "Hello"

    def test_add_turn_enforces_max_turns(self):
        ctx = ConversationContext(max_turns=3)

        for i in range(5):
            ctx.add_turn(f"text{i}", f"번역{i}", "en->ko")

        assert len(ctx.turns) == 3
        assert ctx.turns[-1].original == "text4"

    def test_add_turn_trims_oldest_turns(self):
        ctx = ConversationContext(max_turns=3)

        for i in range(5):
            ctx.add_turn(f"text{i}", f"번역{i}", "en->ko")

        assert ctx.turns[0].original == "text2"
        assert ctx.turns[-1].original == "text4"

    def test_get_context_for_translation_returns_last_5(self):
        ctx = ConversationContext(max_turns=10)

        for i in range(7):
            ctx.add_turn(f"original{i}", f"translated{i}", "en->ko")

        context = ctx.get_context_for_translation()
        assert len(context) == 5
        assert context[0]["original"] == "original2"
        assert context[-1]["original"] == "original6"

    def test_get_context_for_translation_format(self):
        ctx = ConversationContext()
        ctx.add_turn("Hello", "안녕하세요", "en->ko")

        context = ctx.get_context_for_translation()
        assert len(context) == 1
        assert "original" in context[0]
        assert "translated" in context[0]

    def test_clear_removes_all_turns(self):
        ctx = ConversationContext()
        ctx.add_turn("Hello", "안녕하세요", "en->ko")
        ctx.add_turn("World", "세계", "en->ko")

        ctx.clear()
        assert len(ctx.turns) == 0

    def test_empty_context(self):
        ctx = ConversationContext()
        assert len(ctx.turns) == 0
        assert ctx.get_context_for_translation() == []


class TestContextManager:
    def test_get_or_create_session_creates_new(self):
        manager = ContextManager()
        ctx = manager.get_or_create_session("session1")

        assert ctx is not None
        assert isinstance(ctx, ConversationContext)

    def test_get_or_create_session_returns_same(self):
        manager = ContextManager()
        ctx1 = manager.get_or_create_session("session1")
        ctx2 = manager.get_or_create_session("session1")

        assert ctx1 is ctx2

    def test_multiple_sessions_independent(self):
        manager = ContextManager()
        ctx1 = manager.get_or_create_session("session1")
        ctx2 = manager.get_or_create_session("session2")

        ctx1.add_turn("Hello", "안녕", "en->ko")
        ctx2.add_turn("World", "세계", "en->ko")

        assert len(ctx1.turns) == 1
        assert len(ctx2.turns) == 1

    def test_record_turn(self):
        manager = ContextManager()
        manager.record_turn("session1", "Hello", "안녕하세요", "en->ko")

        ctx = manager.get_or_create_session("session1")
        assert len(ctx.turns) == 1
        assert ctx.turns[0].original == "Hello"

    def test_get_context(self):
        manager = ContextManager()
        manager.record_turn("session1", "Hello", "안녕하세요", "en->ko")
        manager.record_turn("session1", "World", "세계", "en->ko")

        context = manager.get_context("session1")
        assert len(context) == 2

    def test_clear_session(self):
        manager = ContextManager()
        manager.record_turn("session1", "Hello", "안녕하세요", "en->ko")

        manager.clear_session("session1")
        assert "session1" not in manager._sessions

    def test_clear_session_nonexistent(self):
        manager = ContextManager()
        manager.clear_session("nonexistent")

    def test_clear_all(self):
        manager = ContextManager()
        manager.record_turn("session1", "Hello", "안녕", "en->ko")
        manager.record_turn("session2", "World", "세계", "en->ko")

        manager.clear_all()
        assert len(manager._sessions) == 0

    def test_max_turns_per_session(self):
        manager = ContextManager(max_turns=2)
        manager.record_turn("session1", "t1", "t1k", "en->ko")
        manager.record_turn("session1", "t2", "t2k", "en->ko")
        manager.record_turn("session1", "t3", "t3k", "en->ko")

        ctx = manager.get_or_create_session("session1")
        assert len(ctx.turns) == 2
