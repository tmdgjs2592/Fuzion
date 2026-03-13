import asyncio
import logging
import argparse
from pathlib import Path
import yaml
from rich.console import Console
from rich.prompt import Confirm

from .config import default_config
from .tui import prompt_user, format_prompt_user, custom_prompt_user, manual_prompt_user
from .orchestrator import run_corpus, run_custom
from .generators import DomatoGenerator, CustomGenerator
from .util import write_json, safe_rmtree, ensure_dir
from .dedup import dedup_summary
from .report import generate_report

logger = logging.getLogger(__name__)


def _reset_dir(p: Path) -> None:
    logger.debug("Resetting directory: %s", p)
    safe_rmtree(p)
    ensure_dir(p)
    logger.debug("Directory reset complete: %s", p)


def _maybe_clear_out_dir(*, out_dir: Path, console: Console) -> None:
    ensure_dir(out_dir)
    if not any(out_dir.iterdir()):
        return

    console.print(
        f"[yellow]Warning:[/yellow] Output directory [cyan]{out_dir}[/cyan] is not empty."
    )
    if Confirm.ask("Clear output directory before this run?", default=False):
        _reset_dir(out_dir)
        console.print(f"[green]Cleared[/green] output directory: [cyan]{out_dir}[/cyan]")
    else:
        console.print("[dim]Keeping existing output directory contents.[/dim]")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument("--jobs", type=int, default=None, help="Number of threads")
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run with a visible browser window instead of headless mode",
    )
    parser.add_argument(
        "--browser-channel",
        type=str,
        default=None,
        help="Playwright browser channel (example: chrome, msedge)",
    )
    parser.add_argument(
        "--browser-executable",
        type=Path,
        default=None,
        help="Path to a browser executable to launch",
    )
    args = parser.parse_args()

    if args.browser_channel and args.browser_executable is not None:
        parser.error("Use either --browser-channel or --browser-executable, not both.")
    if args.browser_executable is not None:
        args.browser_executable = args.browser_executable.expanduser().resolve()
        if not args.browser_executable.exists():
            parser.error(f"--browser-executable not found: {args.browser_executable}")

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    console = Console()
    root = Path(__file__).resolve().parents[2]
    logger.debug("Project root resolved to: %s", root)
    cfg = default_config(root)
    logger.debug("Loaded default config: %s", cfg)
    _maybe_clear_out_dir(out_dir=cfg.out_dir, console=console)

    # jobs
    jobs = max(1, args.jobs) if args.jobs is not None else cfg.max_concurrency
    logger.debug("threads set to jobs=%d", jobs)
    if args.headed and jobs > 1:
        console.print("[yellow]Warning:[/yellow] headed mode with multiple jobs opens multiple browser windows.")

    run_mode = "headed" if args.headed else "headless"
    browser_target = "Chromium"
    if args.browser_channel:
        browser_target = f"browser channel '{args.browser_channel}'"
    elif args.browser_executable is not None:
        browser_target = f"browser executable {args.browser_executable}"

    choice = prompt_user(cfg)
    logger.debug("User selected choice: %d", choice)

    if (choice == 1):
        n, fmt, domato_arg = format_prompt_user(cfg.bundles_yaml)
        logger.debug("Format prompt returned: n=%d, fmt=%s, domato_arg=%s", n, fmt, domato_arg)

        console.print(f"\n[bold]Generating[/bold] {n} files using format [cyan]{fmt}[/cyan]...")
        gen = DomatoGenerator(
            domato_dir=cfg.domato_dir,
            template_dir=cfg.template_dir,
            format_key=fmt,
            domato_format_arg=domato_arg,
        )
        logger.debug("DomatoGenerator instantiated: %s", gen)
        gen.generate(corpus_dir=cfg.corpus_dir, n=n)
        logger.debug("DomatoGenerator.generate complete")

        console.print(f"[bold]Running[/bold] {run_mode} {browser_target} over corpus in: {cfg.corpus_dir}")
        logger.debug(
            "Starting run_corpus: corpus_dir=%s, findings_dir=%s, nav_timeout_s=%s, hard_timeout_s=%s, jobs=%d, headed=%s, browser_channel=%s, browser_executable=%s",
            cfg.corpus_dir, cfg.findings_dir, cfg.nav_timeout_s, cfg.hard_timeout_s, jobs, args.headed, args.browser_channel, args.browser_executable,
        )
        summary, results = asyncio.run(
            run_corpus(
                corpus_dir=cfg.corpus_dir,
                findings_dir=cfg.findings_dir,
                nav_timeout_s=cfg.nav_timeout_s,
                hard_timeout_s=cfg.hard_timeout_s,
                max_concurrency=jobs,
                headed=args.headed,
                browser_channel=args.browser_channel,
                browser_executable_path=args.browser_executable,
            )
        )
        logger.debug("run_corpus complete: summary=%s, result count=%d", summary, len(results))

    elif choice == 2:
        n, seed = custom_prompt_user()
        logger.debug("Custom prompt returned: n=%d, seed=%s", n, seed)

        rules_path = cfg.project_root / "grammars" / "html_rules.yaml"
        logger.debug("Resolved rules_path: %s", rules_path)
        console.print(f"\n[bold]Generating[/bold] {n} custom files from: [cyan]{rules_path}[/cyan]...")

        _reset_dir(cfg.corpus_dir)

        gen = CustomGenerator(rules_path=rules_path, seed=seed)
        logger.debug("CustomGenerator instantiated: %s", gen)
        gen.generate(corpus_dir=cfg.corpus_dir, n=n)
        logger.debug("CustomGenerator.generate complete")

        console.print(f"[bold]Running[/bold] {run_mode} {browser_target} over corpus in: {cfg.corpus_dir}")
        logger.debug(
            "Starting run_corpus: corpus_dir=%s, findings_dir=%s, nav_timeout_s=%s, hard_timeout_s=%s, jobs=%d, headed=%s, browser_channel=%s, browser_executable=%s",
            cfg.corpus_dir, cfg.findings_dir, cfg.nav_timeout_s, cfg.hard_timeout_s, jobs, args.headed, args.browser_channel, args.browser_executable,
        )
        summary, results = asyncio.run(
            run_corpus(
                corpus_dir=cfg.corpus_dir,
                findings_dir=cfg.findings_dir,
                nav_timeout_s=cfg.nav_timeout_s,
                hard_timeout_s=cfg.hard_timeout_s,
                max_concurrency=jobs,
                headed=args.headed,
                browser_channel=args.browser_channel,
                browser_executable_path=args.browser_executable,
            )
        )
        logger.debug("run_corpus complete: summary=%s, result count=%d", summary, len(results))
    elif (choice == 3):
        html = manual_prompt_user(cfg.custom_dir)
        console.print(f"[bold]Running[/bold] {run_mode} {browser_target} over a file: {html}")
        summary, results = asyncio.run(
            run_custom(
                html_dir=cfg.custom_dir/html,
                findings_dir=cfg.findings_dir,
                nav_timeout_s=cfg.nav_timeout_s,
                hard_timeout_s=cfg.hard_timeout_s,
                headed=args.headed,
                browser_channel=args.browser_channel,
                browser_executable_path=args.browser_executable,
            )
        )
    logger.debug("Assembling results list from %d entries", len(results))
    all_results = []
    for html_path, res in results:
        logger.debug(
            "Result: testcase_id=%s, status=%s, elapsed_ms=%s, detail=%s",
            html_path.stem, res.status, res.elapsed_ms, res.detail,
        )
        all_results.append({
            "testcase_id": html_path.stem,
            "testcase": str(html_path),
            "status": res.status,
            "detail": res.detail,
            "elapsed_ms": res.elapsed_ms,
        })

    results_path = cfg.out_dir / "results.json"
    logger.debug("Writing %d result(s) to %s", len(all_results), results_path)
    write_json(results_path, {"results": all_results})
    logger.debug("Results JSON written successfully")

    console.print("\n[bold]Summary[/bold]")
    console.print(f"  ok: {summary.ok}")
    console.print(f"  crash: {summary.crash}")
    console.print(f"  hang: {summary.hang}")
    console.print(f"  timeout: {summary.timeout}")
    console.print(f"  error: {summary.error}")
    console.print(f"\nFindings saved under: [green]{cfg.findings_dir}[/green]")

    # group duplicate failures by status + error message to find unique bug types
    ds = dedup_summary(results_path)
    console.print(f"\n[bold]Deduplication[/bold]")
    if ds["unique_types"] > 0:
        console.print(f"  {ds['total_failures']} failure(s) → {ds['unique_types']} unique type(s)")
        for g in ds["groups"]:
            console.print(f"    [{g['status'].upper()}] root cause: {g['root_cause']} — {g['count']} testcase(s)")
    else:
        console.print("  [green]No failures found — nothing to deduplicate.[/green]")

    # generate the HTML report dashboard from results.json
    report_path = cfg.out_dir / "report.html"
    generate_report(out_dir=cfg.out_dir, output_path=report_path)
    console.print(f"\n[bold]Report[/bold] written to: [green]{report_path}[/green]")

    logger.debug(
        "Final summary: ok=%d, crash=%d, hang=%d, timeout=%d, error=%d",
        summary.ok, summary.crash, summary.hang, summary.timeout, summary.error,
    )
    logger.debug("main() complete")

if __name__ == "__main__":
    main()
