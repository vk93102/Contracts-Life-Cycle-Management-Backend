#!/usr/bin/env python3
"""Endpoint performance test runner.

Goal
- Hit a representative list of CLM API endpoints and capture response-time stats.
- Emit a Markdown report (and optional JSON) suitable for attaching to audits.

Notes
- Defaults to SAFE, read-oriented endpoints (mostly GET + a few low-risk POSTs).
- Endpoints requiring IDs, file uploads, or staging data are intentionally skipped.

Usage examples
  python3 CLM_Backend/tools/endpoint_perf_test.py \
    --base-url http://127.0.0.1:11000 \
    --auth-email admin@example.com --auth-password admin12345

  python3 CLM_Backend/tools/endpoint_perf_test.py \
    --base-url https://staging.example.com \
    --token "$TOKEN" --requests 10 --timeout 15 \
    --out-md ops/performance/reports/endpoint_latency.md
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests


@dataclass(frozen=True)
class EndpointSpec:
    name: str
    method: str
    path: str
    requires_auth: bool = True
    params: Optional[Dict[str, str]] = None
    json_body: Optional[Dict[str, Any]] = None
    headers: Optional[Dict[str, str]] = None
    skip_reason: Optional[str] = None


@dataclass
class EndpointResult:
    name: str
    method: str
    url: str
    requires_auth: bool
    status_code: Optional[int]
    ok: bool
    error: Optional[str]
    samples_ms: List[float]
    bytes: Optional[int]

    p50_ms: Optional[float] = None
    p95_ms: Optional[float] = None
    avg_ms: Optional[float] = None
    max_ms: Optional[float] = None


def _percentile(values: List[float], p: float) -> float:
    if not values:
        raise ValueError("empty values")
    values_sorted = sorted(values)
    k = int(math.ceil(p * len(values_sorted))) - 1
    k = max(0, min(k, len(values_sorted) - 1))
    return values_sorted[k]


def _compute_stats(result: EndpointResult) -> None:
    if not result.samples_ms:
        return
    result.p50_ms = _percentile(result.samples_ms, 0.50)
    result.p95_ms = _percentile(result.samples_ms, 0.95)
    result.avg_ms = sum(result.samples_ms) / len(result.samples_ms)
    result.max_ms = max(result.samples_ms)


def _join_url(base_url: str, path: str) -> str:
    base = base_url.rstrip("/")
    if path.startswith("/"):
        return base + path
    return base + "/" + path


def _get_token_via_login(base_url: str, email: str, password: str, timeout_s: float) -> str:
    url = _join_url(base_url, "/api/auth/login/")
    resp = requests.post(
        url,
        json={"email": email, "password": password},
        headers={"Content-Type": "application/json"},
        timeout=timeout_s,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"login failed: HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        data = resp.json()
    except Exception as e:
        raise RuntimeError(f"login returned non-JSON: {e}")

    token = data.get("access") or data.get("token") or data.get("jwt")
    if not token:
        raise RuntimeError(f"login response missing access token field; keys={list(data.keys())}")
    return str(token)


def default_endpoints(include_write: bool) -> List[EndpointSpec]:
    endpoints: List[EndpointSpec] = [
        # Public / low-risk
        EndpointSpec(name="Health", method="GET", path="/api/v1/health/", requires_auth=False),
        EndpointSpec(name="Metrics", method="GET", path="/metrics", requires_auth=False),

        # Auth (will be 401 unless token present)
        EndpointSpec(name="Auth: Current user", method="GET", path="/api/auth/me/", requires_auth=True),

        # Admin API
        EndpointSpec(name="Admin: Me", method="GET", path="/api/v1/admin/me/", requires_auth=True),
        EndpointSpec(name="Admin: Analytics", method="GET", path="/api/v1/admin/analytics/", requires_auth=True),
        EndpointSpec(name="Admin: Activity", method="GET", path="/api/v1/admin/activity/", requires_auth=True),
        EndpointSpec(name="Admin: Users", method="GET", path="/api/v1/admin/users/", requires_auth=True),

        # Templates / contracts (read-oriented)
        EndpointSpec(name="Templates: Types", method="GET", path="/api/v1/templates/types/", requires_auth=True),
        EndpointSpec(name="Templates: Summary", method="GET", path="/api/v1/templates/summary/", requires_auth=True),
        EndpointSpec(name="Templates: NDA detail", method="GET", path="/api/v1/templates/types/NDA/", requires_auth=True),
        EndpointSpec(name="Templates: Files", method="GET", path="/api/v1/templates/files/", requires_auth=True),
        EndpointSpec(name="Templates: My files", method="GET", path="/api/v1/templates/files/mine/", requires_auth=True),

        EndpointSpec(name="Contracts: List", method="GET", path="/api/v1/contracts/", requires_auth=True),
        EndpointSpec(name="Clauses: List", method="GET", path="/api/v1/clauses/", requires_auth=True),
        EndpointSpec(name="Contract templates: List", method="GET", path="/api/v1/contract-templates/", requires_auth=True),
        EndpointSpec(name="Generation jobs: List", method="GET", path="/api/v1/generation-jobs/", requires_auth=True),

        # Private uploads (may require R2 configuration)
        EndpointSpec(name="Private uploads: List", method="GET", path="/api/v1/private-uploads/", requires_auth=True),

        # Workflows / approvals / reviews
        EndpointSpec(name="Workflows: List", method="GET", path="/api/v1/workflows/", requires_auth=True),
        EndpointSpec(name="Workflow instances: List", method="GET", path="/api/v1/workflow-instances/", requires_auth=True),
        EndpointSpec(name="Approvals: List", method="GET", path="/api/v1/approvals/", requires_auth=True),
        EndpointSpec(name="Reviews: List", method="GET", path="/api/v1/review-contracts/", requires_auth=True),
        EndpointSpec(name="Clause library: List", method="GET", path="/api/v1/clause-library/", requires_auth=True),
        EndpointSpec(name="Calendar events: List", method="GET", path="/api/v1/events/", requires_auth=True),

        # Firma (read / debug endpoints)
        EndpointSpec(name="Firma: Debug config", method="GET", path="/api/v1/firma/debug/config/", requires_auth=True),
        EndpointSpec(name="Firma: Debug connectivity", method="GET", path="/api/v1/firma/debug/connectivity/", requires_auth=True),
        EndpointSpec(name="Firma: Signing requests", method="GET", path="/api/v1/firma/esign/requests/", requires_auth=True),
    ]

    if include_write:
        endpoints.extend(
            [
                # AI endpoints (POST) — may call external services; keep optional.
                EndpointSpec(
                    name="AI: Extract metadata",
                    method="POST",
                    path="/api/v1/ai/extract/metadata/",
                    requires_auth=True,
                    json_body={"text": "This Agreement is between Acme Corp and Beta LLC effective 2026-01-01."},
                ),
                EndpointSpec(
                    name="AI: Classify clause",
                    method="POST",
                    path="/api/v1/ai/classify/clause/",
                    requires_auth=True,
                    json_body={"clause_text": "Either party may terminate upon thirty (30) days notice."},
                ),
            ]
        )

    return endpoints


def run_benchmark(
    base_url: str,
    endpoints: List[EndpointSpec],
    token: Optional[str],
    requests_per_endpoint: int,
    timeout_s: float,
    sleep_s: float,
) -> Tuple[List[EndpointResult], List[Dict[str, str]]]:
    session = requests.Session()

    skipped: List[Dict[str, str]] = []
    results: List[EndpointResult] = []

    for spec in endpoints:
        if spec.skip_reason:
            skipped.append({"method": spec.method, "path": spec.path, "name": spec.name, "reason": spec.skip_reason})
            continue

        url = _join_url(base_url, spec.path)
        headers: Dict[str, str] = {"Accept": "application/json"}
        if spec.headers:
            headers.update(spec.headers)
        if spec.requires_auth and token:
            headers["Authorization"] = f"Bearer {token}"
        if spec.json_body is not None:
            headers.setdefault("Content-Type", "application/json")

        samples_ms: List[float] = []
        last_status: Optional[int] = None
        last_ok = False
        last_error: Optional[str] = None
        last_bytes: Optional[int] = None

        for _ in range(requests_per_endpoint):
            start = time.perf_counter()
            try:
                resp = session.request(
                    method=spec.method,
                    url=url,
                    params=spec.params,
                    json=spec.json_body,
                    headers=headers,
                    timeout=timeout_s,
                )
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                samples_ms.append(elapsed_ms)
                last_status = resp.status_code
                last_ok = resp.ok
                last_bytes = len(resp.content) if resp.content is not None else 0
                last_error = None
            except Exception as e:
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                samples_ms.append(elapsed_ms)
                last_status = None
                last_ok = False
                last_error = str(e)

            if sleep_s > 0:
                time.sleep(sleep_s)

        r = EndpointResult(
            name=spec.name,
            method=spec.method,
            url=url,
            requires_auth=spec.requires_auth,
            status_code=last_status,
            ok=last_ok,
            error=last_error,
            samples_ms=samples_ms,
            bytes=last_bytes,
        )
        _compute_stats(r)
        results.append(r)

    return results, skipped


def render_markdown(
    base_url: str,
    started_at: str,
    requests_per_endpoint: int,
    timeout_s: float,
    sleep_s: float,
    include_write: bool,
    results: List[EndpointResult],
    skipped: List[Dict[str, str]],
) -> str:
    lines: List[str] = []
    lines.append("# API Endpoint Performance Report")
    lines.append("")
    lines.append(f"- Base URL: `{base_url}`")
    lines.append(f"- Started: `{started_at}`")
    lines.append(f"- Samples per endpoint: `{requests_per_endpoint}`")
    lines.append(f"- Timeout (s): `{timeout_s}`")
    lines.append(f"- Sleep between samples (s): `{sleep_s}`")
    lines.append(f"- Include write/AI endpoints: `{include_write}`")
    lines.append("")

    lines.append("## Results")
    lines.append("")
    lines.append("| Endpoint | Method | HTTP | p50 (ms) | p95 (ms) | avg (ms) | max (ms) | bytes | Notes |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---|")

    for r in results:
        http = str(r.status_code) if r.status_code is not None else "ERR"
        p50 = f"{r.p50_ms:.1f}" if r.p50_ms is not None else "-"
        p95 = f"{r.p95_ms:.1f}" if r.p95_ms is not None else "-"
        avg = f"{r.avg_ms:.1f}" if r.avg_ms is not None else "-"
        mx = f"{r.max_ms:.1f}" if r.max_ms is not None else "-"
        b = str(r.bytes) if r.bytes is not None else "-"
        notes = []
        if r.requires_auth:
            notes.append("auth")
        if r.error:
            notes.append(r.error[:80])
        lines.append(
            "| "
            + f"{r.name} (`{r.url}`) | {r.method} | {http} | {p50} | {p95} | {avg} | {mx} | {b} | {', '.join(notes)} |"
        )

    if skipped:
        lines.append("")
        lines.append("## Skipped")
        lines.append("")
        lines.append("| Name | Method | Path | Reason |")
        lines.append("|---|---:|---|---|")
        for s in skipped:
            lines.append(f"| {s['name']} | {s['method']} | `{s['path']}` | {s['reason']} |")

    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("- Prefer comparing environments with the same dataset and similar rate-limit settings.")
    lines.append("- If many endpoints show `401`, pass a valid token (`--token`) or credentials (`--auth-email/--auth-password`).")
    lines.append("- For endpoints requiring IDs or file uploads, extend the script with seeded data and safe fixtures.")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark CLM API endpoints and produce a response-time report.")
    parser.add_argument("--base-url", required=True, help="Base URL, e.g. http://127.0.0.1:11000")
    parser.add_argument("--token", default=os.getenv("TOKEN"), help="Bearer token (or set TOKEN env var)")
    parser.add_argument("--auth-email", default=os.getenv("AUTH_EMAIL"), help="Login email (optional)")
    parser.add_argument("--auth-password", default=os.getenv("AUTH_PASSWORD"), help="Login password (optional)")
    parser.add_argument("--requests", type=int, default=5, help="Requests per endpoint")
    parser.add_argument("--timeout", type=float, default=12.0, help="Request timeout seconds")
    parser.add_argument("--sleep", type=float, default=0.05, help="Sleep between samples (seconds)")
    parser.add_argument("--include-write", action="store_true", help="Include write/AI endpoints")
    parser.add_argument("--out-md", default="ops/performance/reports/endpoint_performance.md", help="Output Markdown path")
    parser.add_argument("--out-json", default="", help="Optional JSON output path")

    args = parser.parse_args()

    token = args.token
    if not token and args.auth_email and args.auth_password:
        token = _get_token_via_login(args.base_url, args.auth_email, args.auth_password, timeout_s=args.timeout)

    started_at = datetime.now(timezone.utc).isoformat()
    endpoints = default_endpoints(include_write=bool(args.include_write))

    results, skipped = run_benchmark(
        base_url=args.base_url,
        endpoints=endpoints,
        token=token,
        requests_per_endpoint=int(args.requests),
        timeout_s=float(args.timeout),
        sleep_s=float(args.sleep),
    )

    md = render_markdown(
        base_url=args.base_url,
        started_at=started_at,
        requests_per_endpoint=int(args.requests),
        timeout_s=float(args.timeout),
        sleep_s=float(args.sleep),
        include_write=bool(args.include_write),
        results=results,
        skipped=skipped,
    )

    out_md = args.out_md
    os.makedirs(os.path.dirname(out_md), exist_ok=True)
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(md)

    if args.out_json:
        os.makedirs(os.path.dirname(args.out_json), exist_ok=True)
        payload = {
            "base_url": args.base_url,
            "started_at": started_at,
            "requests_per_endpoint": int(args.requests),
            "timeout": float(args.timeout),
            "sleep": float(args.sleep),
            "include_write": bool(args.include_write),
            "results": [asdict(r) for r in results],
            "skipped": skipped,
        }
        with open(args.out_json, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    print(f"Wrote Markdown report: {out_md}")
    if args.out_json:
        print(f"Wrote JSON report: {args.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
