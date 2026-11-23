"""Reproducible local load smoke test for core read endpoints.

This is not a production capacity benchmark. It measures one API process and
one database, so PostgreSQL pool behaviour and multi-replica scaling must be
measured separately in staging.

Examples:
    python scripts/load_smoke.py --spawn --duration 10 --endpoint-concurrency 3
    python scripts/load_smoke.py --base-url http://127.0.0.1:8000/api/v1
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import subprocess
import sys
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

import httpx

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = "http://127.0.0.1:8013/api/v1"


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def spawn_server(port: int) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-access-log",
        ],
        cwd=BACKEND_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        env=os.environ.copy(),
        text=True,
    )


async def wait_for_ready(base_url: str, process: subprocess.Popen[str] | None, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    async with httpx.AsyncClient(timeout=2.0) as client:
        while time.monotonic() < deadline:
            if process is not None and process.poll() is not None:
                raise RuntimeError(f"API exited during startup with code {process.returncode}")
            try:
                response = await client.get(f"{base_url}/health/ready")
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.5)
    raise RuntimeError(f"API did not become ready within {timeout:.0f}s")


async def create_session(base_url: str) -> str:
    suffix = uuid.uuid4().hex[:12]
    password = "load-smoke-password-123"
    async with httpx.AsyncClient(timeout=10.0) as client:
        registered = await client.post(
            f"{base_url}/auth/register",
            json={"username": f"load_{suffix}", "password": password, "email": f"load_{suffix}@example.com"},
        )
        if registered.status_code != 201:
            raise RuntimeError(f"registration failed: {registered.status_code} {registered.text[:200]}")
        login = await client.post(
            f"{base_url}/auth/token",
            data={"username": f"load_{suffix}", "password": password},
        )
        if login.status_code != 200:
            raise RuntimeError(f"login failed: {login.status_code} {login.text[:200]}")
        return str(login.json()["access_token"])


ENDPOINTS: list[tuple[str, str, dict[str, str], dict[str, Any]]] = [
    ("health", "GET", {}, {}),
    ("ready", "GET", {}, {}),
    ("catalogue", "GET", {}, {"limit": 20}),
    ("facets", "GET", {}, {}),
    ("search", "GET", {}, {"q": "matrix", "limit": 20}),
    ("recommendations", "GET", {"X-Load-Auth": "1"}, {"k": 24}),
    ("watchlist", "GET", {"X-Load-Auth": "1"}, {}),
]


async def worker(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    endpoint: tuple[str, str, dict[str, str], dict[str, Any]],
    stop_at: float,
    durations: dict[str, list[float]],
    errors: dict[str, int],
    rate_limited: dict[str, int],
    status_counts: dict[str, dict[int, int]],
) -> None:
    name, method, extra_headers, params = endpoint
    while time.monotonic() < stop_at:
        headers = dict(extra_headers)
        if headers.pop("X-Load-Auth", None):
            headers["Authorization"] = f"Bearer {token}"
        started = time.perf_counter()
        try:
            response = await client.request(method, f"{base_url}{_path(name)}", params=params, headers=headers)
            elapsed = time.perf_counter() - started
            durations[name].append(elapsed)
            status_counts[name][response.status_code] = status_counts[name].get(response.status_code, 0) + 1
            if response.status_code == 429:
                rate_limited[name] += 1
            elif response.status_code >= 500:
                errors[name] += 1
        except httpx.HTTPError:
            errors[name] += 1


def _path(name: str) -> str:
    return {
        "health": "/health",
        "ready": "/health/ready",
        "catalogue": "/movies",
        "facets": "/catalogue/facets",
        "search": "/search",
        "recommendations": "/recommendations",
        "watchlist": "/watchlist",
    }[name]


async def run(base_url: str, duration: float, endpoint_concurrency: int) -> dict[str, Any]:
    await wait_for_ready(base_url, None, 5.0)
    token = await create_session(base_url)
    durations: dict[str, list[float]] = defaultdict(list)
    errors: dict[str, int] = defaultdict(int)
    rate_limited: dict[str, int] = defaultdict(int)
    status_counts: dict[str, dict[int, int]] = defaultdict(dict)
    stop_at = time.monotonic() + duration
    total_concurrency = max(1, endpoint_concurrency) * len(ENDPOINTS)
    limits = httpx.Limits(max_connections=total_concurrency * 2, max_keepalive_connections=total_concurrency)

    async with httpx.AsyncClient(timeout=15.0, limits=limits) as client:
        await asyncio.gather(
            *[
                worker(client, base_url, token, endpoint, stop_at, durations, errors, rate_limited, status_counts)
                for endpoint in ENDPOINTS
                for _ in range(max(1, endpoint_concurrency))
            ]
        )

    report: dict[str, Any] = {
        "base_url": base_url,
        "duration_seconds": duration,
        "endpoint_concurrency": max(1, endpoint_concurrency),
        "total_concurrency": total_concurrency,
        "endpoints": {},
    }
    for name, _method, _headers, _params in ENDPOINTS:
        values = durations[name]
        report["endpoints"][name] = {
            "requests": len(values),
            "errors": errors[name],
            "rate_limited": rate_limited[name],
            "statuses": {str(code): count for code, count in sorted(status_counts[name].items())},
            "throughput_rps": round(len(values) / duration, 2) if duration else 0,
            "p50_ms": round(percentile(values, 0.50) * 1000, 2),
            "p95_ms": round(percentile(values, 0.95) * 1000, 2),
            "p99_ms": round(percentile(values, 0.99) * 1000, 2),
            "mean_ms": round(statistics.fmean(values) * 1000, 2) if values else 0,
        }
    return report


async def main_async(args: argparse.Namespace) -> dict[str, Any]:
    process = spawn_server(args.port) if args.spawn else None
    base_url = args.base_url or f"http://127.0.0.1:{args.port}/api/v1"
    try:
        if process is not None:
            await wait_for_ready(base_url, process, args.startup_timeout)
        return await run(base_url, args.duration, args.endpoint_concurrency)
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="")
    parser.add_argument("--port", type=int, default=8013)
    parser.add_argument("--spawn", action="store_true", help="Start a local uvicorn process")
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--endpoint-concurrency", type=int, default=3)
    parser.add_argument("--startup-timeout", type=float, default=120.0)
    parser.add_argument("--json-out", default="")
    args = parser.parse_args()

    report = asyncio.run(main_async(args))
    print(json.dumps(report, indent=2))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    failed = sum(item["errors"] for item in report["endpoints"].values())
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
