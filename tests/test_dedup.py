import json
import pytest
from pathlib import Path
from fuzion.dedup import deduplicate, dedup_summary, _normalize_detail


# test that variable parts of error messages get stripped out
def test_normalize_detail_strips_ports():
    assert ":<port>" in _normalize_detail("http://127.0.0.1:62783/test.html")

def test_normalize_detail_strips_filenames():
    assert "/<file>.html" in _normalize_detail("/evil_timeout.html")


# test dedup with fake results
@pytest.fixture
def fake_results(tmp_path):
    results = {
        "results": [
            {"testcase_id": "test_001", "status": "ok", "detail": "loaded", "elapsed_ms": 500},
            {"testcase_id": "test_002", "status": "crash", "detail": "page crash event", "elapsed_ms": 1500},
            {"testcase_id": "test_003", "status": "crash", "detail": "page crash event", "elapsed_ms": 1600},
            {"testcase_id": "test_004", "status": "timeout", "detail": "Timeout 10000ms exceeded", "elapsed_ms": 10000},
            {"testcase_id": "test_005", "status": "crash", "detail": "out of memory", "elapsed_ms": 7000},
        ]
    }
    path = tmp_path / "results.json"
    path.write_text(json.dumps(results))
    return path


# two crashes with same message should be grouped together
def test_dedup_groups_same_crashes(fake_results):
    groups = deduplicate(fake_results)
    crash_group = [k for k in groups if k.startswith("crash:page crash event")]
    assert len(crash_group) == 1
    assert len(groups[crash_group[0]]) == 2


# different error messages should be separate groups
def test_dedup_separates_different_errors(fake_results):
    groups = deduplicate(fake_results)
    assert len(groups) == 3  # 2 crash types + 1 timeout


# ok results should be excluded
def test_dedup_excludes_ok(fake_results):
    groups = deduplicate(fake_results)
    for key in groups:
        assert not key.startswith("ok:")


# summary should have correct counts
def test_dedup_summary_counts(fake_results):
    summary = dedup_summary(fake_results)
    assert summary["total_failures"] == 4
    assert summary["unique_types"] == 3
    assert len(summary["groups"]) == 3
