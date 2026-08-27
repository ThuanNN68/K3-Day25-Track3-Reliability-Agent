from __future__ import annotations

import argparse
import json
from pathlib import Path


def fmt(metrics: dict[str, object], key: str, digits: int = 2) -> str:
    value = metrics.get(key)
    return f"{value:.{digits}f}" if isinstance(value, float) else str(value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics", default="reports/metrics.json")
    parser.add_argument("--out", default="reports/final_report.md")
    args = parser.parse_args()
    metrics: dict[str, object] = json.loads(Path(args.metrics).read_text(encoding="utf-8"))
    baseline_path = Path("reports/metrics_no_cache.json")
    baseline: dict[str, object] | None = (
        json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path.exists() else None
    )
    scenarios = "\n".join(
        f"| `{name}` | {status} |" for name, status in dict(metrics["scenarios"]).items()
    )
    if baseline is None:
        comparison = "| Baseline | Not included | Run the documented no-cache benchmark before submission. |"
    else:
        comparison = "\n".join(
            f"| {key} | {fmt(baseline, key, digits)} | {fmt(metrics, key, digits)} |"
            for key, digits in (
                ("availability", 4),
                ("latency_p50_ms", 2),
                ("latency_p95_ms", 2),
                ("estimated_cost", 6),
                ("cache_hit_rate", 4),
            )
        )
    availability = float(metrics["availability"])
    p95 = float(metrics["latency_p95_ms"])
    hit_rate = float(metrics["cache_hit_rate"])
    recovery = metrics["recovery_time_ms"]
    recovery_ok = recovery is not None and float(recovery) < 5000
    lines = f"""# Day 25 Reliability Engineering Report

## 1. Architecture summary

```text
Client -> ReliabilityGateway -> semantic cache -> circuit breaker (primary) -> Provider A
                                      | miss/open/failure
                                      +-> circuit breaker (backup) -> Provider B -> static fallback
```

The gateway checks cache first, invokes providers through independent CLOSED/OPEN/HALF_OPEN circuit breakers, and then falls back to the next provider or a degraded reply. Cache entries use TTL, word and character-3-gram cosine similarity, privacy exclusion, and date/ID false-hit rejection.

## 2. Configuration

| Setting | Value | Reason |
|---|---:|---|
| failure_threshold | 3 | Avoids opening on a single transient failure while limiting retries to an unhealthy provider. |
| reset_timeout_seconds | 2 | Bounds the cool-down before a half-open probe. |
| success_threshold | 1 | Restores this local simulated provider after one successful probe. |
| cache TTL | 300 s | Serves repeated FAQ traffic while bounding stale-answer lifetime. |
| similarity_threshold | 0.92 | Conservative semantic reuse; date/ID mismatch guardrail rejects unsafe near matches. |
| requests per scenario | 100 | Three named scenarios yield 300 measured requests. |

## 3. SLO assessment

| SLI | Target | Actual | Met? |
|---|---:|---:|---|
| Availability | >= 99% | {fmt(metrics, 'availability', 4)} | {'Yes' if availability >= 0.99 else 'No'} |
| Latency P95 | < 2500 ms | {fmt(metrics, 'latency_p95_ms')} ms | {'Yes' if p95 < 2500 else 'No'} |
| Cache hit rate | >= 10% | {fmt(metrics, 'cache_hit_rate', 4)} | {'Yes' if hit_rate >= 0.10 else 'No'} |
| Recovery time | < 5000 ms | {fmt(metrics, 'recovery_time_ms')} ms | {'Yes' if recovery_ok else 'No'} |

## 4. Metrics from `reports/metrics.json`

| Metric | Value |
|---|---:|
| availability | {fmt(metrics, 'availability', 4)} |
| error_rate | {fmt(metrics, 'error_rate', 4)} |
| latency_p50_ms | {fmt(metrics, 'latency_p50_ms')} |
| latency_p95_ms | {fmt(metrics, 'latency_p95_ms')} |
| latency_p99_ms | {fmt(metrics, 'latency_p99_ms')} |
| fallback_success_rate | {fmt(metrics, 'fallback_success_rate', 4)} |
| cache_hit_rate | {fmt(metrics, 'cache_hit_rate', 4)} |
| estimated_cost | {fmt(metrics, 'estimated_cost', 6)} |
| estimated_cost_saved | {fmt(metrics, 'estimated_cost_saved', 6)} |
| circuit_open_count | {fmt(metrics, 'circuit_open_count')} |
| recovery_time_ms | {fmt(metrics, 'recovery_time_ms')} |

## 5. Cache comparison

| Metric | Without cache | With cache |
|---|---:|---:|
{comparison}

Cache hits are recorded with zero latency and excluded from the starter's latency sample; cost, availability, and hit rate are the reliable cache-benefit indicators in this measurement.

## 6. Redis shared cache

In-memory cache is per-process, so separate gateway pods do not share warm entries. `SharedRedisCache` stores query and response hashes under a common Redis prefix with TTL, allowing distinct instances to retrieve the same entry. Privacy checks run on both read and write, while similarity lookup preserves the false-hit guardrail.

Evidence: two cache instances against local Redis returned `('visible from instance two', 1.0)` after the first instance wrote the entry. Redis CLI listed `rl:cache:evidence:9ffbf3a7014e`.

## 7. Chaos scenarios

| Scenario | Status |
|---|---|
{scenarios}

The primary timeout scenario exercises fallback and opens its circuit. The flaky scenario exercises failure and recovery. The healthy scenario exercises the primary route and cache reuse.

## 8. Remaining weakness and remediation

Circuit-breaker state is local to each gateway process, so multiple pods could disagree about a failing provider. Store state and half-open probe leases in Redis using atomic counters and TTL, and use a bounded in-memory fallback when Redis is unavailable.

## 9. Next steps

1. Share circuit-breaker state across gateway instances.
2. Export per-scenario and end-to-end latency metrics, including cache hits.
3. Add rate limits and cache-quality monitoring before production traffic.
"""
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(lines, encoding="utf-8")
    print(f"wrote {output}")


if __name__ == "__main__":
    main()
