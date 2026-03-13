from __future__ import annotations

import json
from pathlib import Path

from fuzion.campaign_report import generate_campaign_report


def test_generate_campaign_report_includes_crash_evidence(tmp_path: Path) -> None:
    campaign_dir = tmp_path / "campaign"
    finding_dir = campaign_dir / "findings" / "gen_0000_case_000001"
    gen_dir = campaign_dir / "gen_0000"
    finding_dir.mkdir(parents=True)
    gen_dir.mkdir(parents=True)

    (campaign_dir / "summary.json").write_text(
        json.dumps(
            {
                "campaign_name": "smoke",
                "total_cases": 1,
                "abnormal_cases": 1,
                "unique_buckets": 1,
                "generations": [
                    {
                        "generation": 0,
                        "total_cases": 1,
                        "abnormal_cases": 1,
                        "unique_buckets": 1,
                        "status_counts": {"crash": 1},
                        "selection_mode": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (gen_dir / "cases.json").write_text(
        json.dumps(
            {
                "generation": 0,
                "cases": [
                    {
                        "case_id": "gen_0000_case_000001",
                        "status": "crash",
                        "detail": "TargetClosedError",
                        "root_cause": "unknown",
                        "signal": "target_closed",
                        "mutator": "",
                        "finding_dir": str(finding_dir),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (finding_dir / "meta.json").write_text(
        json.dumps({"native_log_path": str(finding_dir / "chrome.log")}),
        encoding="utf-8",
    )
    (finding_dir / "chrome.log").write_text(
        "noise\nERROR: AddressSanitizer: heap-use-after-free on address 0x1\nstack\n",
        encoding="utf-8",
    )

    report_path = generate_campaign_report(campaign_dir)
    html = report_path.read_text(encoding="utf-8")

    assert "heap-use-after-free" in html
    assert "TargetClosedError" in html
    assert "gen_0000_case_000001" in html


def test_generate_campaign_report_handles_all_ok(tmp_path: Path) -> None:
    campaign_dir = tmp_path / "campaign"
    gen_dir = campaign_dir / "gen_0000"
    gen_dir.mkdir(parents=True)

    (campaign_dir / "summary.json").write_text(
        json.dumps(
            {
                "campaign_name": "clean",
                "total_cases": 1,
                "abnormal_cases": 0,
                "unique_buckets": 0,
                "generations": [
                    {
                        "generation": 0,
                        "total_cases": 1,
                        "abnormal_cases": 0,
                        "unique_buckets": 0,
                        "status_counts": {"ok": 1},
                        "selection_mode": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (gen_dir / "cases.json").write_text(json.dumps({"generation": 0, "cases": []}), encoding="utf-8")

    html = generate_campaign_report(campaign_dir).read_text(encoding="utf-8")

    assert "No abnormal cases were recorded." in html
