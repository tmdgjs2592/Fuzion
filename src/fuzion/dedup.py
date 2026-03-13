"""
Deduplication module for Fuzion error findings.

Many failures may be caused by the same underlying bug.
This file does two things:
  1. Classifies each failing HTML file by scanning its content for
     known crash/hang patterns (e.g. deep nesting, infinite loops).
  2. Groups failures by their root cause so we know how many unique
     bug types were found, not just how many total failures there are.
"""

import re
import json
import platform
import sys
from pathlib import Path
from collections import defaultdict

try:
    from FTB.ProgramConfiguration import ProgramConfiguration
    from FTB.Signatures.CrashInfo import CrashInfo

    _FUZZMANAGER_AVAILABLE = True
except Exception:
    ProgramConfiguration = None
    CrashInfo = None
    _FUZZMANAGER_AVAILABLE = False

# ---------------------------------------------------------------------------
# Root cause classification
# ---------------------------------------------------------------------------
# Read an HTML file and check for known patterns that cause browsers to
# crash, hang, or timeout. Returns a short label describing the root cause.
# Checks are ordered from most specific to least specific — first match wins.
def classify_html(html_path: Path) -> str:
    if not html_path.exists() or not html_path.is_file():
        return "unknown"

    content = html_path.read_text(errors="ignore")

    # check for JS patterns that allocate huge amounts of memory
    # e.g. new Array(999999999), "a".repeat(999999), large buffer allocations
    if re.search(r"new\s+Array\s*\(\s*\d{6,}", content):
        return "memory_exhaustion"
    if re.search(r"\.repeat\s*\(\s*\d{6,}", content):
        return "memory_exhaustion"
    if re.search(r"new\s+ArrayBuffer\s*\(\s*\d{6,}", content):
        return "memory_exhaustion"

    # check for infinite loops in JS — these cause timeouts/hangs
    # e.g. while(true), for(;;), while(1)
    if re.search(r"while\s*\(\s*true\s*\)", content):
        return "infinite_js_loop"
    if re.search(r"for\s*\(\s*;\s*;\s*\)", content):
        return "infinite_js_loop"
    if re.search(r"while\s*\(\s*1\s*\)", content):
        return "infinite_js_loop"

    # check for JS that dynamically creates deep nesting via loops
    # e.g. for(var i=0; i<50000; i++) { createElement("div"); el.appendChild(child); el = child }
    if re.search(r"createElement", content) and re.search(r"appendChild", content):
        # look for a loop that nests elements by reassigning the parent
        # pattern: el = child or parent = child inside a loop with a high iteration count
        if re.search(r"for\s*\(.*\d{3,}", content):
            return "deep_dom_nesting"

    # check for deeply nested DOM elements in the raw HTML itself
    # simple heuristic: count max tag nesting depth
    depth = _estimate_max_nesting(content)
    if depth > 80:
        return "deep_dom_nesting"

    # check for recursive JS functions that call themselves (stack overflow)
    # e.g. function f(){return f()} f()
    if re.search(r"function\s+(\w+)\s*\([^)]*\)\s*\{[^}]*\1\s*\(", content):
        return "js_recursion"

    # check for use-after-free patterns — remove element then access it
    if re.search(r"removeChild", content) and re.search(r"\.style|\.appendChild|\.textContent", content):
        if re.search(r"innerHTML\s*=\s*['\"]", content):
            return "use_after_free"

    # no known pattern matched
    return "unknown"


# count the deepest nesting level in the HTML by tracking open/close tags.
# this is a rough estimate — not a full parser, just good enough to catch
# files with 100+ levels of nested divs/sections/etc.
def _estimate_max_nesting(html: str) -> int:
    depth = 0
    max_depth = 0
    # find all opening and closing tags
    for match in re.finditer(r"<(/?)(\w+)[\s>]", html):
        is_close = match.group(1) == "/"
        tag = match.group(2).lower()
        # skip self-closing / void tags
        if tag in {"img", "input", "br", "hr", "meta", "link", "area",
                    "base", "col", "embed", "source", "track", "wbr"}:
            continue
        if is_close:
            depth = max(0, depth - 1)
        else:
            depth += 1
            max_depth = max(max_depth, depth)
    return max_depth

# Grouping logic

# utility: strip variable parts of error messages (URLs, ports, file paths)
# kept for display/logging — grouping now uses root cause labels instead
def _normalize_detail(detail: str) -> str:
    detail = re.sub(r":\d{4,5}", ":<port>", detail) # remove port numbers
    detail = re.sub(r"/[\w\-]+\.html", "/<file>.html", detail) # remove file names
    detail = re.sub(r"/[\w/\-\.]+\.html", "/<path>.html", detail) # remove full file paths
    return detail.strip()


# create the grouping key for a failure.
# now uses root cause label from HTML analysis instead of just the error message.
# this means two crashes with the same root cause (e.g. both from deep nesting)
# get grouped together, even if the browser's error message was generic.
def _make_group_key(result: dict) -> str:
    status = result["status"]
    root_cause = result.get("root_cause", "unknown")
    return f"{status}:{root_cause}"


def _fuzzmanager_platform() -> str:
    machine = platform.machine().lower()
    if "arm" in machine or "aarch" in machine:
        return "arm64"
    if "64" in machine:
        return "x86-64"
    return "x86"


def _fuzzmanager_os() -> str:
    if sys.platform.startswith("darwin"):
        return "macosx"
    if sys.platform.startswith("win"):
        return "windows"
    return "linux"


def _read_failure_meta(results_path: Path, testcase_id: str) -> dict:
    meta_path = results_path.parent / "findings" / testcase_id / "meta.json"
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text())
    except Exception:
        return {}


def _read_log_tail(path: Path, *, max_bytes: int = 200_000) -> str:
    if not path.exists() or not path.is_file():
        return ""
    try:
        with path.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            start = max(0, size - max_bytes)
            f.seek(start)
            data = f.read()
    except Exception:
        return ""

    text = data.decode(errors="ignore").strip()
    if not text:
        return ""
    if start > 0:
        return "[truncated native log]\n" + text
    return text


def _collect_failure_text(result: dict, meta: dict) -> str:
    parts: list[str] = []

    detail = result.get("detail")
    if isinstance(detail, str) and detail.strip():
        parts.append(detail.strip())

    meta_detail = meta.get("detail")
    if isinstance(meta_detail, str) and meta_detail.strip():
        parts.append(meta_detail.strip())

    js_errors = meta.get("js_errors", [])
    if isinstance(js_errors, list):
        for entry in js_errors:
            if isinstance(entry, dict):
                for key in ("stack", "message", "text"):
                    val = entry.get(key)
                    if isinstance(val, str) and val.strip():
                        parts.append(val.strip())
            elif isinstance(entry, str) and entry.strip():
                parts.append(entry.strip())

    native_log_path = meta.get("native_log_path")
    if isinstance(native_log_path, str) and native_log_path.strip():
        native_log_file = Path(native_log_path.strip())
        native_log_text = _read_log_tail(native_log_file)
        if not native_log_text:
            fallback = native_log_file.parent / "user-data-dir" / "Default" / "chrome_debug.log"
            native_log_text = _read_log_tail(fallback)
        if native_log_text:
            parts.append(native_log_text)

    return "\n".join(parts)


def _build_synthetic_fuzzmanager_input(result: dict, meta: dict) -> str | None:
    """
    Build a compact assertion-like line from existing failure metadata.

    This lets FuzzManager create stable signatures even when we only have
    Playwright timeout/crash detail text (no native stacks/sanitizer output).
    """
    candidates: list[str] = []

    for key in ("detail",):
        val = result.get(key)
        if isinstance(val, str) and val.strip():
            candidates.append(val.strip())

    for key in ("detail",):
        val = meta.get(key)
        if isinstance(val, str) and val.strip():
            candidates.append(val.strip())

    js_errors = meta.get("js_errors", [])
    if isinstance(js_errors, list):
        for entry in js_errors:
            if isinstance(entry, dict):
                for key in ("message", "text", "stack"):
                    val = entry.get(key)
                    if isinstance(val, str) and val.strip():
                        candidates.append(val.strip())
                        break
            elif isinstance(entry, str) and entry.strip():
                candidates.append(entry.strip())

    for raw in candidates:
        # Use the first line only to avoid volatile call-log tails.
        line = raw.splitlines()[0].strip()
        if not line:
            continue
        # Playwright detail strings often contain escaped newlines/quotes from repr().
        line = line.replace("\\n", " ").replace('\\"', '"')
        line = _normalize_detail(line)
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            continue
        if len(line) > 200:
            line = line[:200]
        return f"Assertion failure: {line}"

    return None


def _fuzzmanager_signature_from_text(text: str) -> str | None:
    if not _FUZZMANAGER_AVAILABLE or not text.strip():
        return None

    try:
        cfg = ProgramConfiguration("fuzion", _fuzzmanager_platform(), _fuzzmanager_os())
        crash_info = CrashInfo.fromRawCrashData("", text, cfg)
        short_sig = crash_info.createShortSignature()
        if short_sig and short_sig != "No crash detected":
            return short_sig
    except Exception:
        return None

    return None


def _resolve_root_cause(result: dict, results_path: Path) -> tuple[str, str]:
    testcase_id = result.get("testcase_id", "")
    meta = _read_failure_meta(results_path, testcase_id)
    fm_text = _collect_failure_text(result, meta)
    fm_signature = _fuzzmanager_signature_from_text(fm_text)
    if fm_signature:
        return f"fuzzmanager:{fm_signature}", "fuzzmanager"

    if result.get("status") in {"timeout", "hang", "error"}:
        synthetic_fm_text = _build_synthetic_fuzzmanager_input(result, meta)
        if synthetic_fm_text:
            synthetic_signature = _fuzzmanager_signature_from_text(synthetic_fm_text)
            if synthetic_signature:
                return f"fuzzmanager:{synthetic_signature}", "fuzzmanager_synthetic"

    html_path = Path(result.get("testcase", ""))
    return classify_html(html_path), "heuristic"


# read results.json, classify each failing HTML file, and group by root cause.
# returns a dict where each key is a unique bug type (status:root_cause)
# and the value is a list of testcases that triggered it.
def deduplicate(results_path: Path) -> dict:
    data = json.loads(results_path.read_text())
    results = data["results"]

    failures = [r for r in results if r["status"] != "ok"]

    # classify each failure using FuzzManager signature if available, else HTML heuristics
    for f in failures:
        root_cause, source = _resolve_root_cause(f, results_path)
        f["root_cause"] = root_cause
        f["root_cause_source"] = source

    # group failures that have the same status + root cause
    groups = defaultdict(list)
    for f in failures:
        key = _make_group_key(f)
        groups[key].append({
            "testcase_id": f["testcase_id"],
            "elapsed_ms": f.get("elapsed_ms", 0),
            "detail": f.get("detail", ""),
            "root_cause": f["root_cause"],
        })

    return dict(groups)


# return a summary dict with total failures, unique types, and groups
def dedup_summary(results_path: Path) -> dict:
    groups = deduplicate(results_path)

    total_failures = sum(len(v) for v in groups.values())

    summary = {
        "total_failures": total_failures,
        "unique_types": len(groups),
        "groups": [],
    }

    # split the key back into status and root cause for display
    for key, testcases in groups.items():
        status, root_cause = key.split(":", 1)
        summary["groups"].append({
            "status": status,
            "root_cause": root_cause,
            "count": len(testcases),
            "testcases": testcases,
        })

    return summary


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    results_path = root / "out" / "results.json"

    if not results_path.exists():
        print("No results.json found. Run `fuzion` first.")
        exit(1)

    groups = deduplicate(results_path)

    if not groups:
        print("No failures found — nothing to deduplicate.")
    else:
        total = sum(len(v) for v in groups.values())
        print(f"{total} total failures → {len(groups)} unique type(s)\n")

        for key, testcases in groups.items():
            status, root_cause = key.split(":", 1)
            print(f"  [{status.upper()}] root cause: {root_cause}")
            print(f"    → {len(testcases)} testcase(s): {', '.join(t['testcase_id'] for t in testcases[:5])}")
            if len(testcases) > 5:
                print(f"      ... and {len(testcases) - 5} more")
            print()
