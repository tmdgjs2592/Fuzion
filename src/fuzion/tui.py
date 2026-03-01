from pathlib import Path
import yaml
from rich.console import Console
from rich.prompt import Prompt, IntPrompt
from .config import FuzionConfig
from .generate import generate_html_files

def load_formats(bundles_yaml: Path) -> dict:
    data = yaml.safe_load(bundles_yaml.read_text())
    return data["formats"]

def prompt_user(cfg: FuzionConfig):
    console = Console()
    console.print("[bold]Fuzion[/bold] — grammar-based browser fuzzing harness")    
    console.print("1. [cyan]Generate[/cyan]")
    console.print("2. [cyan]Custom[/cyan]")

    choice = IntPrompt.ask("Choice")
    choice = max(1, min(choice, 2))

    return choice

def format_prompt_user(bundles_yaml: Path) -> tuple[int, str, str]:
    console = Console()
    formats = load_formats(bundles_yaml)
    
    console.print("Choose a format:")
    keys = list(formats.keys())
    for i, k in enumerate(keys, start=1):
        console.print(f"  {i}. [cyan]{k}[/cyan] — {formats[k].get('description','')}")

    choice = IntPrompt.ask("Format number")
    choice = max(1, min(choice, len(keys)))
    fmt = keys[choice - 1]

    n = IntPrompt.ask("How many HTML files to generate?", default=100)
    n = max(1, n)
    domato_arg = formats[fmt]["domato_arg"]

    return n, fmt, domato_arg

def custom_prompt_user() -> tuple[int, int | None]:
    console = Console()

    n = IntPrompt.ask("How many files to generate?", default=100)
    n = max(1, n)

    seed_str = Prompt.ask("Random seed? (leave blank for none)", default="")
    seed = int(seed_str) if seed_str.strip() else None

    return n, seed


