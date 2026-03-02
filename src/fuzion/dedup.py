"""
Deduplication module for Fuzion error findings,
many failures may be caused by the same underlying
bug. This file groups failures by their status and error message to
identify how many unique bug types were found.
"""

import re
import json
from pathlib import Path
from collections import defaultdict


# Parsing:
# strip out variable parts of error messages (URLs, ports, file paths) so that the same type of error groups together regardless of
# which specific testcase triggered it
def _normalize_detail(detail: str) -> str:
    detail = re.sub(r":\d{4,5}", ":<port>", detail) # remove port numbers
    detail = re.sub(r"/[\w\-]+\.html", "/<file>.html", detail) # remove file names
    detail = re.sub(r"/[\w/\-\.]+\.html", "/<path>.html", detail) # remove full file paths
    return detail.strip()

# create a unique key for each failure based on status + normalized error message
# two failures with the same key are considered the same bug type
def _make_group_key(result: dict) -> str:
    status = result["status"]
    detail = _normalize_detail(result.get("detail", ""))
    return f"{status}:{detail}"

# read results.json and group failures by their error signature
# returns a dict where each key is a unique bug type and the value
# is a list of testcase IDs that triggered it
def deduplicate(results_path: Path) -> dict:
    data = json.loads(results_path.read_text())
    results = data["results"]

    failures = [r for r in results if r["status"] != "ok"] # only look at failures, skip ok results

    # group failures that have the same status + error message
    groups = defaultdict(list)
    for f in failures:
        key = _make_group_key(f)
        groups[key].append({
            "testcase_id": f["testcase_id"],
            "elapsed_ms": f.get("elapsed_ms", 0),
            "detail": f.get("detail", ""),
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

    for key, testcases in groups.items():
        status, detail = key.split(":", 1)
        summary["groups"].append({
            "status": status,
            "detail": detail,
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
            status, detail = key.split(":", 1)
            print(f"  [{status.upper()}] {detail[:80]}")
            print(f"    → {len(testcases)} testcase(s): {', '.join(t['testcase_id'] for t in testcases[:5])}")
            if len(testcases) > 5:
                print(f"      ... and {len(testcases) - 5} more")
            print()
