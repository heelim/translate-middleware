"""Tests for config module."""

import os
import tempfile
from pathlib import Path

import pytest
from ko_translate.config import (
    ContextMode,
    EngineType,
    FailMode,
    LogLevel,
    OutputFormat,
    StreamingMode,
    TranslationConfig,
)


class TestLoadDefault:
    def test_returns_default_config_when_no_file(self, monkeypatch):
        monkeypatch.delenv("KO_TRANSLATE_ENGINE", raising=False)
        config = TranslationConfig.load_default()
        assert isinstance(config, TranslationConfig)
        assert config.engine == EngineType.LOCAL

    def test_loads_from_first_existing_path(self, monkeypatch, tmp_path):
        config_dir = tmp_path / ".ko-translate"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text('engine = "openai"')

        monkeypatch.setenv("HOME", str(tmp_path))

        config = TranslationConfig.from_file(config_file)
        assert config.engine == EngineType.OPENAI


class TestFromFile:
    def test_loads_toml_config(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text("""
engine = "openai"
local_model_url = "http://custom:1234"
openai_model = "gpt-4"
fail_mode = "closed"
streaming_mode = "buffered"
output_format = "pure-korean"
""")

        config = TranslationConfig.from_file(config_file)

        assert config.engine == EngineType.OPENAI
        assert config.local_model_url == "http://custom:1234"
        assert config.openai_model == "gpt-4"
        assert config.fail_mode == FailMode.CLOSED
        assert config.streaming_mode == StreamingMode.BUFFERED
        assert config.output_format == OutputFormat.PURE_KOREAN

    def test_file_not_found_returns_default(self, tmp_path):
        config = TranslationConfig.from_file(tmp_path / "nonexistent.toml")
        assert config.engine == EngineType.LOCAL

    def test_partial_config_uses_defaults(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text("""
engine = "openai"
""")

        config = TranslationConfig.from_file(config_file)

        assert config.engine == EngineType.OPENAI
        assert config.local_model_url == "http://127.0.0.1:1234"

    def test_log_settings_loaded(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text("""
log_level = "debug"
log_file = "/tmp/test.log"
log_max_bytes = 5242880
log_backup_count = 3
""")

        config = TranslationConfig.from_file(config_file)

        assert config.log_level == LogLevel.DEBUG
        assert config.log_file == "/tmp/test.log"
        assert config.log_max_bytes == 5242880
        assert config.log_backup_count == 3


class TestEnvironmentOverrides:
    def test_engine_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("KO_TRANSLATE_ENGINE", "openai")
        config_file = tmp_path / "config.toml"
        config_file.write_text("")
        config = TranslationConfig.from_file(config_file)
        assert config.engine == EngineType.OPENAI

    def test_local_model_url_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("KO_TRANSLATE_LOCAL_MODEL_URL", "http://custom:9999")
        config_file = tmp_path / "config.toml"
        config_file.write_text("")
        config = TranslationConfig.from_file(config_file)
        assert config.local_model_url == "http://custom:9999"

    def test_local_model_name_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("KO_TRANSLATE_LOCAL_MODEL_NAME", "custom-model")
        config_file = tmp_path / "config.toml"
        config_file.write_text("")
        config = TranslationConfig.from_file(config_file)
        assert config.local_model_name == "custom-model"

    def test_openai_model_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("KO_TRANSLATE_OPENAI_MODEL", "gpt-5")
        config_file = tmp_path / "config.toml"
        config_file.write_text("")
        config = TranslationConfig.from_file(config_file)
        assert config.openai_model == "gpt-5"

    def test_openai_api_key_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("KO_TRANSLATE_OPENAI_API_KEY", "sk-test123")
        config_file = tmp_path / "config.toml"
        config_file.write_text("")
        config = TranslationConfig.from_file(config_file)
        assert config.openai_api_key == "sk-test123"

    def test_openai_base_url_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("KO_TRANSLATE_OPENAI_BASE_URL", "https://custom.api.com/v1")
        config_file = tmp_path / "config.toml"
        config_file.write_text("")
        config = TranslationConfig.from_file(config_file)
        assert config.openai_base_url == "https://custom.api.com/v1"

    def test_fail_mode_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("KO_TRANSLATE_FAIL_MODE", "closed")
        config_file = tmp_path / "config.toml"
        config_file.write_text("")
        config = TranslationConfig.from_file(config_file)
        assert config.fail_mode == FailMode.CLOSED

    def test_streaming_mode_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("KO_TRANSLATE_STREAMING_MODE", "buffered")
        config_file = tmp_path / "config.toml"
        config_file.write_text("")
        config = TranslationConfig.from_file(config_file)
        assert config.streaming_mode == StreamingMode.BUFFERED

    def test_context_mode_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("KO_TRANSLATE_CONTEXT_MODE", "turn-by-turn")
        config_file = tmp_path / "config.toml"
        config_file.write_text("")
        config = TranslationConfig.from_file(config_file)
        assert config.context_mode == ContextMode.TURN_BY_TURN

    def test_output_format_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("KO_TRANSLATE_OUTPUT_FORMAT", "pure-korean")
        config_file = tmp_path / "config.toml"
        config_file.write_text("")
        config = TranslationConfig.from_file(config_file)
        assert config.output_format == OutputFormat.PURE_KOREAN

    def test_korean_detection_override_true(self, monkeypatch, tmp_path):
        monkeypatch.setenv("KO_TRANSLATE_KOREAN_DETECTION", "true")
        config_file = tmp_path / "config.toml"
        config_file.write_text("")
        config = TranslationConfig.from_file(config_file)
        assert config.korean_detection_mode is True

    def test_korean_detection_override_false(self, monkeypatch, tmp_path):
        monkeypatch.setenv("KO_TRANSLATE_KOREAN_DETECTION", "false")
        config_file = tmp_path / "config.toml"
        config_file.write_text("")
        config = TranslationConfig.from_file(config_file)
        assert config.korean_detection_mode is False

    def test_log_level_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("KO_TRANSLATE_LOG_LEVEL", "warning")
        config_file = tmp_path / "config.toml"
        config_file.write_text("")
        config = TranslationConfig.from_file(config_file)
        assert config.log_level == LogLevel.WARNING

    def test_proxy_host_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("KO_TRANSLATE_PROXY_HOST", "CHANGE_ME_PROXY_HOST")
        config_file = tmp_path / "config.toml"
        config_file.write_text("")
        config = TranslationConfig.from_file(config_file)
        assert config.proxy_host == "CHANGE_ME_PROXY_HOST"

    def test_proxy_port_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("KO_TRANSLATE_PROXY_PORT", "8888")
        config_file = tmp_path / "config.toml"
        config_file.write_text("")
        config = TranslationConfig.from_file(config_file)
        assert config.proxy_port == 8888

    def test_max_context_turns_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("KO_TRANSLATE_MAX_CONTEXT_TURNS", "20")
        config_file = tmp_path / "config.toml"
        config_file.write_text("")
        config = TranslationConfig.from_file(config_file)
        assert config.max_context_turns == 20

    def test_invalid_enum_value_ignored(self, monkeypatch, tmp_path):
        monkeypatch.setenv("KO_TRANSLATE_ENGINE", "invalid_engine")
        config_file = tmp_path / "config.toml"
        config_file.write_text("")
        config = TranslationConfig.from_file(config_file)
        assert config.engine == EngineType.LOCAL

    def test_env_overrides_file(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.toml"
        config_file.write_text('engine = "openai"')
        monkeypatch.setenv("KO_TRANSLATE_ENGINE", "local")

        config = TranslationConfig.from_file(config_file)
        assert config.engine == EngineType.LOCAL


class TestToDict:
    def test_converts_enum_values(self):
        config = TranslationConfig(
            engine=EngineType.OPENAI,
            fail_mode=FailMode.CLOSED,
        )
        d = config.to_dict()

        assert d["engine"] == "openai"
        assert d["fail_mode"] == "closed"

    def test_converts_string_values(self):
        config = TranslationConfig(local_model_url="http://test:1234")
        d = config.to_dict()

        assert d["local_model_url"] == "http://test:1234"


class TestDefaults:
    def test_default_engine_is_local(self):
        config = TranslationConfig()
        assert config.engine == EngineType.LOCAL

    def test_default_fail_mode_is_open(self):
        config = TranslationConfig()
        assert config.fail_mode == FailMode.OPEN

    def test_default_streaming_mode(self):
        config = TranslationConfig()
        assert config.streaming_mode == StreamingMode.STREAMING

    def test_default_context_mode(self):
        config = TranslationConfig()
        assert config.context_mode == ContextMode.CONVERSATION_AWARE

    def test_default_output_format(self):
        config = TranslationConfig()
        assert config.output_format == OutputFormat.MIXED

    def test_default_ports(self):
        config = TranslationConfig()
        assert config.proxy_port == 8080
        assert config.proxy_host == "127.0.0.1"
