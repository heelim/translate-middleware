"""Performance benchmarks for ko-translate-middleware."""

import asyncio
import json
import sys
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ko_translate.config import TranslationConfig, EngineType, FailMode, LogLevel
from ko_translate.engine import create_engine

SHORT = "안녕하세요"
MEDIUM = "안녕하세요! 파이썬으로 알고리즘을 만들어주세요"
LONG = (
    "안녕하세요! 파이썬으로快速排序알고리즘을 만들어주세요. "
    "한국어 텍스트 번역 성능을 테스트하고 있습니다."
)


def create_mock_engine(config):
    """Create engine with mocked translation backend for benchmarking without a server."""
    engine, logger = create_engine(config)

    async def mock_translate(text, source_lang, target_lang, context=None, preserve=True):
        await asyncio.sleep(0.01)
        return f"Translated: {text[:20]}..."

    engine.ko_to_en = lambda text, ctx=None, preserve=True: mock_translate(text, "Korean", "English", ctx, preserve)
    engine.en_to_ko = lambda text, ctx=None, preserve=True: mock_translate(text, "English", "Korean", ctx, preserve)

    return engine


async def benchmark_latency(engine, texts, iterations=100):
    """Measure latency for translation operations."""
    latencies_ko_to_en = []
    latencies_en_to_ko = []

    for _ in range(iterations):
        for text in texts:
            start = time.perf_counter()
            await engine.ko_to_en(text)
            latencies_ko_to_en.append((time.perf_counter() - start) * 1000)

            start = time.perf_counter()
            await engine.en_to_ko(text)
            latencies_en_to_ko.append((time.perf_counter() - start) * 1000)

    def calc_percentiles(latencies):
        sorted_latencies = sorted(latencies)
        return {
            "p50_ms": sorted_latencies[len(sorted_latencies) // 2],
            "p95_ms": sorted_latencies[int(len(sorted_latencies) * 0.95)],
            "p99_ms": sorted_latencies[int(len(sorted_latencies) * 0.99)],
        }

    return {
        "ko_to_en": calc_percentiles(latencies_ko_to_en),
        "en_to_ko": calc_percentiles(latencies_en_to_ko),
    }


async def benchmark_throughput(engine, duration=30):
    """Measure sustained throughput over a duration."""
    test_text = "안녕하세요"
    start = time.perf_counter()
    count = 0

    while time.perf_counter() - start < duration:
        await engine.ko_to_en(test_text)
        count += 1

    elapsed = time.perf_counter() - start
    return count / elapsed


async def measure_memory_delta(engine, iterations=100):
    """Track memory before/after translations."""
    texts = [SHORT, MEDIUM, LONG]

    tracemalloc.start()
    mem_before = tracemalloc.get_traced_memory()[0]

    for _ in range(iterations):
        for text in texts:
            await engine.ko_to_en(text)
            await engine.en_to_ko(text)

    mem_after = tracemalloc.get_traced_memory()[0]
    tracemalloc.stop()

    delta_mb = (mem_after - mem_before) / (1024 * 1024)
    return delta_mb


async def run_benchmarks():
    """Run all benchmarks and return results."""
    config = TranslationConfig(
        engine=EngineType.LOCAL,
        local_model_url="http://127.0.0.1:1234",
        local_model_name="gemma-4-korean-uncensored",
        fail_mode=FailMode.OPEN,
        log_level=LogLevel.ERROR,
    )

    engine = create_mock_engine(config)

    texts = [SHORT, MEDIUM, LONG]

    print("Running latency benchmarks (100 iterations)...")
    latency_results = await benchmark_latency(engine, texts, iterations=100)
    print(f"  ko_to_en: p50={latency_results['ko_to_en']['p50_ms']:.2f}ms, "
          f"p95={latency_results['ko_to_en']['p95_ms']:.2f}ms, "
          f"p99={latency_results['ko_to_en']['p99_ms']:.2f}ms")
    print(f"  en_to_ko: p50={latency_results['en_to_ko']['p50_ms']:.2f}ms, "
          f"p95={latency_results['en_to_ko']['p95_ms']:.2f}ms, "
          f"p99={latency_results['en_to_ko']['p99_ms']:.2f}ms")

    print("\nRunning throughput benchmark (30 seconds)...")
    throughput = await benchmark_throughput(engine, duration=30)
    print(f"  Throughput: {throughput:.2f} req/sec")

    print("\nRunning memory benchmark (100 translations)...")
    memory_delta = await measure_memory_delta(engine, iterations=100)
    print(f"  Memory delta: {memory_delta:.2f} MB")

    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ko_to_en": latency_results["ko_to_en"],
        "en_to_ko": latency_results["en_to_ko"],
        "throughput": {"req_per_sec": round(throughput, 2)},
        "memory_delta_mb": round(memory_delta, 2),
    }

    return results


def main():
    """Main entry point."""
    results = asyncio.run(run_benchmarks())

    output_path = Path(__file__).parent / "results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nResults saved to {output_path}")
    return results


if __name__ == "__main__":
    main()