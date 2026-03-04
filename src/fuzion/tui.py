import logging
from pathlib import Path
import yaml
from rich.console import Console
from rich.prompt import Prompt, IntPrompt
from .config import FuzionConfig
from .generate import generate_html_files

logger = logging.getLogger(__name__)


def load_formats(bundles_yaml: Path) -> dict:
    logger.debug("Loading formats from %s", bundles_yaml)
    data = yaml.safe_load(bundles_yaml.read_text())
    formats = data["formats"]
    logger.debug("Loaded %d format(s): %s", len(formats), list(formats.keys()))
    return formats

def prompt_user(cfg: FuzionConfig):
    logger.debug("prompt_user called")
    console = Console()
    console.print("[bold]Fuzion[/bold] — grammar-based browser fuzzing harness")    
    console.print("1. [cyan]Generate[/cyan]")
    console.print("2. [cyan]Custom[/cyan]")

    choice = IntPrompt.ask("Choice")
    choice = max(1, min(choice, 2))
    logger.debug("User selected choice: %d", choice)

    return choice

def format_prompt_user(bundles_yaml: Path) -> tuple[int, str, str]:
    logger.debug("format_prompt_user called: bundles_yaml=%s", bundles_yaml)
    console = Console()
    formats = load_formats(bundles_yaml)
    
    console.print("Choose a format:")
    keys = list(formats.keys())
    for i, k in enumerate(keys, start=1):
        console.print(f"  {i}. [cyan]{k}[/cyan] — {formats[k].get('description','')}")

    choice = IntPrompt.ask("Format number")
    choice = max(1, min(choice, len(keys)))
    fmt = keys[choice - 1]
    logger.debug("User selected format index %d: '%s'", choice, fmt)

    n = IntPrompt.ask("How many HTML files to generate?", default=100)
    n = max(1, n)
    logger.debug("User requested n=%d files", n)

    domato_arg = formats[fmt]["domato_arg"]
    logger.debug("Resolved domato_arg for format '%s': %s", fmt, domato_arg)

    return n, fmt, domato_arg

def custom_prompt_user() -> tuple[int, int | None]:
    logger.debug("custom_prompt_user called")
    console = Console()

    n = IntPrompt.ask("How many files to generate?", default=100)
    n = max(1, n)
    logger.debug("User requested n=%d custom files", n)

    seed_str = Prompt.ask("Random seed? (leave blank for none)", default="")
    seed = int(seed_str) if seed_str.strip() else None
    logger.debug("User provided seed: %s", seed)

    return n, seed