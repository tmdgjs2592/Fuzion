from __future__ import annotations

import hashlib
import re
from pathlib import Path


_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "source",
    "track",
    "wbr",
}


def _estimate_max_nesting(html: str) -> int:
    depth = 0
    max_depth = 0
    for match in re.finditer(r"<(/?)([a-zA-Z][\w:-]*)[\s>]", html):
        tag = match.group(2).lower()
        if tag in _VOID_TAGS:
            continue
        if match.group(1):
            depth = max(0, depth - 1)
        else:
            depth += 1
            max_depth = max(max_depth, depth)
    return max_depth


def extract_features_from_text(content: str) -> dict:
    return {
        "html_size_bytes": len(content.encode("utf-8")),
        "script_count": len(re.findall(r"<script\b", content, flags=re.IGNORECASE)),
        "style_count": len(re.findall(r"<style\b", content, flags=re.IGNORECASE)),
        "max_nesting": _estimate_max_nesting(content),
        "has_large_allocation": bool(
            re.search(r"new\s+Array\s*\(\s*\d{6,}", content)
            or re.search(r"\.repeat\s*\(\s*\d{6,}", content)
            or re.search(r"new\s+ArrayBuffer\s*\(\s*\d{6,}", content)
        ),
        "has_infinite_loop": bool(
            re.search(r"while\s*\(\s*(?:true|1)\s*\)", content)
            or re.search(r"for\s*\(\s*;\s*;\s*\)", content)
        ),
        "has_dom_append_chain": bool(
            re.search(r"createElement", content)
            and re.search(r"appendChild", content)
            and re.search(r"for\s*\(.*\d{3,}", content)
        ),
    }


def extract_features(html_path: Path) -> dict:
    if not html_path.is_file():
        return extract_features_from_text("")
    return extract_features_from_text(html_path.read_text(errors="ignore"))


def root_cause(features: dict) -> str:
    if features["has_large_allocation"]:
        return "memory_exhaustion"
    if features["has_infinite_loop"]:
        return "infinite_js_loop"
    if features["has_dom_append_chain"] or features["max_nesting"] > 80:
        return "deep_dom_nesting"
    return "unknown"


def normalize_detail(detail: str) -> str:
    detail = re.sub(r":\d{4,5}", ":<port>", detail)
    detail = re.sub(r"/[\w/\-\.]+\.html", "/<path>.html", detail)
    detail = re.sub(r"\b\d{4,}ms\b", "<ms>", detail)
    detail = re.sub(r"\b\d{4,}\b", "<n>", detail)
    return detail.strip()


def bucket_for_path(html_path: Path, *, status: str, detail: str, signal: str = "") -> dict:
    features = extract_features(html_path)
    cause = root_cause(features)
    parts = [status, signal or "unknown", cause]
    normalized = normalize_detail(detail)
    if cause == "unknown" and normalized:
        parts.append(normalized)
    bucket_key = "|".join(parts)
    bucket_id = hashlib.sha256(bucket_key.encode("utf-8")).hexdigest()[:12]
    return {
        "bucket_id": bucket_id,
        "bucket_key": bucket_key,
        "root_cause": cause,
        "features": features,
    }


def summarize_generation(records: list[dict]) -> dict:
    status_counts: dict[str, int] = {}
    mutator_counts: dict[str, int] = {}
    bucket_counts: dict[str, int] = {}
    abnormal_cases = 0

    for record in records:
        status = record["status"]
        status_counts[status] = status_counts.get(status, 0) + 1
        if record.get("mutator"):
            mutator = record["mutator"]
            mutator_counts[mutator] = mutator_counts.get(mutator, 0) + 1
        if status != "ok":
            abnormal_cases += 1
            bucket_id = record["bucket_id"]
            bucket_counts[bucket_id] = bucket_counts.get(bucket_id, 0) + 1

    return {
        "total_cases": len(records),
        "abnormal_cases": abnormal_cases,
        "unique_buckets": len(bucket_counts),
        "status_counts": status_counts,
        "mutator_counts": mutator_counts,
        "bucket_counts": bucket_counts,
    }
