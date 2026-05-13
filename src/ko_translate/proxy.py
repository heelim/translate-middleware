"""OpenAI-compatible proxy server for bidirectional translation."""

from __future__ import annotations

import json
import uuid
from typing import Any, AsyncIterator, Optional

from .config import StreamingMode, TranslationConfig
from .context import ContextManager
from .engine import TranslationEngine
from .korean_detector import contains_korean
from .logging_config import TranslationLogger


class TranslationProxy:
    def __init__(
        self,
        config: TranslationConfig,
        engine: TranslationEngine,
        logger: TranslationLogger,
    ):
        self.config = config
        self.engine = engine
        self.logger = logger
        self.context_manager = ContextManager(max_turns=config.max_context_turns)

    async def handle_chat_completion(
        self,
        request_data: dict[str, Any],
        session_id: Optional[str] = None,
    ) -> dict[str, Any]:
        if session_id is None:
            session_id = str(uuid.uuid4())

        messages = request_data.get("messages", [])
        if not messages:
            return request_data

        last_message = messages[-1]
        if last_message.get("role") != "user":
            return request_data

        user_content = last_message.get("content", "")
        if not isinstance(user_content, str):
            return request_data

        context = self.context_manager.get_context(session_id)

        needs_translation = (
            self.config.korean_detection_mode and contains_korean(user_content)
        ) or not self.config.korean_detection_mode

        if not needs_translation:
            return request_data

        if self.config.streaming_mode == StreamingMode.BUFFERED:
            translated_content = await self.engine.ko_to_en(user_content, context)
            last_message["content"] = translated_content
            request_data["messages"] = messages

            return request_data
        else:
            translated_content = await self.engine.ko_to_en(user_content, context)
            last_message["content"] = translated_content
            request_data["messages"] = messages
            return request_data

    async def handle_response(
        self,
        response_data: dict[str, Any],
        session_id: str,
        original_content: str,
    ) -> dict[str, Any]:
        if "choices" not in response_data or not response_data["choices"]:
            return response_data

        choice = response_data["choices"][0]
        if "message" not in choice:
            return response_data

        message = choice["message"]
        assistant_content = message.get("content", "")

        if not assistant_content:
            return response_data

        context = self.context_manager.get_context(session_id)
        translated_content = await self.engine.en_to_ko(assistant_content, context)

        self.context_manager.record_turn(
            session_id,
            original=original_content,
            translated=translated_content,
            direction="ko->en->ko",
        )

        message["content"] = translated_content
        return response_data

    async def handle_streaming_response(
        self,
        response_iterator: AsyncIterator[bytes],
        session_id: str,
        original_content: str,
    ) -> AsyncIterator[bytes]:
        buffer = ""
        context = self.context_manager.get_context(session_id)

        async for chunk in response_iterator:
            if isinstance(chunk, bytes):
                chunk = chunk.decode("utf-8")

            if chunk.startswith("data: "):
                if chunk.strip() == "data: [DONE]":
                    yield b"data: [DONE]\n\n"
                    break

                try:
                    data = json.loads(chunk[6:])
                except json.JSONDecodeError:
                    yield chunk.encode("utf-8") if isinstance(chunk, str) else chunk
                    continue

                if "choices" in data and data["choices"]:
                    delta = data["choices"][0].get("delta", {})
                    if "content" in delta:
                        buffer += delta["content"]
                        yield chunk.encode("utf-8") if isinstance(chunk, str) else chunk
                        continue

                yield chunk.encode("utf-8") if isinstance(chunk, str) else chunk
            else:
                yield chunk.encode("utf-8") if isinstance(chunk, str) else chunk

        if buffer:
            translated = await self.engine.en_to_ko(buffer, context)
            self.context_manager.record_turn(
                session_id,
                original=original_content,
                translated=translated,
                direction="ko->en->ko",
            )


async def proxy_request(
    request_data: dict[str, Any],
    config: TranslationConfig,
    engine: TranslationEngine,
    logger: TranslationLogger,
    session_id: Optional[str] = None,
    target_url: str = "https://api.openai.com/v1/chat/completions",
    api_key: Optional[str] = None,
) -> dict[str, Any]:
    proxy = TranslationProxy(config, engine, logger)

    if session_id is None:
        session_id = str(uuid.uuid4())

    messages = request_data.get("messages", [])
    original_content = ""
    if messages and messages[-1].get("role") == "user":
        original_content = messages[-1].get("content", "")

    modified_request = await proxy.handle_chat_completion(request_data, session_id)

    return modified_request, session_id, original_content
