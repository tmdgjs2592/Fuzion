from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from .run import run_one, RunResult
from .util import ensure_dir

@dataclass
class TriageSummary:
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
) -> Tuple[TriageSummary, List[tuple[Path, RunResult]]]:
    ensure_dir(corpus_dir)
    ensure_dir(findings_dir)

    summary = TriageSummary()
    results: List[tuple[Path, RunResult]] = []

    for html in sorted(corpus_dir.glob("*.html")):
        res = await run_one(
            html_path=html,
            findings_dir=findings_dir,
            nav_timeout_s=nav_timeout_s,
            hard_timeout_s=hard_timeout_s,
        )
        results.append((html, res))
        setattr(summary, res.status, getattr(summary, res.status) + 1)

    return summary, results

