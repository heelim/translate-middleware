"""Standalone proxy server using Starlette."""

from __future__ import annotations

import argparse
import json
import time
from typing import Any

import httpx

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route
from sse_starlette.sse import EventSourceResponse

from .config import AppConfig
from .context import ContextManager
from .engine import TranslationEngine
from .korean_detector import contains_korean
from .logging_config import get_logger


class ProxyServer:
    def __init__(self, config: AppConfig, engine: TranslationEngine):
        self.config = config
        self.engine = engine
        self.logger = get_logger(
            log_file=config.log_file,
            level=config.log_level.value,
        )
        self.context_manager = ContextManager(max_turns=config.translator.max_context_turns)
        self._start_time = time.time()
        self._metrics = {"requests": 0, "errors": {}, "latencies": []}

    async def handle_chat_completion(self, request: Request) -> Response:
        self._metrics["requests"] += 1
        start_time = time.time()

        body = await request.body()
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._track_error("json_decode_error")
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)

        session_id = request.headers.get("X-Session-ID", "")
        messages = data.get("messages", [])

        if not messages:
            response_data, _ = await self._forward_request(data, request)
            return JSONResponse(response_data)

        last_message = messages[-1]
        if last_message.get("role") != "user":
            response_data, _ = await self._forward_request(data, request)
            return JSONResponse(response_data)

        user_content = last_message.get("content", "")
        if not isinstance(user_content, str):
            response_data, _ = await self._forward_request(data, request)
            return JSONResponse(response_data)

        needs_translation = self.config.translator.korean_detection_mode and contains_korean(user_content)

        original_content = user_content
        context = self.context_manager.get_context(session_id) if session_id else []

        if needs_translation:
            self.logger.info(f"Translating user input ({len(user_content)} chars)")
            try:
                translated = await self.engine.ko_to_en(user_content, context)
                last_message["content"] = translated
                self.logger.info(f"Translation complete ({len(translated)} chars)")
                self._metrics["latencies"].append((time.time() - start_time) * 1000)
            except Exception as e:
                self.logger.error(f"Translation failed: {e}")
                self._track_error("translation_error")
                if self.config.translator.fail_mode.value == "closed":
                    return JSONResponse({"error": str(e)}, status_code=500)

        is_streaming = data.get("stream", False)

        if is_streaming:
            return await self._handle_streaming(data, request, session_id, original_content)
        else:
            return await self._handle_buffered(data, request, session_id, original_content)

    def _track_error(self, error_type: str) -> None:
        if error_type not in self._metrics["errors"]:
            self._metrics["errors"][error_type] = 0
        self._metrics["errors"][error_type] += 1

    async def _handle_buffered(
        self,
        data: dict[str, Any],
        request: Request,
        session_id: str,
        original_content: str,
    ) -> Response:
        response_data, session_id = await self._forward_request(data, request)

        if session_id and original_content and "choices" in response_data:
            choice = response_data["choices"][0]
            if "message" in choice:
                assistant_content = choice["message"].get("content", "")
                if assistant_content:
                    context = self.context_manager.get_context(session_id)
                    try:
                        translated = await self.engine.en_to_ko(assistant_content, context)
                        choice["message"]["content"] = translated
                        self.context_manager.record_turn(
                            session_id,
                            original=original_content,
                            translated=translated,
                            direction="ko->en->ko",
                        )
                    except Exception as e:
                        self.logger.error(f"Response translation failed: {e}")

        return JSONResponse(response_data)

    async def _handle_streaming(
        self,
        data: dict[str, Any],
        request: Request,
        session_id: str,
        original_content: str,
    ) -> StreamingResponse:
        async def event_generator():
            context = self.context_manager.get_context(session_id) if session_id else []
            buffer = ""

            try:
                async for chunk in self._stream_request(data, request):
                    if chunk.startswith("data: "):
                        if chunk.strip() == "data: [DONE]":
                            yield {"event": "message", "data": "[DONE]"}
                            break

                        try:
                            json_str = chunk[6:]
                            chunk_data = json.loads(json_str)

                            if "choices" in chunk_data and chunk_data["choices"]:
                                delta = chunk_data["choices"][0].get("delta", {})
                                if "content" in delta:
                                    buffer += delta["content"]
                                    yield {"event": "message", "data": chunk}

                            else:
                                yield {"event": "message", "data": chunk}

                        except json.JSONDecodeError:
                            yield {"event": "message", "data": chunk}
                    else:
                        yield {"event": "message", "data": chunk}

                if buffer and session_id:
                    try:
                        translated = await self.engine.en_to_ko(buffer, context)
                        self.context_manager.record_turn(
                            session_id,
                            original=original_content,
                            translated=translated,
                            direction="ko->en->ko",
                        )
                    except Exception as e:
                        self.logger.error(f"Streaming response translation failed: {e}")

            except Exception as e:
                self.logger.error(f"Streaming error: {e}")
                yield {"event": "error", "data": str(e)}

        return EventSourceResponse(event_generator())

    async def _forward_request(
        self,
        data: dict[str, Any],
        request: Request,
    ) -> tuple[dict[str, Any], str]:
        session_id = request.headers.get("X-Session-ID", "")

        headers = {}
        for key, value in request.headers.items():
            if key.lower() not in ("host", "content-length", "authorization"):
                headers[key] = value
        if self.config.llm.api_key:
            headers["Authorization"] = f"Bearer {self.config.llm.api_key}"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.config.llm.target_url,
                json=data,
                headers=headers,
                timeout=self.config.llm.timeout,
            )
            response_data = response.json()

        return response_data, session_id

    async def _check_lm_studio_connected(self) -> bool:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(self.config.local_model_url)
                return response.status_code == 200
        except Exception:
            return False

    async def handle_health(self, request: Request) -> Response:
        lm_connected = await self._check_lm_studio_connected()
        uptime = time.time() - self._start_time
        return JSONResponse({
            "status": "ok",
            "lm_studio_connected": lm_connected,
            "uptime_seconds": uptime,
        })

    async def handle_metrics(self, request: Request) -> Response:
        latencies = self._metrics["latencies"]
        latencies.sort()
        count = len(latencies)

        def percentile(p: float) -> float:
            if count == 0:
                return 0.0
            idx = int(count * p)
            idx = min(idx, count - 1)
            return latencies[idx]

        p50 = percentile(0.50)
        p95 = percentile(0.95)
        p99 = percentile(0.99)

        total_requests = self._metrics["requests"]

        lines = [
            "# HELP request_count_total Total number of translation requests",
            "# TYPE request_count_total counter",
            f"request_count_total {total_requests}",
            "",
            "# HELP translation_latency_ms Translation latency in milliseconds",
            "# TYPE translation_latency_ms gauge",
            f"translation_latency_ms{{quantile=\"0.5\"}} {p50:.2f}",
            f"translation_latency_ms{{quantile=\"0.95\"}} {p95:.2f}",
            f"translation_latency_ms{{quantile=\"0.99\"}} {p99:.2f}",
            "",
            "# HELP error_count_total Total number of errors by type",
            "# TYPE error_count_total counter",
        ]

        for error_type, count in self._metrics["errors"].items():
            lines.append(f'error_count_total{{type="{error_type}"}} {count}')

        return Response(content="\n".join(lines) + "\n", media_type="text/plain")

    def _llm_base_url(self) -> str:
        """Derive the upstream base URL from target_url by stripping the path suffix."""
        url = self.config.llm.target_url
        for suffix in ("/chat/completions", "/v1/chat/completions"):
            if url.endswith(suffix):
                return url[: -len(suffix)].rstrip("/")
        return url.rstrip("/")

    def _normalize_models(self, data: dict) -> dict:
        """Normalize upstream model list to OpenAI format.

        Handles:
          - OpenAI  {"object":"list","data":[{"id":...},...]}
          - Anthropic {"data":[{"id":...,"type":"model",...}],"has_more":...}
          - Plain list {"models":[...]} or {"data":[...]} without object field
        """
        if data.get("object") == "list" and "data" in data:
            return data

        entries = data.get("data") or data.get("models") or []
        normalized = []
        for m in entries:
            normalized.append({
                "id": m.get("id") or m.get("name") or "unknown",
                "object": "model",
                "created": int(time.time()),
                "owned_by": m.get("owned_by") or m.get("created_by") or "upstream",
            })
        return {"object": "list", "data": normalized}

    async def handle_models(self, request: Request) -> Response:
        """Proxy GET /models and /v1/models to the upstream LLM.

        Normalizes the response to OpenAI format so any client can parse it
        regardless of which upstream API (OpenAI, Anthropic, etc.) is connected.
        """
        headers = {}
        for key, value in request.headers.items():
            if key.lower() not in ("host", "content-length", "authorization"):
                headers[key] = value
        if self.config.llm.api_key:
            headers["Authorization"] = f"Bearer {self.config.llm.api_key}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self._llm_base_url()}/models",
                    headers=headers,
                )
            if response.status_code != 200:
                return Response(
                    content=response.content,
                    status_code=response.status_code,
                    media_type="application/json",
                )
            return JSONResponse(self._normalize_models(response.json()))
        except Exception as e:
            self.logger.error(f"Failed to proxy /models: {e}")
            return JSONResponse({"error": str(e)}, status_code=502)

    async def _stream_request(
        self,
        data: dict[str, Any],
        request: Request,
    ):
        headers = {}
        for key, value in request.headers.items():
            if key.lower() not in ("host", "content-length", "authorization"):
                headers[key] = value
        if self.config.llm.api_key:
            headers["Authorization"] = f"Bearer {self.config.llm.api_key}"

        async with httpx.AsyncClient().stream(
            "POST",
            self.config.llm.target_url,
            json=data,
            headers=headers,
            timeout=self.config.llm.timeout,
        ) as response:
            async for line in response.aiter_lines():
                yield line


def create_app(config: AppConfig, engine: TranslationEngine) -> Starlette:
    server = ProxyServer(config, engine)

    async def root(request: Request):
        return JSONResponse(
            {
                "service": "ko-translate-proxy",
                "version": "1.0.0",
                "status": "running",
            }
        )

    routes = [
        Route("/", root),
        Route("/health", server.handle_health),
        Route("/metrics", server.handle_metrics),
        Route("/models", server.handle_models),
        Route("/v1/models", server.handle_models),
        Route("/v1/chat/completions", server.handle_chat_completion, methods=["POST"]),
    ]

    app = Starlette(routes=routes)

    return app


def run_server(config: AppConfig, engine: TranslationEngine):
    import uvicorn

    app = create_app(config, engine)
    uvicorn.run(app, host=config.proxy_host, port=config.proxy_port, log_level=config.log_level.value.lower())


def main():
    from .config import AppConfig, EngineType, LogLevel

    parser = argparse.ArgumentParser(description="Korean Translation Proxy Server")
    parser.add_argument("--config", type=str, help="Path to config TOML file")
    parser.add_argument("--port", type=int, help="Proxy port (overrides config)")
    parser.add_argument("--host", type=str, help="Proxy host (overrides config)")
    parser.add_argument("--translator-engine", type=str, choices=["local", "openai", "google", "deepl"], help="Translation engine")
    parser.add_argument("--local-url", type=str, help="LM Studio URL for translation")
    parser.add_argument("--target-url", type=str, help="Target LLM URL")
    parser.add_argument("--log-level", type=str, choices=["debug", "info", "warning", "error"], help="Log level")

    args = parser.parse_args()

    config = AppConfig.from_file(args.config) if args.config else AppConfig.load_default()

    if args.port:
        config.proxy_port = args.port
    if args.host:
        config.proxy_host = args.host
    if args.translator_engine:
        config.translator.engine = EngineType(args.translator_engine)
    if args.local_url:
        config.translator.local_model_url = args.local_url
    if args.target_url:
        config.llm.target_url = args.target_url
    if args.log_level:
        config.log_level = LogLevel(args.log_level)

    logger = get_logger(log_file=config.log_file, level=config.log_level.value)
    engine = TranslationEngine(config.translator, logger)
    run_server(config, engine)


if __name__ == "__main__":
    main()
