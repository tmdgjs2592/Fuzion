import asyncio
from pathlib import Path
import yaml
from rich.console import Console

from .config import default_config
from .tui import prompt_user, load_formats
from .generate import generate_html_files
from .triage import run_corpus

def main():
    console = Console()
    root = Path(__file__).resolve().parents[2]
    cfg = default_config(root)

    n, fmt = prompt_user(cfg.bundles_yaml)
    formats = load_formats(cfg.bundles_yaml)
    domato_arg = formats[fmt]["domato_arg"]

    console.print(f"\n[bold]Generating[/bold] {n} files using format [cyan]{fmt}[/cyan]...")
    generate_html_files(
        domato_dir=cfg.domato_dir,
        corpus_dir=cfg.corpus_dir,
        template_dir=cfg.template_dir,
        n=n,
        format_key=fmt,
        domato_format_arg=domato_arg,
    )

    console.print(f"[bold]Running[/bold] headless Chromium over corpus in: {cfg.corpus_dir}")
    summary, _ = asyncio.run(
        run_corpus(
            corpus_dir=cfg.corpus_dir,
            findings_dir=cfg.findings_dir,
            nav_timeout_s=cfg.nav_timeout_s,
            hard_timeout_s=cfg.hard_timeout_s,
        )
    )

    console.print("\n[bold]Summary[/bold]")
    console.print(f"  ok: {summary.ok}")
    console.print(f"  crash: {summary.crash}")
    console.print(f"  hang: {summary.hang}")
    console.print(f"  timeout: {summary.timeout}")
    console.print(f"  error: {summary.error}")
    console.print(f"\nFindings saved under: [green]{cfg.findings_dir}[/green]")

if __name__ == "__main__":
    main()

