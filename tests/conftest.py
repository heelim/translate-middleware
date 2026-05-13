"""Pytest configuration and shared fixtures for ko-translate-middleware tests."""

import sys
from pathlib import Path

import pytest

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


@pytest.fixture
def sample_korean_text():
    """Pure Korean text samples."""
    return "안녕하세요. 이것은 한국어 텍스트입니다."


@pytest.fixture
def sample_english_text():
    """Pure English text samples."""
    return "Hello. This is an English text."


@pytest.fixture
def sample_mixed_text():
    """Mixed Korean and English text."""
    return "Hello! 안녕하세요. This is mixed text. 이것도 됩니다."


@pytest.fixture
def sample_code_block():
    """Markdown code block sample."""
    return """
```python
def hello():
    print("Hello, World!")
```
"""


@pytest.fixture
def sample_inline_code():
    """Inline code samples."""
    return "Use `print()` function and `$variable` for output."


@pytest.fixture
def mock_logger():
    """Create a mock logger for engine tests."""
    from ko_translate.logging_config import TranslationLogger

    return TranslationLogger(name="test-logger", level="DEBUG")


@pytest.fixture
def mock_translation_config():
    """Create a mock translation config for testing."""
    from ko_translate.config import (
        EngineType,
        FailMode,
        LogLevel,
        StreamingMode,
        TranslationConfig,
    )

    return TranslationConfig(
        engine=EngineType.LOCAL,
        local_model_url="http://127.0.0.1:1234",
        local_model_name="test-model",
        fail_mode=FailMode.OPEN,
        streaming_mode=StreamingMode.STREAMING,
        log_level=LogLevel.INFO,
        max_retries=1,
        retry_delay=0.1,
    )
