# Day 25 Reliability Engineering Report

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
| Availability | >= 99% | 0.9900 | Yes |
| Latency P95 | < 2500 ms | 323.10 ms | Yes |
| Cache hit rate | >= 10% | 0.6567 | Yes |
| Recovery time | < 5000 ms | 2330.50 ms | Yes |

## 4. Metrics from `reports/metrics.json`

| Metric | Value |
|---|---:|
| availability | 0.9900 |
| error_rate | 0.0100 |
| latency_p50_ms | 281.02 |
| latency_p95_ms | 323.10 |
| latency_p99_ms | 361.98 |
| fallback_success_rate | 0.9571 |
| cache_hit_rate | 0.6567 |
| estimated_cost | 0.042340 |
| estimated_cost_saved | 0.197000 |
| circuit_open_count | 8 |
| recovery_time_ms | 2330.50 |

## 5. Cache comparison

| Metric | Without cache | With cache |
|---|---:|---:|
| availability | 0.9600 | 0.9900 |
| latency_p50_ms | 279.38 | 281.02 |
| latency_p95_ms | 318.24 | 323.10 |
| estimated_cost | 0.119380 | 0.042340 |
| cache_hit_rate | 0.0000 | 0.6567 |

Cache hits are recorded with zero latency and excluded from the starter's latency sample; cost, availability, and hit rate are the reliable cache-benefit indicators in this measurement.

## 6. Redis shared cache

In-memory cache is per-process, so separate gateway pods do not share warm entries. `SharedRedisCache` stores query and response hashes under a common Redis prefix with TTL, allowing distinct instances to retrieve the same entry. Privacy checks run on both read and write, while similarity lookup preserves the false-hit guardrail.

Evidence: two cache instances against local Redis returned `('visible from instance two', 1.0)` after the first instance wrote the entry. Redis CLI listed `rl:cache:evidence:9ffbf3a7014e`.

## 7. Chaos scenarios

| Scenario | Status |
|---|---|
| `primary_timeout_100` | pass |
| `primary_flaky_50` | pass |
| `all_healthy` | pass |

The primary timeout scenario exercises fallback and opens its circuit. The flaky scenario exercises failure and recovery. The healthy scenario exercises the primary route and cache reuse.

## 8. Remaining weakness and remediation

Circuit-breaker state is local to each gateway process, so multiple pods could disagree about a failing provider. Store state and half-open probe leases in Redis using atomic counters and TTL, and use a bounded in-memory fallback when Redis is unavailable.

## 9. Next steps

1. Share circuit-breaker state across gateway instances.
2. Export per-scenario and end-to-end latency metrics, including cache hits.
3. Add rate limits and cache-quality monitoring before production traffic.
