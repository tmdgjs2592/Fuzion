from __future__ import annotations

import json
from datetime import datetime, timezone
from html import escape
from pathlib import Path
import re


def _load_summary(campaign_dir: Path) -> dict:
    return json.loads((campaign_dir / "summary.json").read_text(encoding="utf-8"))


def _load_cases(campaign_dir: Path, generation: int) -> list[dict]:
    payload = json.loads((campaign_dir / f"gen_{generation:04d}" / "cases.json").read_text(encoding="utf-8"))
    return payload.get("cases", [])


def _load_meta(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_log_tail(path: Path, *, max_bytes: int = 200_000) -> str:
    if not path.is_file():
        return ""
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes))
            data = handle.read()
    except Exception:
        return ""
    return data.decode(errors="ignore").strip()


def _extract_asan_snippet(text: str) -> str:
    if not text:
        return ""
    start = max(text.rfind("ERROR: AddressSanitizer"), text.rfind("SUMMARY: AddressSanitizer"))
    if start >= 0:
        return text[start:].strip()
    match = re.search(r"(AddressSanitizer.*)", text, flags=re.DOTALL)
    return match.group(1).strip() if match else ""


def _evidence_for_case(campaign_dir: Path, case: dict) -> tuple[str, str]:
    finding_dir = Path(case.get("finding_dir") or campaign_dir / "findings" / case.get("case_id", ""))
    meta = _load_meta(finding_dir / "meta.json")
    native_log_path = Path(meta.get("native_log_path", "")) if meta.get("native_log_path") else (finding_dir / "chrome.log")
    native_log = _read_log_tail(native_log_path)
    asan = _extract_asan_snippet(native_log)
    js_errors = meta.get("js_errors", [])

    evidence_parts: list[str] = []
    if asan:
        evidence_parts.append(asan[:4000])
    elif native_log:
        evidence_parts.append(native_log[-2000:])

    if isinstance(js_errors, list):
        for entry in js_errors:
            if isinstance(entry, dict):
                for key in ("stack", "message", "text"):
                    value = entry.get(key)
                    if isinstance(value, str) and value.strip():
                        evidence_parts.append(value.strip())
                        break
            elif isinstance(entry, str) and entry.strip():
                evidence_parts.append(entry.strip())

    detail = meta.get("detail")
    if isinstance(detail, str) and detail.strip():
        evidence_parts.append(detail.strip())

    evidence = "\n\n".join(part for part in evidence_parts if part).strip()
    return evidence[:5000], str(native_log_path) if native_log_path else ""


def _detail_cell(campaign_dir: Path, case: dict) -> str:
    detail = str(case.get("detail", "")).strip()
    evidence, native_log_path = _evidence_for_case(campaign_dir, case)
    summary = escape((detail or evidence or "-")[:120], quote=True)

    pieces = []
    if detail:
        pieces.append(detail)
    if evidence and evidence != detail:
        pieces.append(evidence)
    body = "\n\n".join(pieces).strip()
    if not body:
        return summary

    extra = ""
    if native_log_path:
        extra = f"<div class='path'>{escape(native_log_path, quote=True)}</div>"
    return f"<details><summary>{summary}</summary>{extra}<pre>{escape(body, quote=True)}</pre></details>"


def _status_counts(generations: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for generation in generations:
        for status, count in generation.get("status_counts", {}).items():
            counts[status] = counts.get(status, 0) + count
    return counts


def _generation_cards(generations: list[dict]) -> str:
    cards = []
    for generation in generations:
        cards.append(
            f"""
            <div class="generation-card">
                <div class="generation-title">Generation {generation["generation"]}</div>
                <div class="generation-metric">cases: {generation["total_cases"]}</div>
                <div class="generation-metric">abnormal: {generation["abnormal_cases"]}</div>
                <div class="generation-metric">buckets: {generation["unique_buckets"]}</div>
                <div class="generation-metric">selection: {escape(str(generation.get("selection_mode") or '-'), quote=True)}</div>
            </div>"""
        )
    return "".join(cards)


def _failure_rows(campaign_dir: Path, generations: list[dict]) -> str:
    rows = []
    for generation in generations:
        for case in _load_cases(campaign_dir, generation["generation"]):
            status = str(case.get("status", "unknown"))
            if status == "ok":
                continue
            rows.append(
                f"""
                <tr>
                    <td>{generation["generation"]}</td>
                    <td>{escape(str(case.get("case_id", "")), quote=True)}</td>
                    <td><span class="badge {escape(status, quote=True)}">{escape(status.upper(), quote=True)}</span></td>
                    <td>{escape(str(case.get("root_cause", "unknown")).replace("_", " "), quote=True)}</td>
                    <td>{escape(str(case.get("signal", "unknown")), quote=True)}</td>
                    <td>{escape(str(case.get("mutator", "")) or "-", quote=True)}</td>
                    <td>{_detail_cell(campaign_dir, case)}</td>
                </tr>"""
            )
    if not rows:
        return "<p class='empty-state'>No abnormal cases were recorded.</p>"
    return (
        "<table><thead><tr><th>Gen</th><th>Case</th><th>Status</th><th>Root Cause</th>"
        "<th>Signal</th><th>Mutator</th><th>Detail</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def generate_campaign_report(campaign_dir: Path, output_path: Path | None = None) -> Path:
    summary = _load_summary(campaign_dir)
    generations = summary.get("generations", [])
    counts = _status_counts(generations)
    output_path = output_path or (campaign_dir / "report.html")
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    html = f"""<!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Fuzion Campaign Report</title>
        <style>
            * {{ box-sizing: border-box; }}
            body {{ margin: 0; padding: 32px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; }}
            h1, h2 {{ margin: 0 0 12px; }}
            .subtitle {{ color: #94a3b8; margin-bottom: 28px; }}
            .cards, .generation-grid {{ display: grid; gap: 16px; }}
            .cards {{ grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); margin-bottom: 28px; }}
            .generation-grid {{ grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); margin-bottom: 28px; }}
            .card, .generation-card {{ background: #1e293b; border-radius: 12px; padding: 18px; }}
            .card-number {{ font-size: 2rem; font-weight: 700; }}
            .card-label, .generation-metric {{ color: #94a3b8; margin-top: 4px; }}
            .generation-title {{ font-size: 1.1rem; font-weight: 700; margin-bottom: 8px; }}
            table {{ width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 12px; overflow: hidden; }}
            th {{ background: #334155; text-align: left; padding: 12px 14px; font-size: 0.82rem; text-transform: uppercase; color: #94a3b8; }}
            td {{ padding: 12px 14px; border-top: 1px solid #334155; vertical-align: top; }}
            details {{ cursor: pointer; }}
            details pre {{ margin-top: 10px; white-space: pre-wrap; word-break: break-word; font-family: ui-monospace, SFMono-Regular, monospace; font-size: 0.82rem; color: #cbd5e1; }}
            .path {{ margin-top: 10px; color: #67e8f9; font-family: ui-monospace, SFMono-Regular, monospace; font-size: 0.78rem; }}
            .badge {{ display: inline-block; border-radius: 999px; padding: 4px 10px; font-size: 0.8rem; font-weight: 700; }}
            .badge.ok {{ background: #14532d; color: #86efac; }}
            .badge.crash {{ background: #7f1d1d; color: #fca5a5; }}
            .badge.timeout {{ background: #78350f; color: #fcd34d; }}
            .badge.hang {{ background: #7c2d12; color: #fdba74; }}
            .badge.error {{ background: #4c1d95; color: #c4b5fd; }}
            .badge.unknown {{ background: #1f2937; color: #d1d5db; }}
            .empty-state {{ background: #1e293b; border-radius: 12px; padding: 24px; color: #86efac; }}
        </style>
    </head>
    <body>
        <h1>Campaign: {escape(summary.get("campaign_name", "unknown"), quote=True)}</h1>
        <p class="subtitle">Generated {generated_at}</p>
        <div class="cards">
            <div class="card"><div class="card-number">{summary.get("total_cases", 0)}</div><div class="card-label">Total Cases</div></div>
            <div class="card"><div class="card-number">{summary.get("abnormal_cases", 0)}</div><div class="card-label">Abnormal Cases</div></div>
            <div class="card"><div class="card-number">{summary.get("unique_buckets", 0)}</div><div class="card-label">Unique Buckets</div></div>
            <div class="card"><div class="card-number">{counts.get("crash", 0)}</div><div class="card-label">Crashes</div></div>
            <div class="card"><div class="card-number">{counts.get("hang", 0)}</div><div class="card-label">Hangs</div></div>
            <div class="card"><div class="card-number">{counts.get("timeout", 0)}</div><div class="card-label">Timeouts</div></div>
            <div class="card"><div class="card-number">{counts.get("error", 0)}</div><div class="card-label">Errors</div></div>
        </div>
        <h2>Generations</h2>
        <div class="generation-grid">{_generation_cards(generations)}</div>
        <h2>Abnormal Cases</h2>
        {_failure_rows(campaign_dir, generations)}
    </body>
    </html>"""

    output_path.write_text(html, encoding="utf-8")
    return output_path
