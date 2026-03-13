from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fuzion.run import RunResult


def _write_html(path: Path) -> None:
    path.write_text("<!DOCTYPE html><html><body>hi</body></html>", encoding="utf-8")


def _make_result(status: str) -> RunResult:
    return RunResult(status=status, detail="", elapsed_ms=10)


@pytest.mark.asyncio
async def test_empty_corpus_returns_empty_results(tmp_path):
    from fuzion.orchestrator import run_corpus

    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()

    with patch("fuzion.orchestrator.run_one", new_callable=AsyncMock) as mock_run:
        summary, results = await run_corpus(
            corpus_dir=corpus_dir,
            findings_dir=tmp_path / "findings",
            nav_timeout_s=1,
            hard_timeout_s=1,
        )

    assert results == []
    assert summary.ok == 0
    assert summary.crash == 0
    mock_run.assert_not_called()


@pytest.mark.asyncio
async def test_runs_every_html_file_in_corpus(tmp_path):
    from fuzion.orchestrator import run_corpus

    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    for i in range(3):
        _write_html(corpus_dir / f"case_{i:06d}.html")

    with patch("fuzion.orchestrator.run_one", new_callable=AsyncMock, return_value=_make_result("ok")) as mock_run:
        summary, results = await run_corpus(
            corpus_dir=corpus_dir,
            findings_dir=tmp_path / "findings",
            nav_timeout_s=1,
            hard_timeout_s=1,
        )

    assert mock_run.call_count == 3
    assert len(results) == 3


@pytest.mark.asyncio
async def test_ignores_non_html_files(tmp_path):
    from fuzion.orchestrator import run_corpus

    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    _write_html(corpus_dir / "case_000001.html")
    (corpus_dir / "notes.txt").write_text("ignore me")
    (corpus_dir / "data.json").write_text("{}")

    with patch("fuzion.orchestrator.run_one", new_callable=AsyncMock, return_value=_make_result("ok")) as mock_run:
        _, results = await run_corpus(
            corpus_dir=corpus_dir,
            findings_dir=tmp_path / "findings",
            nav_timeout_s=1,
            hard_timeout_s=1,
        )

    assert mock_run.call_count == 1
    assert len(results) == 1


@pytest.mark.asyncio
async def test_summary_counts_are_accurate(tmp_path):
    from fuzion.orchestrator import run_corpus

    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    statuses = ["ok", "ok", "crash", "hang", "timeout", "error"]
    for i, status in enumerate(statuses):
        _write_html(corpus_dir / f"case_{i:06d}.html")

    return_values = [_make_result(s) for s in statuses]

    with patch("fuzion.orchestrator.run_one", new_callable=AsyncMock, side_effect=return_values):
        summary, _ = await run_corpus(
            corpus_dir=corpus_dir,
            findings_dir=tmp_path / "findings",
            nav_timeout_s=1,
            hard_timeout_s=1,
        )

    assert summary.ok == 2
    assert summary.crash == 1
    assert summary.hang == 1
    assert summary.timeout == 1
    assert summary.error == 1


@pytest.mark.asyncio
async def test_results_contain_path_and_run_result_pairs(tmp_path):
    from fuzion.orchestrator import run_corpus

    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    html = corpus_dir / "case_000001.html"
    _write_html(html)

    with patch("fuzion.orchestrator.run_one", new_callable=AsyncMock, return_value=_make_result("ok")):
        _, results = await run_corpus(
            corpus_dir=corpus_dir,
            findings_dir=tmp_path / "findings",
            nav_timeout_s=1,
            hard_timeout_s=1,
        )

    assert len(results) == 1
    path, result = results[0]
    assert path == html
    assert isinstance(result, RunResult)


@pytest.mark.asyncio
async def test_crash_evidence_survives_subsequent_ok_run(tmp_path):
    from fuzion.orchestrator import run_corpus

    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    findings_dir = tmp_path / "findings"

    crash_html = corpus_dir / "case_000001.html"
    ok_html = corpus_dir / "case_000002.html"
    _write_html(crash_html)
    _write_html(ok_html)

    async def fake_run_one(*, html_path, findings_dir, nav_timeout_s, hard_timeout_s, **_kwargs):
        run_dir = findings_dir / html_path.stem
        if html_path.name == "case_000001.html":
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "meta.json").write_text('{"result": "crash"}')
            return _make_result("crash")
        return _make_result("ok")

    with patch("fuzion.orchestrator.run_one", side_effect=fake_run_one):
        summary, _ = await run_corpus(
            corpus_dir=corpus_dir,
            findings_dir=findings_dir,
            nav_timeout_s=1,
            hard_timeout_s=1,
        )

    assert summary.crash == 1
    assert summary.ok == 1
    assert (findings_dir / "case_000001" / "meta.json").exists()


@pytest.mark.asyncio
async def test_run_corpus_forwards_browser_options(tmp_path):
    from fuzion.orchestrator import run_corpus

    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    html = corpus_dir / "case_000001.html"
    _write_html(html)
    browser_exe = tmp_path / "chrome"
    browser_exe.write_text("", encoding="utf-8")

    with patch("fuzion.orchestrator.run_one", new_callable=AsyncMock, return_value=_make_result("ok")) as mock_run:
        await run_corpus(
            corpus_dir=corpus_dir,
            findings_dir=tmp_path / "findings",
            nav_timeout_s=1,
            hard_timeout_s=1,
            headed=True,
            browser_channel="chrome",
            browser_executable_path=browser_exe,
        )

    called = mock_run.await_args.kwargs
    assert called["headed"] is True
    assert called["browser_channel"] == "chrome"
    assert called["browser_executable_path"] == browser_exe
