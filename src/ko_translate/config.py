"""Configuration for ko-translate-middleware.

Two separate concerns:
  [translator] — translation engine (Google / DeepL / local model)
  [llm]        — target chatbot/agent LLM being proxied
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class EngineType(str, Enum):
    LOCAL = "local"       # local LM Studio model
    OPENAI = "openai"     # any OpenAI-compatible API (separate from the proxied LLM)
    GOOGLE = "google"     # Google Cloud Translation API
    DEEPL = "deepl"       # DeepL API


class FailMode(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    CONFIGURABLE = "configurable"


class StreamingMode(str, Enum):
    BUFFERED = "buffered"
    STREAMING = "streaming"


class ContextMode(str, Enum):
    CONVERSATION_AWARE = "conversation-aware"
    TURN_BY_TURN = "turn-by-turn"


class OutputFormat(str, Enum):
    MIXED = "mixed-korean-english"
    PURE_KOREAN = "pure-korean"


class LogLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class TranslatorConfig:
    """Translation engine — kept strictly separate from the LLM being proxied."""

    engine: EngineType = EngineType.LOCAL

    # Local LM Studio translation model
    local_model_url: str = "http://127.0.0.1:1234"
    local_model_name: str = "gemma-4-korean-uncensored"

    # OpenAI-compatible API for translation (independent of the proxied LLM)
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"

    # Google Cloud Translation API
    google_api_key: Optional[str] = None

    # DeepL API
    deepl_api_key: Optional[str] = None
    deepl_free_tier: bool = True  # free tier uses api-free.deepl.com

    # Behavior
    fail_mode: FailMode = FailMode.OPEN
    korean_detection_mode: bool = True
    output_format: OutputFormat = OutputFormat.MIXED
    context_mode: ContextMode = ContextMode.CONVERSATION_AWARE
    max_context_turns: int = 10
    preserve_code_blocks: bool = True
    preserve_technical_terms: bool = True
    max_retries: int = 3
    retry_delay: float = 1.0


@dataclass
class LLMConfig:
    """Target chatbot / agent LLM that the proxy forwards requests to."""

    target_url: str = "https://api.openai.com/v1/chat/completions"
    api_key: Optional[str] = None
    timeout: float = 60.0


@dataclass
class AppConfig:
    translator: TranslatorConfig = field(default_factory=TranslatorConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)

    # HTTP server
    proxy_host: str = "127.0.0.1"
    proxy_port: int = 8080
    streaming_mode: StreamingMode = StreamingMode.STREAMING
    log_level: LogLevel = LogLevel.INFO
    log_file: str = "~/.ko-translate/failures.log"
    log_max_bytes: int = 10 * 1024 * 1024
    log_backup_count: int = 5

    @classmethod
    def from_file(cls, path: Path | str) -> AppConfig:
        path = Path(path).expanduser()
        if not path.exists():
            return cls()
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict) -> AppConfig:
        t = data.get("translator", {})
        lm = data.get("llm", {})

        translator = TranslatorConfig(
            engine=EngineType(t.get("engine", "local")),
            local_model_url=t.get("local_model_url", "http://127.0.0.1:1234"),
            local_model_name=t.get("local_model_name", "gemma-4-korean-uncensored"),
            openai_base_url=t.get("openai_base_url", "https://api.openai.com/v1"),
            openai_api_key=t.get("openai_api_key"),
            openai_model=t.get("openai_model", "gpt-4o-mini"),
            google_api_key=t.get("google_api_key"),
            deepl_api_key=t.get("deepl_api_key"),
            deepl_free_tier=t.get("deepl_free_tier", True),
            fail_mode=FailMode(t.get("fail_mode", "open")),
            korean_detection_mode=t.get("korean_detection_mode", True),
            output_format=OutputFormat(t.get("output_format", "mixed-korean-english")),
            context_mode=ContextMode(t.get("context_mode", "conversation-aware")),
            max_context_turns=t.get("max_context_turns", 10),
            preserve_code_blocks=t.get("preserve_code_blocks", True),
            preserve_technical_terms=t.get("preserve_technical_terms", True),
            max_retries=t.get("max_retries", 3),
            retry_delay=t.get("retry_delay", 1.0),
        )

        llm = LLMConfig(
            target_url=lm.get("target_url", "https://api.openai.com/v1/chat/completions"),
            api_key=lm.get("api_key"),
            timeout=lm.get("timeout", 60.0),
        )

        cfg = cls(translator=translator, llm=llm)
        cfg.proxy_host = data.get("proxy_host", cfg.proxy_host)
        cfg.proxy_port = data.get("proxy_port", cfg.proxy_port)
        if "streaming_mode" in data:
            cfg.streaming_mode = StreamingMode(data["streaming_mode"])
        if "log_level" in data:
            cfg.log_level = LogLevel(data["log_level"])
        cfg.log_file = data.get("log_file", cfg.log_file)
        cfg.log_max_bytes = data.get("log_max_bytes", cfg.log_max_bytes)
        cfg.log_backup_count = data.get("log_backup_count", cfg.log_backup_count)

        cfg._apply_env_overrides()
        return cfg

    def _apply_env_overrides(self) -> None:
        # Translator
        if v := os.environ.get("KO_TRANSLATE_ENGINE"):
            self.translator.engine = EngineType(v)
        if v := os.environ.get("KO_TRANSLATE_GOOGLE_API_KEY"):
            self.translator.google_api_key = v
        if v := os.environ.get("KO_TRANSLATE_DEEPL_API_KEY"):
            self.translator.deepl_api_key = v
        if v := os.environ.get("KO_TRANSLATE_LOCAL_MODEL_URL"):
            self.translator.local_model_url = v
        if v := os.environ.get("KO_TRANSLATE_LOCAL_MODEL_NAME"):
            self.translator.local_model_name = v
        if v := os.environ.get("KO_TRANSLATE_OPENAI_BASE_URL"):
            self.translator.openai_base_url = v
        if v := os.environ.get("KO_TRANSLATE_OPENAI_API_KEY"):
            self.translator.openai_api_key = v
        if v := os.environ.get("KO_TRANSLATE_OPENAI_MODEL"):
            self.translator.openai_model = v
        if v := os.environ.get("KO_TRANSLATE_KOREAN_DETECTION"):
            self.translator.korean_detection_mode = v.lower() == "true"
        if v := os.environ.get("KO_TRANSLATE_FAIL_MODE"):
            self.translator.fail_mode = FailMode(v)
        # LLM
        if v := os.environ.get("KO_TRANSLATE_TARGET_URL"):
            self.llm.target_url = v
        if v := os.environ.get("KO_TRANSLATE_LLM_API_KEY"):
            self.llm.api_key = v
        if v := os.environ.get("KO_TRANSLATE_LLM_TIMEOUT"):
            self.llm.timeout = float(v)
        # Server
        if v := os.environ.get("KO_TRANSLATE_PROXY_HOST"):
            self.proxy_host = v
        if v := os.environ.get("KO_TRANSLATE_PROXY_PORT"):
            self.proxy_port = int(v)
        if v := os.environ.get("KO_TRANSLATE_LOG_LEVEL"):
            self.log_level = LogLevel(v)

    @classmethod
    def load_default(cls) -> AppConfig:
        for path in [
            Path("~/.ko-translate/config.toml").expanduser(),
            Path("~/.config/ko-translate/config.toml").expanduser(),
            Path("/etc/ko-translate/config.toml"),
        ]:
            if path.exists():
                return cls.from_file(path)
        cfg = cls()
        cfg._apply_env_overrides()
        return cfg


# Backward-compat alias
TranslationConfig = AppConfig
