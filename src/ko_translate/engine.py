"""Core translation engine with LM Studio and OpenAI backends."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional

import httpx

from .config import EngineType, FailMode, TranslationConfig
from .context import ContextManager
from .logging_config import TranslationLogger, get_logger
from .preservation import PreservationResult, preserve_code_blocks, restore_code_blocks


class TranslationError(Exception):
    pass


class TranslationBackend(ABC):
    @abstractmethod
    async def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        context: Optional[list[dict[str, str]]] = None,
    ) -> str:
        pass

    @abstractmethod
    async def translate_stream(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        context: Optional[list[dict[str, str]]] = None,
    ) -> AsyncIterator[str]:
        pass


class LMStudioBackend(TranslationBackend):
    def __init__(
        self,
        base_url: str,
        model_name: str,
        logger: TranslationLogger,
        timeout: float = 60.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.logger = logger
        self.timeout = timeout

    async def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        context: Optional[list[dict[str, str]]] = None,
    ) -> str:
        messages = self._build_messages(text, source_lang, target_lang, context)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/chat/completions",
                json={
                    "model": self.model_name,
                    "messages": messages,
                    "temperature": 0.3,
                    "max_tokens": 2000,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

    async def translate_stream(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        context: Optional[list[dict[str, str]]] = None,
    ) -> AsyncIterator[str]:
        messages = self._build_messages(text, source_lang, target_lang, context)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/v1/chat/completions",
                json={
                    "model": self.model_name,
                    "messages": messages,
                    "temperature": 0.3,
                    "max_tokens": 2000,
                    "stream": True,
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        if line.strip() == "data: [DONE]":
                            break
                        data = json.loads(line[6:])
                        if "delta" in data["choices"][0]:
                            content = data["choices"][0]["delta"].get("content", "")
                            if content:
                                yield content

    def _build_messages(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        context: Optional[list[dict[str, str]]] = None,
    ) -> list[dict[str, str]]:
        system_prompt = (
            f"You are a professional translator. Translate the following text from {source_lang} to {target_lang}. "
            f"Preserve all code blocks, technical terms, and formatting. "
            f"Only translate the actual content, not any code or technical identifiers."
        )

        messages = [{"role": "system", "content": system_prompt}]

        if context:
            for turn in context[-5:]:
                if turn.get("original"):
                    messages.append({"role": "user", "content": turn["original"]})
                if turn.get("translated"):
                    messages.append({"role": "assistant", "content": turn["translated"]})

        messages.append({"role": "user", "content": text})
        return messages


class OpenAIBackend(TranslationBackend):
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        logger: TranslationLogger,
        timeout: float = 60.0,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.logger = logger
        self.timeout = timeout

    async def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        context: Optional[list[dict[str, str]]] = None,
    ) -> str:
        messages = self._build_messages(text, source_lang, target_lang, context)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.3,
                    "max_tokens": 2000,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

    async def translate_stream(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        context: Optional[list[dict[str, str]]] = None,
    ) -> AsyncIterator[str]:
        messages = self._build_messages(text, source_lang, target_lang, context)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.3,
                    "max_tokens": 2000,
                    "stream": True,
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        if line.strip() == "data: [DONE]":
                            break
                        data = json.loads(line[6:])
                        if "delta" in data["choices"][0]:
                            content = data["choices"][0]["delta"].get("content", "")
                            if content:
                                yield content

    def _build_messages(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        context: Optional[list[dict[str, str]]] = None,
    ) -> list[dict[str, str]]:
        system_prompt = (
            f"You are a professional translator. Translate the following text from {source_lang} to {target_lang}. "
            f"Preserve all code blocks, technical terms, and formatting. "
            f"Only translate the actual content, not any code or technical identifiers."
        )

        messages = [{"role": "system", "content": system_prompt}]

        if context:
            for turn in context[-5:]:
                if turn.get("original"):
                    messages.append({"role": "user", "content": turn["original"]})
                if turn.get("translated"):
                    messages.append({"role": "assistant", "content": turn["translated"]})

        messages.append({"role": "user", "content": text})
        return messages


class TranslationEngine:
    def __init__(self, config: TranslationConfig, logger: TranslationLogger):
        self.config = config
        self.logger = logger
        self.primary_backend: Optional[TranslationBackend] = None
        self.fallback_backend: Optional[TranslationBackend] = None
        self.context_manager = ContextManager(max_turns=config.max_context_turns)
        self._session_id: Optional[str] = None
        self._setup_backends()

    def set_session(self, session_id: str):
        """Set the session ID for conversation context."""
        self._session_id = session_id

    def get_context(self) -> list[dict[str, str]]:
        """Get conversation context for the current session."""
        if self._session_id:
            return self.context_manager.get_context(self._session_id)
        return []

    def _record_turn(self, original: str, translated: str, direction: str):
        """Record a translation turn for conversation context."""
        if self._session_id:
            self.context_manager.record_turn(self._session_id, original, translated, direction)

    def _setup_backends(self):
        if self.config.engine == EngineType.LOCAL:
            self.primary_backend = LMStudioBackend(
                base_url=self.config.local_model_url,
                model_name=self.config.local_model_name,
                logger=self.logger,
            )
        else:
            self.primary_backend = OpenAIBackend(
                api_key=self.config.openai_api_key or "",
                base_url=self.config.openai_base_url,
                model=self.config.openai_model,
                logger=self.logger,
            )

        self.fallback_backend = OpenAIBackend(
            api_key=self.config.openai_api_key or "",
            base_url=self.config.openai_base_url,
            model=self.config.openai_model,
            logger=self.logger,
        )

    async def ko_to_en(
        self,
        text: str,
        context: Optional[list[dict[str, str]]] = None,
        preserve: bool = True,
    ) -> str:
        result = await self._translate(text, "Korean", "English", context, preserve)
        self._record_turn(text, result, "ko-en")
        return result

    async def en_to_ko(
        self,
        text: str,
        context: Optional[list[dict[str, str]]] = None,
        preserve: bool = True,
    ) -> str:
        result = await self._translate(text, "English", "Korean", context, preserve)
        self._record_turn(text, result, "en-ko")
        return result

    async def ko_to_en_stream(
        self,
        text: str,
        context: Optional[list[dict[str, str]]] = None,
    ) -> AsyncIterator[str]:
        async for chunk in self.translate_stream_ko_to_en(text, context):
            yield chunk

    async def en_to_ko_stream(
        self,
        text: str,
        context: Optional[list[dict[str, str]]] = None,
    ) -> AsyncIterator[str]:
        async for chunk in self.translate_stream_en_to_ko(text, context):
            yield chunk

    async def _translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        context: Optional[list[dict[str, str]]] = None,
        preserve: bool = True,
    ) -> str:
        preserve_result: Optional[PreservationResult] = None
        if preserve:
            preserve_result = preserve_code_blocks(text)
            text = preserve_result.processed_text

        try:
            result = await self.primary_backend.translate(text, source_lang, target_lang, context)
        except Exception as primary_err:
            self.logger.log_failure(text, "", f"{source_lang}->{target_lang}", primary_err)
            if self.config.fail_mode == FailMode.CLOSED:
                raise TranslationError(
                    f"Primary translation failed: {primary_err}"
                ) from primary_err

            if self.fallback_backend and self.config.fail_mode == FailMode.CONFIGURABLE:
                try:
                    result = await self.fallback_backend.translate(
                        text, source_lang, target_lang, context
                    )
                except Exception as fallback_err:
                    self.logger.log_failure(text, "", f"{source_lang}->{target_lang}", fallback_err)
                    if self.config.fail_mode == FailMode.CLOSED:
                        raise TranslationError(
                            f"Fallback translation failed: {fallback_err}"
                        ) from fallback_err
                    result = text
            else:
                result = text

        if preserve and preserve_result:
            result = restore_code_blocks(result, preserve_result.preserved)

        return result

    async def translate_stream_ko_to_en(
        self,
        text: str,
        context: Optional[list[dict[str, str]]] = None,
    ) -> AsyncIterator[str]:
        preserve_result = preserve_code_blocks(text)
        processed_text = preserve_result.processed_text

        try:
            async for chunk in self.primary_backend.translate_stream(
                processed_text, "Korean", "English", context
            ):
                yield chunk
        except Exception as err:
            self.logger.log_failure(text, "", "ko->en (stream)", err)
            if self.config.fail_mode != FailMode.OPEN:
                raise TranslationError(f"Streaming translation failed: {err}") from err
            yield text

    async def translate_stream_en_to_ko(
        self,
        text: str,
        context: Optional[list[dict[str, str]]] = None,
    ) -> AsyncIterator[str]:
        preserve_result = preserve_code_blocks(text)
        processed_text = preserve_result.processed_text

        try:
            async for chunk in self.primary_backend.translate_stream(
                processed_text, "English", "Korean", context
            ):
                yield chunk
        except Exception as err:
            self.logger.log_failure(text, "", "en->ko (stream)", err)
            if self.config.fail_mode != FailMode.OPEN:
                raise TranslationError(f"Streaming translation failed: {err}") from err
            yield text


def create_engine(config: TranslationConfig) -> tuple[TranslationEngine, TranslationLogger]:
    logger = get_logger(
        log_file=config.log_file,
        level=config.log_level.value,
    )
    engine = TranslationEngine(config, logger)
    return engine, logger
