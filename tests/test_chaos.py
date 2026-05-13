"""Chaos test infrastructure for ko-translate-middleware.

Tests fault tolerance and error handling for various failure scenarios
including network failures, malformed responses, and streaming interruptions.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx

from ko_translate.config import EngineType, FailMode, StreamingMode, TranslationConfig
from ko_translate.engine import (
    LMStudioBackend,
    TranslationEngine,
    TranslationError,
    create_engine,
)
from ko_translate.logging_config import TranslationLogger


def mock_lm_studio_timeout():
    """Raises httpx.TimeoutException."""
    raise httpx.TimeoutException("Connection timeout")


def mock_lm_studio_connection_refused():
    """Raises httpx.ConnectError."""
    raise httpx.ConnectError("Connection refused")


def mock_lm_studio_500():
    """Returns HTTP 500 response."""
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "Internal Server Error",
            request=MagicMock(),
            response=mock_response,
        )
    )
    return mock_response


def mock_lm_studio_503():
    """Returns HTTP 503 response."""
    mock_response = MagicMock()
    mock_response.status_code = 503
    mock_response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "Service Unavailable",
            request=MagicMock(),
            response=mock_response,
        )
    )
    return mock_response


def mock_lm_studio_malformed_json():
    """Returns non-JSON response."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
    return mock_response


def mock_lm_studio_empty_choices():
    """Returns valid JSON but empty choices."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"choices": []}
    return mock_response


def mock_lm_studio_missing_content():
    """Returns choice without message.content."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"role": "assistant"}}]
    }
    return mock_response


def mock_stream_interrupted():
    """Stream that terminates early."""

    class InterruptedStream:
        """Simulates a stream that gets interrupted during iteration."""

        def __init__(self):
            self.response = MagicMock()
            self.response.status_code = 200
            self.response.raise_for_status = MagicMock()

        async def stream(self, *args, **kwargs):
            yield "data: " + json.dumps(
                {"choices": [{"delta": {"content": "partial"}}]}
            )
            raise httpx.ReadTimeout("Stream interrupted")

        def aiter_lines(self):
            async def generator():
                yield "data: " + json.dumps(
                    {"choices": [{"delta": {"content": "partial"}}]}
                )
                raise httpx.ReadTimeout("Stream interrupted")

            return generator()

    return InterruptedStream()


class TestChaosBase:
    """Base class for chaos tests with shared fixtures."""

    @pytest.fixture
    def config(self):
        """Create a test configuration pointing to localhost:9999 (will be mocked)."""
        c = TranslationConfig()
        c.local_model_url = "http://localhost:9999"
        c.local_model_name = "test-model"
        c.fail_mode = FailMode.OPEN
        c.max_retries = 1
        c.retry_delay = 0.01
        return c

    @pytest.fixture
    def config_closed(self):
        """Configuration with fail_mode=CLOSED for error propagation tests."""
        c = TranslationConfig()
        c.local_model_url = "http://localhost:9999"
        c.local_model_name = "test-model"
        c.fail_mode = FailMode.CLOSED
        c.max_retries = 1
        c.retry_delay = 0.01
        return c

    @pytest.fixture
    def logger(self):
        """Create a test logger."""
        return TranslationLogger(name="test-chaos", level="ERROR")

    @pytest.fixture
    def lm_studio_backend(self, logger):
        """Create LM Studio backend for testing."""
        return LMStudioBackend(
            base_url="http://localhost:9999",
            model_name="test-model",
            logger=logger,
        )

    @pytest.fixture
    def engine_with_mock(self, config, logger):
        """Create engine with mock configuration."""
        engine, log = create_engine(config)
        return engine, log

    @pytest.fixture
    def engine_closed_fail_mode(self, config_closed, logger):
        """Create engine with CLOSED fail mode."""
        engine, log = create_engine(config_closed)
        return engine, log


class TestNetworkFailures(TestChaosBase):
    """Tests for network failure scenarios."""

    @pytest.mark.asyncio
    async def test_timeout_open_mode(self, lm_studio_backend, config):
        """When timeout occurs with fail_mode=OPEN, returns original text."""
        engine, _ = create_engine(config)

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.TimeoutException("Connection timeout")
            )

            result = await engine.ko_to_en("Hello")

        assert result == "Hello"

    @pytest.mark.asyncio
    async def test_timeout_closed_mode(self, config_closed):
        """When timeout occurs with fail_mode=CLOSED, raises TranslationError."""
        engine, _ = create_engine(config_closed)

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.TimeoutException("Connection timeout")
            )

            with pytest.raises(TranslationError):
                await engine.ko_to_en("Hello")

    @pytest.mark.asyncio
    async def test_connection_refused_open_mode(self, lm_studio_backend, config):
        """When connection refused with fail_mode=OPEN, returns original text."""
        engine, _ = create_engine(config)

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )

            result = await engine.ko_to_en("Hello")

        assert result == "Hello"

    @pytest.mark.asyncio
    async def test_connection_refused_closed_mode(self, config_closed):
        """When connection refused with fail_mode=CLOSED, raises TranslationError."""
        engine, _ = create_engine(config_closed)

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )

            with pytest.raises(TranslationError):
                await engine.ko_to_en("Hello")

    @pytest.mark.asyncio
    async def test_500_error_open_mode(self, config):
        """When 500 error occurs with fail_mode=OPEN, returns original text."""
        engine, _ = create_engine(config)

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = mock_lm_studio_500()
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await engine.ko_to_en("Hello")

        assert result == "Hello"

    @pytest.mark.asyncio
    async def test_500_error_closed_mode(self, config_closed):
        """When 500 error occurs with fail_mode=CLOSED, raises TranslationError."""
        engine, _ = create_engine(config_closed)

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = mock_lm_studio_500()
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            with pytest.raises(TranslationError):
                await engine.ko_to_en("Hello")

    @pytest.mark.asyncio
    async def test_503_error_open_mode(self, config):
        """When 503 error occurs with fail_mode=OPEN, returns original text."""
        engine, _ = create_engine(config)

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = mock_lm_studio_503()
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await engine.ko_to_en("Hello")

        assert result == "Hello"

    @pytest.mark.asyncio
    async def test_503_error_closed_mode(self, config_closed):
        """When 503 error occurs with fail_mode=CLOSED, raises TranslationError."""
        engine, _ = create_engine(config_closed)

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = mock_lm_studio_503()
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            with pytest.raises(TranslationError):
                await engine.ko_to_en("Hello")


class TestMalformedResponses(TestChaosBase):
    """Tests for malformed response scenarios."""

    @pytest.mark.asyncio
    async def test_malformed_json_open_mode(self, config):
        """When JSON is malformed with fail_mode=OPEN, returns original text."""
        engine, _ = create_engine(config)

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = mock_lm_studio_malformed_json()
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await engine.ko_to_en("Hello")

        assert result == "Hello"

    @pytest.mark.asyncio
    async def test_malformed_json_closed_mode(self, config_closed):
        """When JSON is malformed with fail_mode=CLOSED, raises TranslationError."""
        engine, _ = create_engine(config_closed)

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = mock_lm_studio_malformed_json()
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            with pytest.raises(TranslationError):
                await engine.ko_to_en("Hello")

    @pytest.mark.asyncio
    async def test_empty_choices_open_mode(self, config):
        """When choices array is empty with fail_mode=OPEN, returns original text."""
        engine, _ = create_engine(config)

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = mock_lm_studio_empty_choices()
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await engine.ko_to_en("Hello")

        assert result == "Hello"

    @pytest.mark.asyncio
    async def test_empty_choices_closed_mode(self, config_closed):
        """When choices array is empty with fail_mode=CLOSED, raises TranslationError."""
        engine, _ = create_engine(config_closed)

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = mock_lm_studio_empty_choices()
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            with pytest.raises(TranslationError):
                await engine.ko_to_en("Hello")

    @pytest.mark.asyncio
    async def test_missing_content_open_mode(self, config):
        """When content is missing with fail_mode=OPEN, returns original text."""
        engine, _ = create_engine(config)

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = mock_lm_studio_missing_content()
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await engine.ko_to_en("Hello")

        assert result == "Hello"

    @pytest.mark.asyncio
    async def test_missing_content_closed_mode(self, config_closed):
        """When content is missing with fail_mode=CLOSED, raises TranslationError."""
        engine, _ = create_engine(config_closed)

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = mock_lm_studio_missing_content()
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            with pytest.raises(TranslationError):
                await engine.ko_to_en("Hello")


class TestStreamingChaos(TestChaosBase):
    """Tests for streaming interruption scenarios."""

    @pytest.mark.asyncio
    async def test_stream_interrupted_open_mode(self, config):
        """When stream is interrupted with fail_mode=OPEN, returns original text."""
        engine, _ = create_engine(config)

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.stream = MagicMock(
                side_effect=httpx.ReadTimeout("Stream interrupted")
            )

            result = engine.translate_stream_ko_to_en("Hello")
            chunks = []
            async for chunk in result:
                chunks.append(chunk)

        assert "Hello" in chunks

    @pytest.mark.asyncio
    async def test_stream_interrupted_closed_mode(self, config_closed):
        """When stream is interrupted with fail_mode=CLOSED, raises TranslationError."""
        engine, _ = create_engine(config_closed)

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.stream = MagicMock(
                side_effect=httpx.ReadTimeout("Stream interrupted")
            )

            with pytest.raises(TranslationError):
                result = engine.translate_stream_ko_to_en("Hello")
                async for _ in result:
                    pass

    @pytest.mark.asyncio
    async def test_stream_partial_response_open_mode(self, config):
        """When stream returns partial content then fails, returns what was received + original."""
        engine, _ = create_engine(config)

        async def mock_stream(*args, **kwargs):
            yield "data: " + json.dumps(
                {"choices": [{"delta": {"content": "partial"}}]}
            )
            # Stream interrupted after partial response
            raise httpx.ReadTimeout("Stream interrupted")

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.stream = mock_stream

            result = engine.translate_stream_ko_to_en("Hello")
            chunks = []
            async for chunk in result:
                chunks.append(chunk)

        # In open mode with interrupted stream, it yields original text
        assert "Hello" in chunks or chunks == ["Hello"]


class TestFailModeBehavior(TestChaosBase):
    """Explicit tests for fail mode behavior differences."""

    @pytest.mark.asyncio
    async def test_fail_mode_open_returns_original_on_network_error(self, config):
        """fail_mode=OPEN should return original text on network errors."""
        engine, _ = create_engine(config)
        original_text = "안녕하세요"

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.TimeoutException("timeout")
            )

            result = await engine.ko_to_en(original_text)

        assert result == original_text

    @pytest.mark.asyncio
    async def test_fail_mode_closed_raises_on_network_error(self, config_closed):
        """fail_mode=CLOSED should raise TranslationError on network errors."""
        engine, _ = create_engine(config_closed)
        original_text = "안녕하세요"

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=httpx.TimeoutException("timeout")
            )

            with pytest.raises(TranslationError) as exc_info:
                await engine.ko_to_en(original_text)

            assert "timeout" in str(exc_info.value).lower() or "TranslationError" in str(type(exc_info.value))

    @pytest.mark.asyncio
    async def test_fail_mode_open_returns_original_on_bad_response(self, config):
        """fail_mode=OPEN should return original text on malformed/bad responses."""
        engine, _ = create_engine(config)
        original_text = "안녕하세요"

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = mock_lm_studio_empty_choices()
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await engine.ko_to_en(original_text)

        assert result == original_text

    @pytest.mark.asyncio
    async def test_fail_mode_closed_raises_on_bad_response(self, config_closed):
        """fail_mode=CLOSED should raise TranslationError on malformed/bad responses."""
        engine, _ = create_engine(config_closed)
        original_text = "안녕하세요"

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = mock_lm_studio_empty_choices()
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            with pytest.raises(TranslationError):
                await engine.ko_to_en(original_text)

    @pytest.mark.asyncio
    async def test_fail_mode_open_streaming_yields_original_on_error(self, config):
        """fail_mode=OPEN streaming should yield original text on errors."""
        engine, _ = create_engine(config)
        original_text = "안녕하세요"

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.stream = MagicMock(
                side_effect=httpx.ReadTimeout("stream timeout")
            )

            result = engine.translate_stream_ko_to_en(original_text)
            chunks = []
            async for chunk in result:
                chunks.append(chunk)

        assert original_text in chunks

    @pytest.mark.asyncio
    async def test_fail_mode_closed_streaming_raises_on_error(self, config_closed):
        """fail_mode=CLOSED streaming should raise TranslationError on errors."""
        engine, _ = create_engine(config_closed)
        original_text = "안녕하세요"

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.stream = MagicMock(
                side_effect=httpx.ReadTimeout("stream timeout")
            )

            result = engine.translate_stream_ko_to_en(original_text)
            with pytest.raises(TranslationError):
                async for _ in result:
                    pass


CHAOS_HELPERS = {
    "mock_lm_studio_timeout": mock_lm_studio_timeout,
    "mock_lm_studio_connection_refused": mock_lm_studio_connection_refused,
    "mock_lm_studio_500": mock_lm_studio_500,
    "mock_lm_studio_503": mock_lm_studio_503,
    "mock_lm_studio_malformed_json": mock_lm_studio_malformed_json,
    "mock_lm_studio_empty_choices": mock_lm_studio_empty_choices,
    "mock_lm_studio_missing_content": mock_lm_studio_missing_content,
    "mock_stream_interrupted": mock_stream_interrupted,
}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
