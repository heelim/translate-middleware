"""Configuration management for ko-translate-middleware.

Supports TOML config file + environment variable override.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class EngineType(str, Enum):
    LOCAL = "local"
    OPENAI = "openai"
    GOOGLE = "google"
    DEEPL = "deepl"


class FailMode(str, Enum):
    OPEN = "open"  # Pass through untranslated on failure
    CLOSED = "closed"  # Return error on failure
    CONFIGURABLE = "configurable"  # Use fallback engine


class StreamingMode(str, Enum):
    BUFFERED = "buffered"  # Wait for complete response, then translate
    STREAMING = "streaming"  # Translate in real-time as chunks arrive
    BOTH = "both"  # User can choose per-request


class ContextMode(str, Enum):
    CONVERSATION_AWARE = "conversation-aware"  # Maintain full context
    TURN_BY_TURN = "turn-by-turn"  # Translate each turn independently


class OutputFormat(str, Enum):
    MIXED = "mixed-korean-english"  # Preserve English in mixed contexts
    PURE_KOREAN = "pure-korean"  # Translate everything to Korean


class LogLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class TranslationConfig:
    """Main configuration class for the translation middleware."""

    # Engine settings
    engine: EngineType = EngineType.LOCAL
    local_model_url: str = "http://127.0.0.1:1234"
    local_model_name: str = "gemma-4-korean-uncensored"
    openai_model: str = "gpt-4o-mini"
    openai_api_key: Optional[str] = None
    openai_base_url: str = "https://api.openai.com/v1"

    # Behavior settings
    fail_mode: FailMode = FailMode.OPEN
    streaming_mode: StreamingMode = StreamingMode.STREAMING
    context_mode: ContextMode = ContextMode.CONVERSATION_AWARE
    output_format: OutputFormat = OutputFormat.MIXED
    korean_detection_mode: bool = True  # Auto-detect Korean vs manual toggle

    # Logging settings
    log_level: LogLevel = LogLevel.INFO
    log_file: str = "~/.ko-translate/failures.log"
    log_max_bytes: int = 10 * 1024 * 1024  # 10MB
    log_backup_count: int = 5

    # Proxy settings
    proxy_host: str = "127.0.0.1"
    proxy_port: int = 8080
    proxy_timeout: float = 60.0

    # Context settings
    max_context_turns: int = 10
    preserve_code_blocks: bool = True
    preserve_technical_terms: bool = True

    # Retry settings
    max_retries: int = 3
    retry_delay: float = 1.0

    @classmethod
    def from_file(cls, path: Path | str) -> TranslationConfig:
        """Load configuration from a TOML file."""
        path = Path(path).expanduser()
        if not path.exists():
            return cls()

        with open(path, "rb") as f:
            data = tomllib.load(f)

        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict) -> TranslationConfig:
        """Create config from dictionary, respecting env overrides."""
        config_dict = {}

        # Map TOML keys to config fields
        field_mapping = {
            "engine": "engine",
            "local_model_url": "local_model_url",
            "local_model_name": "local_model_name",
            "openai_model": "openai_model",
            "openai_api_key": "openai_api_key",
            "openai_base_url": "openai_base_url",
            "fail_mode": "fail_mode",
            "streaming_mode": "streaming_mode",
            "context_mode": "context_mode",
            "output_format": "output_format",
            "korean_detection_mode": "korean_detection_mode",
            "log_level": "log_level",
            "log_file": "log_file",
            "log_max_bytes": "log_max_bytes",
            "log_backup_count": "log_backup_count",
            "proxy_host": "proxy_host",
            "proxy_port": "proxy_port",
            "proxy_timeout": "proxy_timeout",
            "max_context_turns": "max_context_turns",
            "preserve_code_blocks": "preserve_code_blocks",
            "preserve_technical_terms": "preserve_technical_terms",
            "max_retries": "max_retries",
            "retry_delay": "retry_delay",
        }

        for toml_key, field_name in field_mapping.items():
            if toml_key in data:
                config_dict[field_name] = data[toml_key]

        # Apply environment variable overrides
        config_dict = cls._apply_env_overrides(config_dict)

        return cls(**config_dict)

    @classmethod
    def _apply_env_overrides(cls, config_dict: dict) -> dict:
        """Apply environment variable overrides to config values."""
        env_mappings = {
            "KO_TRANSLATE_ENGINE": ("engine", lambda v: EngineType(v)),
            "KO_TRANSLATE_LOCAL_MODEL_URL": ("local_model_url", str),
            "KO_TRANSLATE_LOCAL_MODEL_NAME": ("local_model_name", str),
            "KO_TRANSLATE_OPENAI_MODEL": ("openai_model", str),
            "KO_TRANSLATE_OPENAI_API_KEY": ("openai_api_key", str),
            "KO_TRANSLATE_OPENAI_BASE_URL": ("openai_base_url", str),
            "KO_TRANSLATE_FAIL_MODE": ("fail_mode", lambda v: FailMode(v)),
            "KO_TRANSLATE_STREAMING_MODE": ("streaming_mode", lambda v: StreamingMode(v)),
            "KO_TRANSLATE_CONTEXT_MODE": ("context_mode", lambda v: ContextMode(v)),
            "KO_TRANSLATE_OUTPUT_FORMAT": ("output_format", lambda v: OutputFormat(v)),
            "KO_TRANSLATE_KOREAN_DETECTION": (
                "korean_detection_mode",
                lambda v: v.lower() == "true",
            ),
            "KO_TRANSLATE_LOG_LEVEL": ("log_level", lambda v: LogLevel(v)),
            "KO_TRANSLATE_LOG_FILE": ("log_file", str),
            "KO_TRANSLATE_PROXY_HOST": ("proxy_host", str),
            "KO_TRANSLATE_PROXY_PORT": ("proxy_port", int),
            "KO_TRANSLATE_MAX_CONTEXT_TURNS": ("max_context_turns", int),
        }

        for env_var, (field_name, converter) in env_mappings.items():
            value = os.environ.get(env_var)
            if value is not None:
                try:
                    config_dict[field_name] = converter(value)
                except (ValueError, TypeError):
                    pass  # Skip invalid env values

        return config_dict

    @classmethod
    def load_default(cls) -> TranslationConfig:
        """Load configuration from default locations."""
        search_paths = [
            Path("~/.ko-translate/config.toml").expanduser(),
            Path("~/.config/ko-translate/config.toml").expanduser(),
            Path("/etc/ko-translate/config.toml").expanduser(),
        ]

        for path in search_paths:
            if path.exists():
                return cls.from_file(path)

        return cls()

    def to_dict(self) -> dict:
        """Export configuration as dictionary."""
        result = {}
        for field_name, field_value in self.__dict__.items():
            if isinstance(field_value, Enum):
                result[field_name] = field_value.value
            else:
                result[field_name] = field_value
        return result
