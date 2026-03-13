import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from .run import run_one, RunResult
from .util import ensure_dir

logger = logging.getLogger(__name__)


@dataclass
class RunSummary:
    ok: int = 0
    crash: int = 0
    hang: int = 0
    timeout: int = 0
    error: int = 0

async def run_corpus(
    *,
    corpus_dir: Path,
    findings_dir: Path,
    nav_timeout_s: int,
    hard_timeout_s: int,
    max_concurrency: int = 1,
    headed: bool = False,
    browser_channel: str | None = None,
    browser_executable_path: Path | None = None,
) -> Tuple[RunSummary, List[tuple[Path, RunResult]]]:
    logger.debug(
        "run_corpus called: corpus_dir=%s, findings_dir=%s, nav_timeout_s=%d, hard_timeout_s=%d, max_concurrency=%d, headed=%s, browser_channel=%s, browser_executable_path=%s",
        corpus_dir, findings_dir, nav_timeout_s, hard_timeout_s, max_concurrency, headed, browser_channel, browser_executable_path,
    )
    ensure_dir(corpus_dir)
    ensure_dir(findings_dir)

    summary = RunSummary()
    results: List[tuple[Path, RunResult]] = []

    html_files = sorted(corpus_dir.glob("*.html"))
    logger.debug("Found %d .html file(s) in corpus_dir %s", len(html_files), corpus_dir)


    # ensure concurrency for all vals of file size
    concurrency = max(1, max_concurrency)
    if len(html_files):
        concurrency = min(len(html_files), concurrency)


    logger.debug("Using concurrency=%d", concurrency)

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        BarColumn(bar_width=30),
        TextColumn("{task.completed}/{task.total}"),
        TextColumn("•"),
        TextColumn("[green]{task.fields[ok]} ok[/green]  [red]{task.fields[crashes]} crash[/red]  [yellow]{task.fields[timeouts]} timeout[/yellow]  [magenta]{task.fields[errors]} error[/magenta]"),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task("Running", total=len(html_files), ok=0, crashes=0, timeouts=0, errors=0)

        sem = asyncio.Semaphore(concurrency)

       



        async def _run_with_limit(html: Path) -> tuple[Path, RunResult]:
            async with sem: # if sem isn't busy, run testcase
                logger.debug("Running testcase: %s", html.name)
                res = await run_one(
                    html_path=html,
                    findings_dir=findings_dir,
                    nav_timeout_s=nav_timeout_s,
                    hard_timeout_s=hard_timeout_s,
                    headed=headed,
                    browser_channel=browser_channel,
                    browser_executable_path=browser_executable_path,
                )
                return html, res

        tasks = [asyncio.create_task(_run_with_limit(html)) for html in html_files]
        try:
            for done in asyncio.as_completed(tasks):
                html, res = await done
                logger.debug("Testcase %s result: status=%s, elapsed_ms=%s, detail=%s", html.name, res.status, res.elapsed_ms, res.detail)
                results.append((html, res))
                setattr(summary, res.status, getattr(summary, res.status) + 1)
                progress.update(task, advance=1, ok=summary.ok, crashes=summary.crash, timeouts=summary.timeout, errors=summary.error)
                logger.debug("Running summary: ok=%d, crash=%d, hang=%d, timeout=%d, error=%d", summary.ok, summary.crash, summary.hang, summary.timeout, summary.error)
        except Exception as e:
            for t in tasks:
                logger.debug("error:",str(e))
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

    # sort results (optional but makes it appear sequential)
    results.sort(key=lambda item: item[0].name)

    logger.debug("run_corpus complete: %d result(s), final summary: ok=%d, crash=%d, hang=%d, timeout=%d, error=%d", len(results), summary.ok, summary.crash, summary.hang, summary.timeout, summary.error)
    return summary, results

async def run_custom(
    *,
    html_dir: Path,
    findings_dir: Path,
    nav_timeout_s: int,
    hard_timeout_s: int,
    headed: bool = False,
    browser_channel: str | None = None,
    browser_executable_path: Path | None = None,
) -> Tuple[RunSummary, List[tuple[Path, RunResult]]]:
    logger.debug(
        "run_custom called: html_dir=%s, findings_dir=%s, nav_timeout_s=%d, hard_timeout_s=%d, headed=%s, browser_channel=%s, browser_executable_path=%s",
        html_dir, findings_dir, nav_timeout_s, hard_timeout_s, headed, browser_channel, browser_executable_path,
    )
    ensure_dir(findings_dir)

    summary = RunSummary()
    results: List[tuple[Path, RunResult]] = []

    logger.debug("Running single testcase: %s", html_dir.name)
    res = await run_one(
                html_path=html_dir,
                findings_dir=findings_dir,
                nav_timeout_s=nav_timeout_s,
                hard_timeout_s=hard_timeout_s,
                headed=headed,
                browser_channel=browser_channel,
                browser_executable_path=browser_executable_path,
            )
    logger.debug("Testcase %s result: status=%s, elapsed_ms=%s, detail=%s", html_dir.name, res.status, res.elapsed_ms, res.detail)
    results.append((html_dir, res))
    setattr(summary, res.status, getattr(summary, res.status) + 1)

    logger.debug("run_custom complete: final summary: ok=%d, crash=%d, hang=%d, timeout=%d, error=%d", summary.ok, summary.crash, summary.hang, summary.timeout, summary.error)
    return summary, results
