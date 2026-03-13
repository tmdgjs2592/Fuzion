from __future__ import annotations

from argparse import ArgumentParser, Namespace

from rich.console import Console

from .campaign import CampaignConfig, campaign_root, run_campaign
from .campaign_report import generate_campaign_report
from .config import FuzionConfig
from .tui import load_formats


def add_campaign_args(parser: ArgumentParser) -> None:
    parser.add_argument("--campaign-name", help="Run a non-interactive mutation campaign")
    parser.add_argument("--seed-source", choices=["manual", "custom", "custom_v2", "domato"], default="manual")
    parser.add_argument("--seed-count", type=int, default=4)
    parser.add_argument("--generations", type=int, default=2)
    parser.add_argument("--mutations-per-case", type=int, default=1)
    parser.add_argument("--retain-per-bucket", type=int, default=1)
    parser.add_argument("--campaign-format", default="html", help="Domato format key for domato seed campaigns")
    parser.add_argument("--random-seed", type=int, default=42)


def maybe_run_campaign(*, args: Namespace, cfg: FuzionConfig, console: Console, jobs: int) -> bool:
    if not args.campaign_name:
        return False

    format_arg = "html_only.html"
    if args.seed_source == "domato":
        formats = load_formats(cfg.bundles_yaml)
        if args.campaign_format not in formats:
            raise ValueError(f"Unknown campaign format: {args.campaign_format}")
        format_arg = formats[args.campaign_format]["domato_arg"]

    config = CampaignConfig(
        project_root=cfg.project_root,
        out_dir=cfg.out_dir,
        campaign_name=args.campaign_name,
        seed_source=args.seed_source,
        seed_count=args.seed_count,
        generations=args.generations,
        mutations_per_case=args.mutations_per_case,
        retain_per_bucket=args.retain_per_bucket,
        nav_timeout_s=cfg.nav_timeout_s,
        hard_timeout_s=cfg.hard_timeout_s,
        max_concurrency=jobs,
        headed=args.headed,
        browser_channel=args.browser_channel,
        browser_executable_path=args.browser_executable,
        domato_format_key=args.campaign_format,
        domato_format_arg=format_arg,
        random_seed=args.random_seed,
    )
    summary = run_campaign(config)
    root = campaign_root(config)
    report_path = generate_campaign_report(root)

    console.print("\n[bold]Campaign[/bold]")
    console.print(f"  name: {config.campaign_name}")
    console.print(f"  total cases: {summary.total_cases}")
    console.print(f"  abnormal cases: {summary.abnormal_cases}")
    console.print(f"  unique buckets: {summary.unique_buckets}")
    console.print(f"  artifacts: [green]{root}[/green]")
    console.print(f"  report: [green]{report_path}[/green]")
    return True
