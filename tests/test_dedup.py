import json
import pytest
from pathlib import Path
from fuzion.dedup import (
    deduplicate,
    dedup_summary,
    _normalize_detail,
    classify_html,
    _collect_failure_text,
)


# test that variable parts of error messages get stripped out
def test_normalize_detail_strips_ports():
    assert ":<port>" in _normalize_detail("http://127.0.0.1:62783/test.html")

def test_normalize_detail_strips_filenames():
    assert "/<file>.html" in _normalize_detail("/evil_timeout.html")


# ---------------------------------------------------------------------------
# classify_html tests — verify that HTML pattern matching works
# ---------------------------------------------------------------------------

# file with a huge Array allocation should be classified as memory_exhaustion
def test_classify_memory_exhaustion(tmp_path):
    f = tmp_path / "oom.html"
    f.write_text('<script>let x = new Array(999999999)</script>')
    assert classify_html(f) == "memory_exhaustion"

# file with while(true) should be classified as infinite_js_loop
def test_classify_infinite_loop(tmp_path):
    f = tmp_path / "loop.html"
    f.write_text('<script>while(true) {}</script>')
    assert classify_html(f) == "infinite_js_loop"

# file with 100+ nested divs should be classified as deep_dom_nesting
def test_classify_deep_nesting(tmp_path):
    f = tmp_path / "deep.html"
    f.write_text("<div>" * 120 + "</div>" * 120)
    assert classify_html(f) == "deep_dom_nesting"

# normal file should be classified as unknown (no bad patterns)
def test_classify_normal_file(tmp_path):
    f = tmp_path / "ok.html"
    f.write_text('<html><body><p>hello</p></body></html>')
    assert classify_html(f) == "unknown"

# missing file should be classified as unknown
def test_classify_missing_file(tmp_path):
    f = tmp_path / "nope.html"
    assert classify_html(f) == "unknown"


def test_collect_failure_text_includes_native_log(tmp_path):
    native_log = tmp_path / "chrome.log"
    native_log.write_text(
        "[1234:ERROR:example.cc(9)] native crash marker\nstack frame line",
        encoding="utf-8",
    )
    result = {"detail": "timeout detail"}
    meta = {"native_log_path": str(native_log)}

    text = _collect_failure_text(result, meta)

    assert "timeout detail" in text
    assert "native crash marker" in text
    assert "stack frame line" in text


def test_collect_failure_text_falls_back_to_chrome_debug_log(tmp_path):
    case_dir = tmp_path / "case_000010"
    debug_log = case_dir / "user-data-dir" / "Default" / "chrome_debug.log"
    debug_log.parent.mkdir(parents=True)
    debug_log.write_text("fallback native line", encoding="utf-8")

    result = {"detail": "timeout detail"}
    meta = {"native_log_path": str(case_dir / "chrome.log")}

    text = _collect_failure_text(result, meta)

    assert "timeout detail" in text
    assert "fallback native line" in text


# ---------------------------------------------------------------------------
# dedup grouping tests — now groups by root cause instead of error message
# ---------------------------------------------------------------------------

# create fake results with HTML files that have different root causes
@pytest.fixture
def fake_results(tmp_path):
    # create actual HTML files so classify_html can read them
    oom = tmp_path / "oom.html"
    oom.write_text('<script>let x = new Array(999999999)</script>')

    deep = tmp_path / "deep.html"
    deep.write_text("<div>" * 120 + "</div>" * 120)

    loop = tmp_path / "loop.html"
    loop.write_text('<script>while(true) {}</script>')

    results = {
        "results": [
            {"testcase_id": "test_001", "status": "ok", "testcase": str(tmp_path / "ok.html"), "detail": "loaded", "elapsed_ms": 500},
            {"testcase_id": "oom", "status": "crash", "testcase": str(oom), "detail": "page crash event", "elapsed_ms": 1500},
            {"testcase_id": "deep", "status": "crash", "testcase": str(deep), "detail": "page crash event", "elapsed_ms": 1600},
            {"testcase_id": "loop", "status": "timeout", "testcase": str(loop), "detail": "Timeout 10000ms exceeded", "elapsed_ms": 10000},
        ]
    }
    path = tmp_path / "results.json"
    path.write_text(json.dumps(results))
    return path


# two crashes with same error message but different HTML patterns
# should now be in separate groups (memory_exhaustion vs deep_dom_nesting)
def test_dedup_separates_by_root_cause(fake_results):
    groups = deduplicate(fake_results)
    crash_groups = [k for k in groups if k.startswith("crash:")]
    assert len(crash_groups) == 2  # memory_exhaustion and deep_dom_nesting

# ok results should still be excluded
def test_dedup_excludes_ok(fake_results):
    groups = deduplicate(fake_results)
    for key in groups:
        assert not key.startswith("ok:")

# summary should count 3 failures across 3 unique root causes
def test_dedup_summary_counts(fake_results):
    summary = dedup_summary(fake_results)
    assert summary["total_failures"] == 3
    assert summary["unique_types"] == 3

# each group should have a root_cause field
def test_dedup_summary_has_root_cause(fake_results):
    summary = dedup_summary(fake_results)
    for g in summary["groups"]:
        assert "root_cause" in g
        assert g["root_cause"] in ("memory_exhaustion", "deep_dom_nesting", "infinite_js_loop", "unknown")
