import json
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from html import escape
from .dedup import classify_html, dedup_summary

logger = logging.getLogger(__name__)


def generate_report(out_dir: Path, output_path: Path) -> None:
    logger.debug("generate_report called: out_dir=%s, output_path=%s", out_dir, output_path)
    results_file = out_dir / "results.json"
    logger.debug("Looking for results file at %s", results_file)
    if not results_file.exists():
        logger.debug("results.json not found at %s, aborting report generation", results_file)
        print("No results.json found. Run `fuzion` first.")
        return

    data = json.loads(results_file.read_text())
    results = data["results"]
    logger.debug("Loaded %d result(s) from %s", len(results), results_file)

    counts = {"ok": 0, "crash": 0, "timeout": 0, "hang": 0, "error": 0}
    for r in results:
        status = r.get("status", "unknown")
        if status in counts:
            counts[status] += 1
    logger.debug("Status counts: ok=%d, crash=%d, timeout=%d, hang=%d, error=%d", counts["ok"], counts["crash"], counts["timeout"], counts["hang"], counts["error"])

    table_rows = ""
    pst = timezone(timedelta(hours=-8))
    failures = [r for r in results if r.get("status") != "ok"]
    logger.debug("Found %d non-ok result(s) to include in failure table", len(failures))
    for r in failures:
        status = str(r.get("status", "unknown"))
        status_class = status if status in counts else "unknown"
        status_class = escape(status_class, quote=True)
        detail = str(r.get("detail", ""))
        if len(detail) > 80:
            logger.debug("Truncating detail for testcase '%s' (original length %d)", r.get("testcase_id", ""), len(detail))
            detail = detail[:80] + "..."
        testcase_id = escape(str(r.get("testcase_id", "")), quote=True)
        elapsed = escape(str(r.get("elapsed_ms", 0)), quote=True)
        detail = escape(str(detail), quote=True)
        status_label = escape(status.upper(), quote=True)

        # classify the HTML file to get the root cause label
        testcase_path = r.get("testcase", "")
        root_cause = classify_html(Path(testcase_path)) if testcase_path else "unknown"
        root_cause_display = escape(root_cause.replace("_", " "), quote=True)
        logger.debug("Table row: testcase_id=%s, status=%s, root_cause=%s", testcase_id, status, root_cause)
        table_rows += f"""
        <tr>
            <td>{testcase_id}</td>
            <td><span class="badge {status_class}">{status_label}</span></td>
            <td><span class="root-cause">{root_cause_display}</span></td>
            <td>{elapsed}ms</td>
            <td>{detail}</td>
        </tr>"""

    total = len(results)
    logger.debug("Total testcases: %d", total)

    # build dedup summary section for the report
    ds = dedup_summary(results_file)
    if ds["unique_types"] > 0:
        dedup_html = f'<div class="dedup-section"><h2>Deduplication — {ds["total_failures"]} failure(s) → {ds["unique_types"]} unique type(s)</h2>'
        for g in ds["groups"]:
            status_upper = escape(g["status"].upper())
            root_cause_label = escape(g["root_cause"].replace("_", " "))
            count = g["count"]
            testcase_ids = ", ".join(escape(t["testcase_id"]) for t in g["testcases"][:5])
            more = f" ... and {count - 5} more" if count > 5 else ""
            dedup_html += f"""
            <div class="dedup-group">
                <div class="dedup-count">{count}x</div>
                <span class="badge {escape(g['status'])}">{status_upper}</span>
                <span class="dedup-label">{root_cause_label}</span>
                <span style="color:#94a3b8; font-size:0.8rem;">{testcase_ids}{more}</span>
            </div>"""
        dedup_html += "</div>"
    else:
        dedup_html = '<div class="dedup-section"><p class="dedup-none">No failures found — nothing to deduplicate.</p></div>'

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Fuzion Report</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; padding: 40px; }}
        h1 {{ font-size: 2rem; margin-bottom: 8px; }}
        .subtitle {{ color: #94a3b8; margin-bottom: 32px; }}
        .cards {{ display: flex; gap: 16px; margin-bottom: 40px; }}
        .card {{ background: #1e293b; border-radius: 12px; padding: 24px; flex: 1; text-align: center; }}
        .card .number {{ font-size: 2.5rem; font-weight: bold; }}
        .card .label {{ color: #94a3b8; margin-top: 4px; font-size: 0.9rem; text-transform: uppercase; }}
        .card.ok .number {{ color: #22c55e; }}
        .card.crash .number {{ color: #ef4444; }}
        .card.timeout .number {{ color: #f59e0b; }}
        .card.hang .number {{ color: #f97316; }}
        .card.error .number {{ color: #a78bfa; }}
        .card.total .number {{ color: #38bdf8; }}
        table {{ width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 12px; overflow: hidden; }}
        th {{ background: #334155; text-align: left; padding: 14px 16px; font-size: 0.85rem; text-transform: uppercase; color: #94a3b8; }}
        td {{ padding: 12px 16px; border-top: 1px solid #334155; }}
        tr:hover {{ background: #253044; }}
        .badge {{ padding: 4px 12px; border-radius: 20px; font-size: 0.8rem; font-weight: 600; }}
        .badge.ok {{ background: #14532d; color: #86efac; }}
        .badge.crash {{ background: #7f1d1d; color: #fca5a5; }}
        .badge.timeout {{ background: #78350f; color: #fcd34d; }}
        .badge.hang {{ background: #7c2d12; color: #fdba74; }}
        .badge.error {{ background: #4c1d95; color: #c4b5fd; }}
        .badge.unknown {{ background: #1f2937; color: #d1d5db; }}
        .root-cause {{ color: #67e8f9; font-family: monospace; font-size: 0.85rem; }}
        h2 {{ font-size: 1.4rem; margin-bottom: 16px; margin-top: 8px; }}
        .dedup-section {{ background: #1e293b; border-radius: 12px; padding: 24px; margin-bottom: 40px; }}
        .dedup-group {{ display: flex; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px solid #334155; }}
        .dedup-group:last-child {{ border-bottom: none; }}
        .dedup-count {{ font-size: 1.5rem; font-weight: bold; color: #38bdf8; min-width: 40px; text-align: right; }}
        .dedup-label {{ font-family: monospace; color: #67e8f9; }}
        .dedup-status {{ font-size: 0.8rem; font-weight: 600; }}
        .dedup-none {{ color: #22c55e; }}
        .empty-state {{ color: #22c55e; text-align: center; padding: 40px; font-size: 1.1rem; }}
    </style>
</head>
<body>
    <h1>Fuzion Report</h1>
    <p class="subtitle">Generated {datetime.now(pst).strftime("%B %d, %Y at %I:%M %p PST")}</p>
    <div class="cards">
        <div class="card total"><div class="number">{total}</div><div class="label">Total Runs</div></div>
        <div class="card ok"><div class="number">{counts["ok"]}</div><div class="label">OK</div></div>
        <div class="card crash"><div class="number">{counts["crash"]}</div><div class="label">Crashes</div></div>
        <div class="card timeout"><div class="number">{counts["timeout"]}</div><div class="label">Timeouts</div></div>
        <div class="card hang"><div class="number">{counts["hang"]}</div><div class="label">Hangs</div></div>
        <div class="card error"><div class="number">{counts["error"]}</div><div class="label">Errors</div></div>
    </div>
    {dedup_html}
    <h2>Failure Details</h2>
    {"<p class='empty-state'>No failures found — all testcases passed.</p>" if not table_rows else f"""<table>
        <thead><tr><th>Testcase</th><th>Result</th><th>Root Cause</th><th>Elapsed</th><th>Detail</th></tr></thead>
        <tbody>{table_rows}</tbody>
    </table>"""}
</body>
</html>"""

    logger.debug("Writing HTML report (%d chars) to %s", len(html), output_path)
    output_path.write_text(html)
    logger.debug("Report written successfully to %s", output_path)
    print(f"Report written to {output_path}")

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    generate_report(
        out_dir=root / "out",
        output_path=root / "out" / "report.html",
    )
