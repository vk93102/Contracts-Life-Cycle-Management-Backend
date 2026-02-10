#!/usr/bin/env python3
"""API test runner (E2E + Performance) for CLM Backend.

What this solves
- "Test end to end properly": run ordered flows that create/use resources.
- "Show response time of endpoints": benchmark endpoints with p50/p95/avg/max.
- "Overleaf LaTeX report": emit a LaTeX section containing the latest results table.

This runner is manifest-driven so we can cover *all* endpoints/features in a controlled,
repeatable way without hardcoding environment-specific IDs.

See: ops/performance/api_test_manifest.json

Usage
  python3 CLM_Backend/tools/api_test_runner.py \
    --base-url http://127.0.0.1:11000 \
    --manifest ops/performance/api_test_manifest.json \
    --mode perf \
    --samples 10 \
    --out-md ops/performance/reports/endpoint_performance.md \
    --out-tex ops/security/overleaf/sections/12-api-performance-results.tex

  python3 CLM_Backend/tools/api_test_runner.py \
    --base-url http://127.0.0.1:11000 \
    --manifest ops/performance/api_test_manifest.json \
    --mode e2e \
    --flow core_smoke
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests


def _join_url(base_url: str, path: str) -> str:
    base = base_url.rstrip("/")
    if path.startswith("/"):
        return base + path
    return base + "/" + path


def _percentile(values: List[float], p: float) -> float:
    if not values:
        raise ValueError("empty")
    values_sorted = sorted(values)
    k = int(math.ceil(p * len(values_sorted))) - 1
    k = max(0, min(k, len(values_sorted) - 1))
    return values_sorted[k]


def _render_template(s: str, context: Dict[str, Any]) -> str:
    """Very small templating: replaces {{var}} with context[var]."""

    def repl(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        val = context.get(key)
        return "" if val is None else str(val)

    return re.sub(r"\{\{\s*([^}]+?)\s*\}\}", repl, s)


def _get_in(obj: Any, dotted_path: str) -> Any:
    """Extract from dict/list via dotted path like 'contract.id' or 'results.0.id'."""
    cur = obj
    for part in (dotted_path or "").split("."):
        if part == "":
            continue
        if isinstance(cur, list):
            idx = int(part)
            cur = cur[idx]
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _login(base_url: str, email: str, password: str, timeout_s: float) -> str:
    url = _join_url(base_url, "/api/auth/login/")
    resp = requests.post(url, json={"email": email, "password": password}, timeout=timeout_s)
    if resp.status_code >= 400:
        raise RuntimeError(f"login failed: HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    token = data.get("access")
    if not token:
        raise RuntimeError(f"login response missing 'access' token; keys={list(data.keys())}")
    return str(token)


@dataclass(frozen=True)
class ManifestEndpoint:
    name: str
    method: str
    path: str
    auth: bool = True
    params: Optional[Dict[str, str]] = None
    json: Optional[Dict[str, Any]] = None
    expected_status: Optional[List[int]] = None
    notes: str = ""
    dangerous: bool = False


@dataclass(frozen=True)
class ManifestStep:
    name: str
    method: str
    path: str
    auth: bool = True
    params: Optional[Dict[str, str]] = None
    json: Optional[Dict[str, Any]] = None
    multipart: Optional[Dict[str, Any]] = None  # {"files": {field: path}, "data": {k:v}}
    expected_status: Optional[List[int]] = None
    extract: Optional[Dict[str, str]] = None  # var -> dotted path in JSON response


@dataclass
class PerfResult:
    name: str
    method: str
    url: str
    http: str
    p50_ms: Optional[float]
    p95_ms: Optional[float]
    avg_ms: Optional[float]
    max_ms: Optional[float]
    bytes: Optional[int]
    notes: str


def _request(
    session: requests.Session,
    method: str,
    url: str,
    token: Optional[str],
    auth: bool,
    params: Optional[Dict[str, str]],
    json_body: Optional[Dict[str, Any]],
    multipart: Optional[Dict[str, Any]],
    timeout_s: float,
) -> Tuple[requests.Response, float]:
    headers: Dict[str, str] = {"Accept": "application/json"}
    if auth and token:
        headers["Authorization"] = f"Bearer {token}"
    if json_body is not None and multipart is not None:
        raise ValueError("Provide either json or multipart, not both")

    files = None
    data = None
    opened_files = []
    if multipart is not None:
        files = {}
        data = {}
        for k, v in (multipart.get("data") or {}).items():
            data[str(k)] = str(v)
        for field, path in (multipart.get("files") or {}).items():
            fp = open(str(path), "rb")
            opened_files.append(fp)
            files[str(field)] = (os.path.basename(str(path)), fp)
        # Let requests set Content-Type boundary.
    elif json_body is not None:
        headers["Content-Type"] = "application/json"

    start = time.perf_counter()
    try:
        resp = session.request(
            method=method,
            url=url,
            params=params,
            json=json_body,
            data=data,
            files=files,
            headers=headers,
            timeout=timeout_s,
        )
    finally:
        for fp in opened_files:
            try:
                fp.close()
            except Exception:
                pass
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return resp, elapsed_ms


def run_perf(
    base_url: str,
    token: Optional[str],
    endpoints: List[ManifestEndpoint],
    samples: int,
    timeout_s: float,
    sleep_s: float,
) -> List[PerfResult]:
    session = requests.Session()
    results: List[PerfResult] = []

    for ep in endpoints:
        if getattr(ep, "dangerous", False):
            # These require explicit allow flag; handled by caller.
            pass
        url = _join_url(base_url, ep.path)
        timings: List[float] = []
        last_status: Optional[int] = None
        last_bytes: Optional[int] = None
        last_err: Optional[str] = None

        for _ in range(samples):
            try:
                resp, ms = _request(session, ep.method, url, token, ep.auth, ep.params, ep.json, None, timeout_s)
                timings.append(ms)
                last_status = resp.status_code
                last_bytes = len(resp.content or b"")
                last_err = None
            except Exception as e:
                timings.append(float("nan"))
                last_status = None
                last_bytes = None
                last_err = str(e)
            if sleep_s > 0:
                time.sleep(sleep_s)

        clean = [t for t in timings if not (isinstance(t, float) and math.isnan(t))]
        if clean:
            p50 = _percentile(clean, 0.50)
            p95 = _percentile(clean, 0.95)
            avg = sum(clean) / len(clean)
            mx = max(clean)
        else:
            p50 = p95 = avg = mx = None

        http = str(last_status) if last_status is not None else "ERR"
        notes = ep.notes
        if last_err:
            notes = (notes + "; " if notes else "") + last_err[:90]
        if last_status is not None and ep.expected_status:
            if last_status not in ep.expected_status:
                notes = (notes + "; " if notes else "") + f"unexpected_http={last_status}"

        results.append(
            PerfResult(
                name=ep.name,
                method=ep.method,
                url=url,
                http=http,
                p50_ms=p50,
                p95_ms=p95,
                avg_ms=avg,
                max_ms=mx,
                bytes=last_bytes,
                notes=notes,
            )
        )

    return results


def run_e2e_flow(
    base_url: str,
    token: Optional[str],
    steps: List[ManifestStep],
    timeout_s: float,
) -> Dict[str, Any]:
    session = requests.Session()
    ctx: Dict[str, Any] = {}
    out: Dict[str, Any] = {"steps": []}

    for step in steps:
        path = _render_template(step.path, ctx)
        url = _join_url(base_url, path)

        json_body = None
        if step.json is not None:
            # Render strings inside json body recursively
            def render_obj(o: Any) -> Any:
                if isinstance(o, str):
                    return _render_template(o, ctx)
                if isinstance(o, dict):
                    return {k: render_obj(v) for k, v in o.items()}
                if isinstance(o, list):
                    return [render_obj(v) for v in o]
                return o

            json_body = render_obj(step.json)

        # Multipart support (render strings inside multipart spec)
        if step.multipart is not None:
            mp = step.multipart

            def render_mp(o: Any) -> Any:
                if isinstance(o, str):
                    return _render_template(o, ctx)
                if isinstance(o, dict):
                    return {k: render_mp(v) for k, v in o.items()}
                if isinstance(o, list):
                    return [render_mp(v) for v in o]
                return o

            mp = render_mp(mp)
            resp, ms = _request(session, step.method, url, token, step.auth, step.params, None, mp, timeout_s)
        else:
            resp, ms = _request(session, step.method, url, token, step.auth, step.params, json_body, None, timeout_s)
        rec: Dict[str, Any] = {
            "name": step.name,
            "method": step.method,
            "url": url,
            "http": resp.status_code,
            "elapsed_ms": round(ms, 2),
        }

        ok_status = True
        if step.expected_status:
            ok_status = resp.status_code in step.expected_status
        rec["ok"] = ok_status

        body_json: Optional[dict] = None
        try:
            body_json = resp.json()
        except Exception:
            body_json = None

        if body_json is not None and step.extract:
            for var, dotted in step.extract.items():
                val = _get_in(body_json, dotted)
                if val is not None:
                    ctx[var] = val

        # Include small response preview (avoid huge)
        rec["response_preview"] = (resp.text or "")[:400]
        out["steps"].append(rec)

        if not ok_status:
            out["failed"] = rec
            break

    out["context"] = ctx
    return out


def render_markdown_e2e(meta: Dict[str, Any], out: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# API End-to-End Test Report")
    lines.append("")
    for k, v in meta.items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")
    lines.append("| Step | Method | HTTP | ok | elapsed (ms) | URL |")
    lines.append("|---|---:|---:|---:|---:|---|")
    for s in out.get("steps", []) or []:
        lines.append(
            "| "
            + f"{s.get('name','')} | {s.get('method','')} | {s.get('http','')} | {s.get('ok','')} | {s.get('elapsed_ms','')} | `{s.get('url','')}` |"
        )
    lines.append("")
    if out.get("failed"):
        lines.append("## Result")
        lines.append("")
        lines.append("- Status: `FAILED`")
        lines.append(f"- Failed step: `{out['failed'].get('name','')}`")
    else:
        lines.append("## Result")
        lines.append("")
        lines.append("- Status: `PASSED`")
    lines.append("")
    return "\n".join(lines)


def render_markdown_perf(meta: Dict[str, Any], results: List[PerfResult]) -> str:
    lines: List[str] = []
    lines.append("# API Endpoint Performance Report")
    lines.append("")
    for k, v in meta.items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")
    lines.append("| Endpoint | Method | HTTP | p50 (ms) | p95 (ms) | avg (ms) | max (ms) | bytes | Notes |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---|")
    for r in results:
        lines.append(
            "| "
            + f"{r.name} (`{r.url}`) | {r.method} | {r.http} | "
            + f"{_fmt(r.p50_ms)} | {_fmt(r.p95_ms)} | {_fmt(r.avg_ms)} | {_fmt(r.max_ms)} | {r.bytes or '-'} | {r.notes} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_latex_perf(results: List[PerfResult]) -> str:
    # LaTeX-safe escaping for table text.
    def esc(s: str) -> str:
        return (
            s.replace("\\", "\\textbackslash{}")
            .replace("_", "\\_")
            .replace("%", "\\%")
            .replace("&", "\\&")
            .replace("#", "\\#")
        )

    lines: List[str] = []
    lines.append("% Auto-generated by api_test_runner.py")
    lines.append("\\subsection{Latest Performance Results}")
    lines.append("\\begin{longtable}{@{}p{0.34\\textwidth}p{0.07\\textwidth}p{0.07\\textwidth}rrrrp{0.26\\textwidth}@{}}");
    lines.append("\\toprule")
    lines.append("Endpoint & M & HTTP & p50 & p95 & avg & max & Notes\\\\")
    lines.append("\\midrule")
    for r in results:
        lines.append(
            f"{esc(r.name)} & {esc(r.method)} & {esc(r.http)} & "
            f"{_fmt_num(r.p50_ms)} & {_fmt_num(r.p95_ms)} & {_fmt_num(r.avg_ms)} & {_fmt_num(r.max_ms)} & {esc((r.notes or '')[:120])}\\\\"
        )
    lines.append("\\bottomrule")
    lines.append("\\end{longtable}")
    lines.append("")
    lines.append("\\textit{Units: milliseconds (ms). Percentiles are computed across samples per endpoint.}")
    lines.append("")
    return "\n".join(lines) + "\n"


def render_latex_e2e(meta: Dict[str, Any], out: Dict[str, Any]) -> str:
    def esc(s: str) -> str:
        return (
            s.replace("\\", "\\textbackslash{}")
            .replace("_", "\\_")
            .replace("%", "\\%")
            .replace("&", "\\&")
            .replace("#", "\\#")
        )

    status = "FAILED" if out.get("failed") else "PASSED"

    lines: List[str] = []
    lines.append("% Auto-generated by api_test_runner.py")
    lines.append("\\section{API End-to-End Test Evidence}")
    lines.append("\\subsection{Run Metadata}")
    lines.append("\\begin{itemize}")
    for k, v in meta.items():
        lines.append(f"  \\item {esc(str(k))}: \\texttt{{{esc(str(v))}}}")
    lines.append(f"  \\item Result: \\textbf{{{status}}}")
    lines.append("\\end{itemize}")
    lines.append("")

    lines.append("\\subsection{Step Results}")
    lines.append("\\begin{longtable}{@{}p{0.44\\textwidth}p{0.08\\textwidth}p{0.07\\textwidth}p{0.07\\textwidth}r@{}}")
    lines.append("\\toprule")
    lines.append("Step & M & HTTP & OK & ms\\\\")
    lines.append("\\midrule")
    for s in out.get("steps", []) or []:
        lines.append(
            f"{esc(str(s.get('name','')))} & {esc(str(s.get('method','')))} & {esc(str(s.get('http','')))} & {esc(str(s.get('ok','')))} & {esc(str(s.get('elapsed_ms','')))}\\\\"
        )
    lines.append("\\bottomrule")
    lines.append("\\end{longtable}")
    lines.append("")
    return "\n".join(lines) + "\n"


def _fmt(x: Optional[float]) -> str:
    if x is None:
        return "-"
    return f"{x:.1f}"


def _fmt_num(x: Optional[float]) -> str:
    if x is None:
        return "-"
    return f"{x:.1f}"


def load_manifest(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--mode", choices=["perf", "e2e"], required=True)
    ap.add_argument("--token", default=os.getenv("TOKEN", ""))
    ap.add_argument("--samples", type=int, default=10)
    ap.add_argument("--timeout", type=float, default=15.0)
    ap.add_argument("--sleep", type=float, default=0.05)
    default_perf_md = "ops/performance/reports/endpoint_performance.md"
    default_perf_json = "ops/performance/reports/endpoint_performance.json"
    ap.add_argument("--out-md", default=default_perf_md)
    ap.add_argument("--out-json", default=default_perf_json)
    default_perf_tex = "ops/security/overleaf/sections/12-api-performance-results.tex"
    ap.add_argument("--out-tex", default=default_perf_tex)
    ap.add_argument("--flow", default="core_smoke")
    ap.add_argument("--allow-destructive", action="store_true", help="Allow dangerous endpoints/steps (DELETE, admin mutations)")
    ap.add_argument(
        "--readonly",
        action="store_true",
        help="Perf mode only: only run safe read-only methods (GET/HEAD/OPTIONS)",
    )
    ap.add_argument(
        "--include-parameterized",
        action="store_true",
        help="Perf mode only: include parameterized endpoints like /resource/<id>/ (default skips them)",
    )

    args = ap.parse_args()
    manifest = load_manifest(args.manifest)

    token = args.token.strip() or None
    auth = manifest.get("auth") or {}
    if not token and auth.get("email") and auth.get("password"):
        token = _login(args.base_url, auth["email"], auth["password"], timeout_s=float(args.timeout))

    started_at = datetime.now(timezone.utc).isoformat()

    if args.mode == "perf":
        # Safety: the auto-exported manifest is often used for exploratory runs.
        # Avoid overwriting the Overleaf evidence table unless explicitly requested.
        if ("_full" in os.path.basename(args.manifest)) and (args.out_tex == default_perf_tex):
            args.out_tex = "ops/performance/reports/endpoint_performance_full_readonly.tex"

        endpoints_raw = manifest.get("endpoints", [])
        endpoints = [
            ManifestEndpoint(
                name=e["name"],
                method=e.get("method", "GET"),
                path=e["path"],
                auth=bool(e.get("auth", True)),
                params=e.get("params"),
                json=e.get("json"),
                expected_status=e.get("expected_status"),
                notes=e.get("notes", ""),
                dangerous=bool(e.get("dangerous", False)),
            )
            for e in endpoints_raw
        ]

        if not args.allow_destructive:
            endpoints = [e for e in endpoints if not e.dangerous]

        if args.readonly:
            endpoints = [e for e in endpoints if str(e.method).upper() in {"GET", "HEAD", "OPTIONS"}]

        if not args.include_parameterized:
            endpoints = [e for e in endpoints if "<" not in e.path and ">" not in e.path]

        results = run_perf(
            base_url=args.base_url,
            token=token,
            endpoints=endpoints,
            samples=int(args.samples),
            timeout_s=float(args.timeout),
            sleep_s=float(args.sleep),
        )

        meta = {
            "Base URL": args.base_url,
            "Started": started_at,
            "Samples per endpoint": int(args.samples),
            "Timeout (s)": float(args.timeout),
            "Sleep (s)": float(args.sleep),
        }
        md = render_markdown_perf(meta, results)
        os.makedirs(os.path.dirname(args.out_md), exist_ok=True)
        with open(args.out_md, "w", encoding="utf-8") as f:
            f.write(md)

        payload = {"meta": meta, "results": [asdict(r) for r in results]}
        os.makedirs(os.path.dirname(args.out_json), exist_ok=True)
        with open(args.out_json, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        tex = render_latex_perf(results)
        os.makedirs(os.path.dirname(args.out_tex), exist_ok=True)
        with open(args.out_tex, "w", encoding="utf-8") as f:
            f.write(tex)

        print(f"Wrote: {args.out_md}")
        print(f"Wrote: {args.out_json}")
        print(f"Wrote: {args.out_tex}")
        return 0

    # E2E mode
    flows = manifest.get("flows") or {}
    steps_raw = flows.get(args.flow)
    if not steps_raw:
        raise SystemExit(f"Flow not found in manifest: {args.flow}")

    if args.out_md == default_perf_md:
        args.out_md = f"ops/performance/reports/e2e_{args.flow}.md"
    if args.out_json == default_perf_json:
        args.out_json = f"ops/performance/reports/e2e_{args.flow}.json"
    if args.out_tex == default_perf_tex:
        args.out_tex = "ops/security/overleaf/sections/13-api-e2e-results.tex"

    steps = [
        ManifestStep(
            name=s["name"],
            method=s.get("method", "GET"),
            path=s["path"],
            auth=bool(s.get("auth", True)),
            params=s.get("params"),
            json=s.get("json"),
            multipart=s.get("multipart"),
            expected_status=s.get("expected_status"),
            extract=s.get("extract"),
        )
        for s in steps_raw
    ]

    out = run_e2e_flow(args.base_url, token, steps, timeout_s=float(args.timeout))
    meta = {
        "Base URL": args.base_url,
        "Started": started_at,
        "Flow": args.flow,
        "Timeout (s)": float(args.timeout),
    }
    md = render_markdown_e2e(meta, out)
    os.makedirs(os.path.dirname(args.out_md), exist_ok=True)
    with open(args.out_md, "w", encoding="utf-8") as f:
        f.write(md)

    tex = render_latex_e2e(meta, out)
    os.makedirs(os.path.dirname(args.out_tex), exist_ok=True)
    with open(args.out_tex, "w", encoding="utf-8") as f:
        f.write(tex)
    os.makedirs(os.path.dirname(args.out_json), exist_ok=True)
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    print(f"Wrote E2E results MD: {args.out_md}")
    print(f"Wrote E2E results TEX: {args.out_tex}")
    print(f"Wrote E2E results JSON: {args.out_json}")
    if out.get("failed"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
