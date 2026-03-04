import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

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
) -> Tuple[RunSummary, List[tuple[Path, RunResult]]]:
    logger.debug(
        "run_corpus called: corpus_dir=%s, findings_dir=%s, nav_timeout_s=%d, hard_timeout_s=%d",
        corpus_dir, findings_dir, nav_timeout_s, hard_timeout_s,
    )
    ensure_dir(corpus_dir)
    ensure_dir(findings_dir)

    summary = RunSummary()
    results: List[tuple[Path, RunResult]] = []

    html_files = sorted(corpus_dir.glob("*.html"))
    logger.debug("Found %d .html file(s) in corpus_dir %s", len(html_files), corpus_dir)

    for html in html_files:
        logger.debug("Running testcase: %s", html.name)
        res = await run_one(
            html_path=html,
            findings_dir=findings_dir,
            nav_timeout_s=nav_timeout_s,
            hard_timeout_s=hard_timeout_s,
        )
        logger.debug("Testcase %s result: status=%s, elapsed_ms=%s, detail=%s", html.name, res.status, res.elapsed_ms, res.detail)
        results.append((html, res))
        setattr(summary, res.status, getattr(summary, res.status) + 1)
        logger.debug("Running summary: ok=%d, crash=%d, hang=%d, timeout=%d, error=%d", summary.ok, summary.crash, summary.hang, summary.timeout, summary.error)

    logger.debug("run_corpus complete: %d result(s), final summary: ok=%d, crash=%d, hang=%d, timeout=%d, error=%d", len(results), summary.ok, summary.crash, summary.hang, summary.timeout, summary.error)
    return summary, results

async def run_custom(
    *,
    html_dir: Path,
    findings_dir: Path,
    nav_timeout_s: int,
    hard_timeout_s: int,
) -> Tuple[RunSummary, List[tuple[Path, RunResult]]]:
    logger.debug(
        "run_custom called: html_dir=%s, findings_dir=%s, nav_timeout_s=%d, hard_timeout_s=%d",
        html_dir, findings_dir, nav_timeout_s, hard_timeout_s,
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
            )
    logger.debug("Testcase %s result: status=%s, elapsed_ms=%s, detail=%s", html_dir.name, res.status, res.elapsed_ms, res.detail)
    results.append((html_dir, res))
    setattr(summary, res.status, getattr(summary, res.status) + 1)

    logger.debug("run_custom complete: final summary: ok=%d, crash=%d, hang=%d, timeout=%d, error=%d", summary.ok, summary.crash, summary.hang, summary.timeout, summary.error)
    return summary, results