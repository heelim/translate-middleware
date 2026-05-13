"""Context management for conversation-aware translation."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ConversationTurn:
    original: str
    translated: str
    direction: str
    timestamp: float = 0.0


@dataclass
class ConversationContext:
    turns: list[ConversationTurn] = field(default_factory=list)
    max_turns: int = 10

    def add_turn(self, original: str, translated: str, direction: str):
        self.turns.append(
            ConversationTurn(original=original, translated=translated, direction=direction)
        )
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns :]

    def get_context_for_translation(self) -> list[dict[str, str]]:
        return [
            {"original": turn.original, "translated": turn.translated} for turn in self.turns[-5:]
        ]

    def clear(self):
        self.turns.clear()


class ContextManager:
    def __init__(self, max_turns: int = 10):
        self.max_turns = max_turns
        self._sessions: dict[str, ConversationContext] = {}

    def get_or_create_session(self, session_id: str) -> ConversationContext:
        if session_id not in self._sessions:
            self._sessions[session_id] = ConversationContext(max_turns=self.max_turns)
        return self._sessions[session_id]

    def record_turn(self, session_id: str, original: str, translated: str, direction: str):
        ctx = self.get_or_create_session(session_id)
        ctx.add_turn(original, translated, direction)

    def get_context(self, session_id: str) -> list[dict[str, str]]:
        ctx = self.get_or_create_session(session_id)
        return ctx.get_context_for_translation()

    def clear_session(self, session_id: str):
        if session_id in self._sessions:
            self._sessions[session_id].clear()
            del self._sessions[session_id]

    def clear_all(self):
        self._sessions.clear()
