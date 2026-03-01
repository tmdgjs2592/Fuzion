import asyncio
from pathlib import Path
import yaml
from rich.console import Console

from .config import default_config
from .tui import prompt_user, format_prompt_user, custom_prompt_user
from .orchestrator import run_corpus
from .generators import DomatoGenerator, CustomGenerator
from .util import write_json, safe_rmtree, ensure_dir

def _reset_dir(p: Path) -> None:
    safe_rmtree(p)
    ensure_dir(p)

def main():
    console = Console()
    root = Path(__file__).resolve().parents[2]
    cfg = default_config(root)

    choice = prompt_user(cfg)

    if (choice == 1):
        n, fmt, domato_arg = format_prompt_user(cfg.bundles_yaml)

        console.print(f"\n[bold]Generating[/bold] {n} files using format [cyan]{fmt}[/cyan]...")
        gen = DomatoGenerator(
            domato_dir=cfg.domato_dir,
            template_dir=cfg.template_dir,
            format_key=fmt,
            domato_format_arg=domato_arg,
        )
        gen.generate(corpus_dir=cfg.corpus_dir, n=n)

        console.print(f"[bold]Running[/bold] headless Chromium over corpus in: {cfg.corpus_dir}")
        summary, results = asyncio.run(
            run_corpus(
                corpus_dir=cfg.corpus_dir,
                findings_dir=cfg.findings_dir,
                nav_timeout_s=cfg.nav_timeout_s,
                hard_timeout_s=cfg.hard_timeout_s,
            )
        )
    elif choice == 2:
        n, seed = custom_prompt_user()

        rules_path = cfg.project_root / "grammars" / "html_rules.yaml"
        console.print(f"\n[bold]Generating[/bold] {n} custom files from: [cyan]{rules_path}[/cyan]...")

        _reset_dir(cfg.corpus_dir)

        gen = CustomGenerator(rules_path=rules_path, seed=seed)
        gen.generate(corpus_dir=cfg.corpus_dir, n=n)

        console.print(f"[bold]Running[/bold] headless Chromium over corpus in: {cfg.corpus_dir}")
        summary, results = asyncio.run(
            run_corpus(
                corpus_dir=cfg.corpus_dir,
                findings_dir=cfg.findings_dir,
                nav_timeout_s=cfg.nav_timeout_s,
                hard_timeout_s=cfg.hard_timeout_s,
            )
        )

    all_results = []
    for html_path, res in results:
        all_results.append({
            "testcase_id": html_path.stem,
            "testcase": str(html_path),
            "status": res.status,
            "detail": res.detail,
            "elapsed_ms": res.elapsed_ms,
        })
    write_json(cfg.out_dir / "results.json", {"results": all_results})

    console.print("\n[bold]Summary[/bold]")
    console.print(f"  ok: {summary.ok}")
    console.print(f"  crash: {summary.crash}")
    console.print(f"  hang: {summary.hang}")
    console.print(f"  timeout: {summary.timeout}")
    console.print(f"  error: {summary.error}")
    console.print(f"\nFindings saved under: [green]{cfg.findings_dir}[/green]")

if __name__ == "__main__":
    main()

