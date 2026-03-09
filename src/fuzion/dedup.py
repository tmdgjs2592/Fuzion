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
from pathlib import Path
from collections import defaultdict


# ---------------------------------------------------------------------------
# Root cause classification
# ---------------------------------------------------------------------------
# Read an HTML file and check for known patterns that cause browsers to
# crash, hang, or timeout. Returns a short label describing the root cause.
# Checks are ordered from most specific to least specific — first match wins.
def classify_html(html_path: Path) -> str:
    if not html_path.exists():
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


# read results.json, classify each failing HTML file, and group by root cause.
# returns a dict where each key is a unique bug type (status:root_cause)
# and the value is a list of testcases that triggered it.
def deduplicate(results_path: Path) -> dict:
    data = json.loads(results_path.read_text())
    results = data["results"]

    failures = [r for r in results if r["status"] != "ok"]

    # classify each failure by reading its HTML file
    for f in failures:
        html_path = Path(f.get("testcase", ""))
        f["root_cause"] = classify_html(html_path)

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
