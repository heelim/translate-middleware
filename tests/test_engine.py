"""Tests for engine module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx
from ko_translate.config import EngineType, FailMode, StreamingMode, TranslationConfig
from ko_translate.engine import (
    LMStudioBackend,
    OpenAIBackend,
    TranslationEngine,
    TranslationError,
    create_engine,
)
from ko_translate.logging_config import TranslationLogger


@pytest.fixture
def logger():
    return TranslationLogger(name="test", level="ERROR")


@pytest.fixture
def lm_studio_backend(logger):
    return LMStudioBackend(
        base_url="http://localhost:1234",
        model_name="test-model",
        logger=logger,
    )


@pytest.fixture
def openai_backend(logger):
    return OpenAIBackend(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        model="gpt-4",
        logger=logger,
    )


class TestLMStudioBackend:
    @pytest.mark.asyncio
    async def test_translate_success(self, lm_studio_backend):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "안녕하세요"}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            result = await lm_studio_backend.translate("Hello", "English", "Korean")

        assert result == "안녕하세요"

    @pytest.mark.asyncio
    async def test_translate_with_context(self, lm_studio_backend):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "translated"}}]
        }

        context = [
            {"original": "Hello", "translated": "안녕하세요"},
            {"original": "How are you?", "translated": "어떻게 지내세요?"},
        ]

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            await lm_studio_backend.translate("Good", "English", "Korean", context)

            call_args = mock_client.return_value.__aenter__.return_value.post.call_args
            messages = call_args.kwargs["json"]["messages"]

            assert len(messages) == 6
            assert messages[0]["role"] == "system"
            assert any(m["content"] == "Hello" for m in messages)
            assert any(m["content"] == "안녕하세요" for m in messages)

    @pytest.mark.asyncio
    async def test_translate_error_raises(self, lm_studio_backend):
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.HTTPError("Connection failed")
            )

            with pytest.raises(httpx.HTTPError):
                await lm_studio_backend.translate("Hello", "English", "Korean")


class TestOpenAIBackend:
    @pytest.mark.asyncio
    async def test_translate_success(self, openai_backend):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "안녕하세요"}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            result = await openai_backend.translate("Hello", "English", "Korean")

        assert result == "안녕하세요"

    @pytest.mark.asyncio
    async def test_translate_includes_auth_header(self, openai_backend):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "translated"}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            await openai_backend.translate("Hello", "English", "Korean")

            call_args = mock_client.return_value.__aenter__.return_value.post.call_args
            headers = call_args.kwargs.get("headers", {})
            assert "Authorization" in headers
            assert headers["Authorization"] == "Bearer test-key"


class TestBuildMessages:
    def test_lm_studio_builds_system_prompt(self, lm_studio_backend):
        messages = lm_studio_backend._build_messages(
            "Hello", "English", "Korean", None
        )

        assert messages[0]["role"] == "system"
        assert "English" in messages[0]["content"]
        assert "Korean" in messages[0]["content"]

    def test_lm_studio_adds_context_turns(self, lm_studio_backend):
        context = [
            {"original": "Hi", "translated": "안녕"},
        ]
        messages = lm_studio_backend._build_messages("Hello", "English", "Korean", context)

        assert len(messages) == 4
        assert messages[1]["content"] == "Hi"
        assert messages[2]["content"] == "안녕"
        assert messages[3]["content"] == "Hello"

    def test_lm_studio_adds_user_text_last(self, lm_studio_backend):
        messages = lm_studio_backend._build_messages(
            "Hello world", "English", "Korean", None
        )

        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "Hello world"

    def test_lm_studio_respects_context_limit(self, lm_studio_backend):
        context = [
            {"original": f"text{i}", "translated": f"번역{i}"}
            for i in range(10)
        ]
        messages = lm_studio_backend._build_messages("Hello", "English", "Korean", context)

        user_messages = [m for m in messages if m["role"] == "user"]
        assert len(user_messages) == 6


class TestTranslationEngine:
    @pytest.mark.asyncio
    async def test_ko_to_en_calls_primary_backend(self, mock_translation_config, logger):
        engine = TranslationEngine(mock_translation_config, logger)
        engine.primary_backend = AsyncMock()
        engine.primary_backend.translate.return_value = "Hello"

        result = await engine.ko_to_en("안녕하세요")

        assert result == "Hello"
        engine.primary_backend.translate.assert_called_once()

    @pytest.mark.asyncio
    async def test_en_to_ko_calls_primary_backend(self, mock_translation_config, logger):
        engine = TranslationEngine(mock_translation_config, logger)
        engine.primary_backend = AsyncMock()
        engine.primary_backend.translate.return_value = "안녕하세요"

        result = await engine.en_to_ko("Hello")

        assert result == "안녕하세요"
        engine.primary_backend.translate.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_on_primary_failure(self, mock_translation_config, logger):
        mock_translation_config.fail_mode = FailMode.CONFIGURABLE
        engine = TranslationEngine(mock_translation_config, logger)

        engine.primary_backend = AsyncMock()
        engine.primary_backend.translate.side_effect = Exception("Primary failed")
        engine.fallback_backend = AsyncMock()
        engine.fallback_backend.translate.return_value = "fallback result"

        result = await engine.ko_to_en("안녕하세요")

        assert result == "fallback result"
        engine.fallback_backend.translate.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_original_on_open_fail(self, mock_translation_config, logger):
        mock_translation_config.fail_mode = FailMode.OPEN
        engine = TranslationEngine(mock_translation_config, logger)

        engine.primary_backend = AsyncMock()
        engine.primary_backend.translate.side_effect = Exception("Failed")

        result = await engine.ko_to_en("안녕하세요")

        assert result == "안녕하세요"

    @pytest.mark.asyncio
    async def test_raises_on_closed_fail(self, mock_translation_config, logger):
        mock_translation_config.fail_mode = FailMode.CLOSED
        engine = TranslationEngine(mock_translation_config, logger)

        engine.primary_backend = AsyncMock()
        engine.primary_backend.translate.side_effect = Exception("Failed")

        with pytest.raises(TranslationError):
            await engine.ko_to_en("안녕하세요")

    @pytest.mark.asyncio
    async def test_preserve_and_restore_code_blocks(
        self, mock_translation_config, logger
    ):
        mock_translation_config.preserve_code_blocks = True
        engine = TranslationEngine(mock_translation_config, logger)
        engine.primary_backend = AsyncMock()
        engine.primary_backend.translate.return_value = "translated `code`"

        result = await engine.ko_to_en("안녕하세요 `code`")

        assert "`code`" in result


class TestCreateEngine:
    def test_creates_engine_with_local_backend(self):
        config = TranslationConfig(engine=EngineType.LOCAL)
        engine, logger = create_engine(config)

        assert isinstance(engine, TranslationEngine)
        assert isinstance(logger, TranslationLogger)
        assert isinstance(engine.primary_backend, LMStudioBackend)

    def test_creates_engine_with_openai_backend(self):
        config = TranslationConfig(
            engine=EngineType.OPENAI,
            openai_api_key="test-key",
        )
        engine, logger = create_engine(config)

        assert isinstance(engine, TranslationEngine)
        assert isinstance(engine.primary_backend, OpenAIBackend)
