from __future__ import annotations

import json
from pathlib import Path

from fuzion.report import generate_report


def _write_results(out_dir: Path, payload: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(payload), encoding="utf-8")


def test_generate_report_escapes_failure_fields(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    _write_results(
        out_dir,
        {
            "results": [
                {
                    "testcase_id": "<script>alert(1)</script>",
                    "status": "error",
                    "detail": 'boom <b>bad</b> & "quote"',
                    "elapsed_ms": 42,
                }
            ]
        },
    )

    output_path = out_dir / "report.html"
    generate_report(out_dir=out_dir, output_path=output_path)
    html = output_path.read_text(encoding="utf-8")

    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "boom &lt;b&gt;bad&lt;/b&gt; &amp; &quot;quote&quot;" in html
    assert "<script>alert(1)</script>" not in html
    assert "boom <b>bad</b>" not in html


def test_generate_report_uses_safe_badge_for_unknown_status(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    _write_results(
        out_dir,
        {
            "results": [
                {
                    "testcase_id": "case_1",
                    "status": 'x" onmouseover="alert(1)',
                    "detail": "weird",
                    "elapsed_ms": 12,
                }
            ]
        },
    )

    output_path = out_dir / "report.html"
    generate_report(out_dir=out_dir, output_path=output_path)
    html = output_path.read_text(encoding="utf-8")

    assert 'class="badge unknown"' in html
    assert "onmouseover=" not in html
