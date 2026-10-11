"""Load-test the PRD time-to-first-answer KPI (p95 < 10 s).

Sends N concurrent requests against POST /api/chat (default) or
POST /api/search, measures latencies, and reports p50/p95/p99, throughput,
and error rate. Exits non-zero when p95 exceeds the threshold so CI or an
operator can gate on the KPI.

Only stdlib + httpx (already in the dev group) are used.

Usage:
    .venv/bin/python scripts/loadtest.py --help
    .venv/bin/python scripts/loadtest.py --requests 50 --concurrency 5
    RAGUARD_BASE_URL=http://localhost:8000 RAGUARD_TOKEN=<jwt> \\
        .venv/bin/python scripts/loadtest.py --endpoint search --requests 100

Auth: pass --token or set RAGUARD_TOKEN (sent as `Authorization: Bearer`).
Without a token, expect 401s — they count as errors in the report.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import os
import sys
import time

import httpx

DEFAULT_THRESHOLD_SECONDS = 10.0


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = (len(ordered) - 1) * (pct / 100.0)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    frac = rank - low
    return ordered[low] * (1 - frac) + ordered[high] * frac


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load-test raguard chat/search latency against the 10 s p95 PRD KPI."
    )
    parser.add_argument(
        "--base-url", default=os.environ.get("RAGUARD_BASE_URL", "http://localhost:8000")
    )
    parser.add_argument("--endpoint", choices=("chat", "search"), default="chat")
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--query", default="what is the refund policy?")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD_SECONDS)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--token", default=os.environ.get("RAGUARD_TOKEN", ""))
    args = parser.parse_args(argv)
    if args.requests < 1 or args.concurrency < 1:
        parser.error("--requests and --concurrency must be >= 1")
    return args


def one_request(client: httpx.Client, url: str, payload: dict[str, str]) -> tuple[float, bool]:
    start = time.perf_counter()
    try:
        response = client.post(url, json=payload)
        ok = 200 <= response.status_code < 300
    except httpx.HTTPError:
        ok = False
    return time.perf_counter() - start, ok


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    url = args.base_url.rstrip("/") + f"/api/{args.endpoint}"
    payload = {"query": args.query}
    headers = {"Authorization": f"Bearer {args.token}"} if args.token else {}

    try:
        client = httpx.Client(base_url=args.base_url, headers=headers, timeout=args.timeout)
    except Exception as exc:  # pragma: no cover - constructor failure
        print(f"error: cannot create HTTP client: {exc}")
        return 1

    latencies: list[float] = []
    errors = 0
    wall_start = time.perf_counter()
    try:
        with client:
            with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
                futures = [
                    pool.submit(one_request, client, url, payload) for _ in range(args.requests)
                ]
                for future in concurrent.futures.as_completed(futures):
                    try:
                        latency, ok = future.result()
                    except Exception:
                        latency, ok = 0.0, False
                    latencies.append(latency)
                    if not ok:
                        errors += 1
    except Exception as exc:
        print(f"error: load test failed: {exc}")
        return 1
    wall = time.perf_counter() - wall_start

    total = len(latencies)
    error_rate = errors / total if total else 1.0
    p50 = percentile(latencies, 50)
    p95 = percentile(latencies, 95)
    p99 = percentile(latencies, 99)
    rps = total / wall if wall > 0 else 0.0

    print(f"target:     POST {url} (n={total}, concurrency={args.concurrency})")
    print(
        f"p50/p95/p99: {p50:.3f}s / {p95:.3f}s / {p99:.3f}s (threshold p95 < {args.threshold:.1f}s)"
    )
    print(f"throughput:  {rps:.2f} req/s  errors: {errors}/{total} ({error_rate:.1%})")
    if p95 > args.threshold:
        print(f"FAIL: p95 {p95:.3f}s exceeds threshold {args.threshold:.1f}s")
        return 2
    if errors == total:
        print(f"FAIL: all {total} requests failed (server up? token valid?)")
        return 1
    if errors:
        print(f"WARN: {errors}/{total} requests failed (auth? server up?)")
    else:
        print("PASS: p95 within budget")
    return 0


if __name__ == "__main__":
    sys.exit(main())
