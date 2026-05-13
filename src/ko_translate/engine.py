"""Translation engine with dedicated translation API backends.

Backends:
  LMStudioBackend     — local LM Studio model (translation-only model)
  GoogleTranslateBackend — Google Cloud Translation API v2
  DeepLBackend        — DeepL API

The translation engine is intentionally decoupled from the target LLM
that the proxy forwards chatbot/agent requests to.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional

import httpx

from .config import EngineType, FailMode, TranslatorConfig

from .context import ContextManager
from .logging_config import TranslationLogger, get_logger
from .preservation import PreservationResult, preserve_code_blocks, restore_code_blocks

_LANG_NAMES = {"ko": "Korean", "en": "English"}


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

    async def translate_stream(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        context: Optional[list[dict[str, str]]] = None,
    ) -> AsyncIterator[str]:
        # Default: call translate() and yield in one chunk.
        # Override for backends that support real streaming.
        yield await self.translate(text, source_lang, target_lang, context)


class LMStudioBackend(TranslationBackend):
    """Local LM Studio model used exclusively for translation."""

    def __init__(self, base_url: str, model_name: str, logger: TranslationLogger, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.logger = logger
        self.timeout = timeout

    async def translate(self, text, source_lang, target_lang, context=None) -> str:
        messages = self._build_messages(text, source_lang, target_lang, context)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/chat/completions",
                json={"model": self.model_name, "messages": messages, "temperature": 0.3, "max_tokens": 2000},
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]

    async def translate_stream(self, text, source_lang, target_lang, context=None) -> AsyncIterator[str]:
        messages = self._build_messages(text, source_lang, target_lang, context)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/v1/chat/completions",
                json={"model": self.model_name, "messages": messages, "temperature": 0.3, "max_tokens": 2000, "stream": True},
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        if line.strip() == "data: [DONE]":
                            break
                        data = json.loads(line[6:])
                        content = data["choices"][0].get("delta", {}).get("content", "")
                        if content:
                            yield content

    def _build_messages(self, text, source_lang, target_lang, context) -> list[dict]:
        src = _LANG_NAMES.get(source_lang, source_lang)
        tgt = _LANG_NAMES.get(target_lang, target_lang)
        messages = [
            {"role": "system", "content": (
                f"You are a professional translator. "
                f"Translate from {src} to {tgt}. "
                f"Preserve code blocks, technical terms, and formatting. "
                f"Output only the translation, nothing else."
            )},
        ]
        if context:
            for turn in context[-5:]:
                if turn.get("original"):
                    messages.append({"role": "user", "content": turn["original"]})
                if turn.get("translated"):
                    messages.append({"role": "assistant", "content": turn["translated"]})
        messages.append({"role": "user", "content": text})
        return messages


class OpenAICompatibleBackend(TranslationBackend):
    """Any OpenAI-compatible API used as a translation engine.

    Configured independently from the proxied chat/agent LLM — they can
    be entirely different providers, endpoints, or API keys.
    """

    def __init__(self, base_url: str, api_key: str, model: str, logger: TranslationLogger, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.logger = logger
        self.timeout = timeout

    async def translate(self, text, source_lang, target_lang, context=None) -> str:
        messages = self._build_messages(text, source_lang, target_lang, context)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "messages": messages, "temperature": 0.3, "max_tokens": 2000},
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]

    async def translate_stream(self, text, source_lang, target_lang, context=None) -> AsyncIterator[str]:
        messages = self._build_messages(text, source_lang, target_lang, context)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "messages": messages, "temperature": 0.3, "max_tokens": 2000, "stream": True},
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        if line.strip() == "data: [DONE]":
                            break
                        data = json.loads(line[6:])
                        content = data["choices"][0].get("delta", {}).get("content", "")
                        if content:
                            yield content

    def _build_messages(self, text, source_lang, target_lang, context) -> list[dict]:
        src = _LANG_NAMES.get(source_lang, source_lang)
        tgt = _LANG_NAMES.get(target_lang, target_lang)
        messages = [
            {"role": "system", "content": (
                f"You are a professional translator. "
                f"Translate from {src} to {tgt}. "
                f"Preserve code blocks, technical terms, and formatting. "
                f"Output only the translation, nothing else."
            )},
        ]
        if context:
            for turn in context[-5:]:
                if turn.get("original"):
                    messages.append({"role": "user", "content": turn["original"]})
                if turn.get("translated"):
                    messages.append({"role": "assistant", "content": turn["translated"]})
        messages.append({"role": "user", "content": text})
        return messages


class GoogleTranslateBackend(TranslationBackend):
    """Google Cloud Translation API v2."""

    _URL = "https://translation.googleapis.com/language/translate/v2"

    def __init__(self, api_key: str, timeout: float = 30.0):
        self.api_key = api_key
        self.timeout = timeout

    async def translate(self, text, source_lang, target_lang, context=None) -> str:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self._URL,
                params={"key": self.api_key},
                json={"q": text, "source": source_lang, "target": target_lang, "format": "text"},
            )
            response.raise_for_status()
            return response.json()["data"]["translations"][0]["translatedText"]


class DeepLBackend(TranslationBackend):
    """DeepL Translation API."""

    def __init__(self, api_key: str, free_tier: bool = True, timeout: float = 30.0):
        self.api_key = api_key
        self.timeout = timeout
        base = "api-free.deepl.com" if free_tier else "api.deepl.com"
        self._url = f"https://{base}/v2/translate"

    async def translate(self, text, source_lang, target_lang, context=None) -> str:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self._url,
                headers={"Authorization": f"DeepL-Auth-Key {self.api_key}"},
                json={
                    "text": [text],
                    "source_lang": source_lang.upper(),
                    "target_lang": target_lang.upper(),
                },
            )
            response.raise_for_status()
            return response.json()["translations"][0]["text"]


class TranslationEngine:
    def __init__(self, config: TranslatorConfig, logger: TranslationLogger):
        self.config = config
        self.logger = logger
        self.context_manager = ContextManager(max_turns=config.max_context_turns)
        self._session_id: Optional[str] = None
        self._backend = self._build_backend()

    def _build_backend(self) -> TranslationBackend:
        if self.config.engine == EngineType.OPENAI:
            if not self.config.openai_api_key:
                raise ValueError("openai_api_key required for engine=openai")
            return OpenAICompatibleBackend(
                base_url=self.config.openai_base_url,
                api_key=self.config.openai_api_key,
                model=self.config.openai_model,
                logger=self.logger,
            )
        if self.config.engine == EngineType.GOOGLE:
            if not self.config.google_api_key:
                raise ValueError("google_api_key required for engine=google")
            return GoogleTranslateBackend(self.config.google_api_key)
        if self.config.engine == EngineType.DEEPL:
            if not self.config.deepl_api_key:
                raise ValueError("deepl_api_key required for engine=deepl")
            return DeepLBackend(self.config.deepl_api_key, self.config.deepl_free_tier)
        # EngineType.LOCAL
        return LMStudioBackend(
            base_url=self.config.local_model_url,
            model_name=self.config.local_model_name,
            logger=self.logger,
        )

    def set_session(self, session_id: str) -> None:
        self._session_id = session_id

    def get_context(self) -> list[dict[str, str]]:
        if self._session_id:
            return self.context_manager.get_context(self._session_id)
        return []

    def _record_turn(self, original: str, translated: str, direction: str) -> None:
        if self._session_id:
            self.context_manager.record_turn(self._session_id, original, translated, direction)

    async def ko_to_en(self, text: str, context: Optional[list] = None, preserve: bool = True) -> str:
        result = await self._translate(text, "ko", "en", context, preserve)
        self._record_turn(text, result, "ko-en")
        return result

    async def en_to_ko(self, text: str, context: Optional[list] = None, preserve: bool = True) -> str:
        result = await self._translate(text, "en", "ko", context, preserve)
        self._record_turn(text, result, "en-ko")
        return result

    async def ko_to_en_stream(self, text: str, context: Optional[list] = None) -> AsyncIterator[str]:
        async for chunk in self._translate_stream(text, "ko", "en", context):
            yield chunk

    async def en_to_ko_stream(self, text: str, context: Optional[list] = None) -> AsyncIterator[str]:
        async for chunk in self._translate_stream(text, "en", "ko", context):
            yield chunk

    async def _translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        context: Optional[list] = None,
        preserve: bool = True,
    ) -> str:
        preserve_result: Optional[PreservationResult] = None
        if preserve and self.config.preserve_code_blocks:
            preserve_result = preserve_code_blocks(text)
            text = preserve_result.processed_text

        try:
            result = await self._backend.translate(text, source_lang, target_lang, context)
        except Exception as err:
            self.logger.log_failure(text, "", f"{source_lang}->{target_lang}", err)
            if self.config.fail_mode == FailMode.CLOSED:
                raise TranslationError(f"Translation failed: {err}") from err
            result = text

        if preserve_result:
            result = restore_code_blocks(result, preserve_result.preserved)
        return result

    async def _translate_stream(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        context: Optional[list] = None,
    ) -> AsyncIterator[str]:
        preserve_result = None
        if self.config.preserve_code_blocks:
            preserve_result = preserve_code_blocks(text)
            text = preserve_result.processed_text

        try:
            async for chunk in self._backend.translate_stream(text, source_lang, target_lang, context):
                yield chunk
        except Exception as err:
            self.logger.log_failure(text, "", f"{source_lang}->{target_lang} (stream)", err)
            if self.config.fail_mode != FailMode.OPEN:
                raise TranslationError(f"Streaming translation failed: {err}") from err
            yield text


def create_engine(config: TranslatorConfig) -> tuple[TranslationEngine, TranslationLogger]:
    logger = get_logger(log_file=config.log_file if hasattr(config, "log_file") else "~/.ko-translate/failures.log")
    engine = TranslationEngine(config, logger)
    return engine, logger
