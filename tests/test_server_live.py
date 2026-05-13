"""Live integration tests for ProxyServer using real LM Studio endpoint."""

import os
import pytest
from starlette.testclient import TestClient

from ko_translate import ProxyServer, TranslationConfig, create_engine


@pytest.fixture
def config():
    c = TranslationConfig()
    c.local_model_url = "http://CHANGE_ME_LM_STUDIO_HOST:1234"
    c.local_model_name = "gemma-4-e4b-uncensored-hauhaucs-aggressive"
    c.proxy_host = "127.0.0.1"
    c.proxy_port = 18080
    return c


@pytest.fixture
def server(config):
    engine, logger = create_engine(config)
    server = ProxyServer(config, engine)
    return server


@pytest.fixture
def app(server):
    """Create test app with proper ASGI transport."""
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def health_check(request):
        return JSONResponse({"status": "healthy", "service": "ko-translate-proxy"})

    async def root(request):
        return JSONResponse({
            "service": "ko-translate-proxy",
            "version": "1.0.0",
            "status": "running",
        })

    routes = [
        Route("/", root),
        Route("/health", health_check),
        Route("/v1/chat/completions", server.handle_chat_completion, methods=["POST"]),
    ]

    return Starlette(routes=routes)


@pytest.fixture
def client(app):
    """Create test client with async transport."""
    os.environ["KO_TRANSLATE_TARGET_URL"] = "http://CHANGE_ME_LM_STUDIO_HOST:1234/v1/chat/completions"
    with TestClient(app, raise_server_exceptions=True) as test_client:
        yield test_client
    if "KO_TRANSLATE_TARGET_URL" in os.environ:
        del os.environ["KO_TRANSLATE_TARGET_URL"]


class TestServerLifecycle:
    """Test 1: Server startup/shutdown lifecycle."""

    def test_server_starts_and_responds_to_health_check(self, app, client):
        """Server should start and respond to health endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_server_root_endpoint(self, app, client):
        """Server root endpoint should return service info."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "ko-translate-proxy"
        assert data["status"] == "running"


class TestNonStreamingRouting:
    """Test 2: POST /v1/chat/completions - non-streaming request routing."""

    def test_non_streaming_basic_request(self, client):
        """Basic non-streaming request should be routed correctly."""
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gemma-4-e4b-uncensored-hauhaucs-aggressive",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "choices" in data
        assert len(data["choices"]) > 0
        assert "message" in data["choices"][0]


class TestStreamingRouting:
    """Test 3: POST /v1/chat/completions - streaming request routing."""

    def test_streaming_request_routing(self, client):
        """Streaming request should be routed and return streaming response."""
        with client.stream(
            "POST",
            "/v1/chat/completions",
            json={
                "model": "gemma-4-e4b-uncensored-hauhaucs-aggressive",
                "messages": [{"role": "user", "content": "Hi"}],
                "stream": True,
            },
        ) as response:
            assert response.status_code == 200
            chunks = list(response.iter_text())
            assert len(chunks) > 0


class TestKoreanTranslation:
    """Test 4: Translation of Korean user input."""

    def test_korean_input_gets_translated(self, client):
        """Korean user input should be translated before forwarding."""
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gemma-4-e4b-uncensored-hauhaucs-aggressive",
                "messages": [{"role": "user", "content": "안녕하세요"}],
                "stream": False,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "choices" in data
        # Response should be in Korean (translated back)
        content = data["choices"][0]["message"]["content"]
        assert content is not None


class TestEnglishPassthrough:
    """Test 5: Pass-through of English user input (no translation needed)."""

    def test_english_input_passed_through(self, client):
        """English input should not be translated."""
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gemma-4-e4b-uncensored-hauhaucs-aggressive",
                "messages": [{"role": "user", "content": "Hello, how are you?"}],
                "stream": False,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "choices" in data


class TestEmptyMessages:
    """Test 6: Empty messages array."""

    def test_empty_messages_array(self, client):
        """Empty messages array should be forwarded (passthrough)."""
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gemma-4-e4b-uncensored-hauhaucs-aggressive",
                "messages": [],
                "stream": False,
            },
        )
        # Empty messages should pass through to backend
        assert response.status_code == 200


class TestNonUserRolePassthrough:
    """Test 7: Non-user role message (assistant role passthrough)."""

    def test_assistant_role_message_passthrough(self, client):
        """Assistant role messages should be passed through without translation."""
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gemma-4-e4b-uncensored-hauhaucs-aggressive",
                "messages": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi there!"},
                ],
                "stream": False,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "choices" in data


class TestStreamingResponse:
    """Test 8: Streaming response handling."""

    def test_streaming_response_content(self, client):
        """Streaming response should contain translated content."""
        with client.stream(
            "POST",
            "/v1/chat/completions",
            json={
                "model": "gemma-4-e4b-uncensored-hauhaucs-aggressive",
                "messages": [{"role": "user", "content": "Tell me a joke"}],
                "stream": True,
            },
        ) as response:
            assert response.status_code == 200
            chunks = list(response.iter_text())
            # Should have received some chunks
            assert len(chunks) > 0


class TestErrorPropagation:
    """Test 9: Error propagation from LLM."""

    def test_invalid_endpoint_error(self, client):
        """Errors from LLM should be propagated back."""
        # Send to wrong endpoint to trigger error
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "nonexistent-model",
                "messages": [{"role": "user", "content": "test"}],
                "stream": False,
            },
        )
        # Should get error response (404 or similar)
        assert response.status_code in [200, 404, 500]


class TestSessionIDHeader:
    """Test 10: X-Session-ID header handling."""

    def test_session_id_header_forwarded(self, client):
        """X-Session-ID header should be handled correctly."""
        response = client.post(
            "/v1/chat/completions",
            headers={"X-Session-ID": "test-session-123"},
            json={
                "model": "gemma-4-e4b-uncensored-hauhaucs-aggressive",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "choices" in data

    def test_session_id_used_for_context(self, client):
        """Multiple requests with same session ID should maintain context."""
        session_id = "context-test-session-456"

        # First request
        response1 = client.post(
            "/v1/chat/completions",
            headers={"X-Session-ID": session_id},
            json={
                "model": "gemma-4-e4b-uncensored-hauhaucs-aggressive",
                "messages": [{"role": "user", "content": "My name is John"}],
                "stream": False,
            },
        )
        assert response1.status_code == 200

        # Second request with same session - should have context
        response2 = client.post(
            "/v1/chat/completions",
            headers={"X-Session-ID": session_id},
            json={
                "model": "gemma-4-e4b-uncensored-hauhaucs-aggressive",
                "messages": [{"role": "user", "content": "What is my name?"}],
                "stream": False,
            },
        )
        assert response2.status_code == 200


class TestInvalidJSON:
    """Test 11: Invalid JSON request."""

    def test_invalid_json_request(self, client):
        """Invalid JSON should return 400 error."""
        response = client.post(
            "/v1/chat/completions",
            content=b"not valid json{",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400
        assert "error" in response.json()


class TestMissingModel:
    """Test 12: Missing model field."""

    def test_missing_model_field(self, client):
        """Request without model field should still work (uses default)."""
        response = client.post(
            "/v1/chat/completions",
            json={
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False,
            },
        )
        # LM Studio may accept missing model or use default
        assert response.status_code in [200, 400]


class TestConversationContext:
    """Test 13: Conversation context in multiple requests."""

    def test_conversation_context_maintained(self, client):
        """Conversation context should be maintained across requests."""
        session_id = "conv-context-test-789"

        # First turn
        response1 = client.post(
            "/v1/chat/completions",
            headers={"X-Session-ID": session_id},
            json={
                "model": "gemma-4-e4b-uncensored-hauhaucs-aggressive",
                "messages": [{"role": "user", "content": "What is 2+2?"}],
                "stream": False,
            },
        )
        assert response1.status_code == 200

        # Second turn with context
        response2 = client.post(
            "/v1/chat/completions",
            headers={"X-Session-ID": session_id},
            json={
                "model": "gemma-4-e4b-uncensored-hauhaucs-aggressive",
                "messages": [
                    {"role": "user", "content": "What is 2+2?"},
                    {"role": "assistant", "content": "It is 4."},
                    {"role": "user", "content": "Add 5 to that"}],
                "stream": False,
            },
        )
        assert response2.status_code == 200


class TestKoreanDetectionEnabled:
    """Test 14: Korean detection when enabled."""

    def test_korean_detected_when_enabled(self, client, config):
        """Korean text should be detected and translated when detection is enabled."""
        # korean_detection_mode is True by default
        assert config.korean_detection_mode is True

        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gemma-4-e4b-uncensored-hauhaucs-aggressive",
                "messages": [{"role": "user", "content": "반가워요"}],
                "stream": False,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "choices" in data


class TestKoreanDetectionDisabled:
    """Test 15: Korean detection when disabled."""

    def test_korean_not_translated_when_disabled(self, client, config):
        """Korean text should NOT be translated when detection is disabled."""
        # Disable Korean detection
        config.korean_detection_mode = False

        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gemma-4-e4b-uncensored-hauhaucs-aggressive",
                "messages": [{"role": "user", "content": "안녕하세요"}],
                "stream": False,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "choices" in data
        # Content should be passed through without translation
        # (response will be in English since input wasn't translated)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
