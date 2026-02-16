from pathlib import Path
import yaml
from rich.console import Console
from rich.prompt import Prompt, IntPrompt

def load_formats(bundles_yaml: Path) -> dict:
    data = yaml.safe_load(bundles_yaml.read_text())
    return data["formats"]

def prompt_user(bundles_yaml: Path) -> tuple[int, str]:
    console = Console()
    formats = load_formats(bundles_yaml)

    console.print("[bold]Fuzion[/bold] — grammar-based browser fuzzing harness")
    console.print("Choose a format:")

    keys = list(formats.keys())
    for i, k in enumerate(keys, start=1):
        console.print(f"  {i}. [cyan]{k}[/cyan] — {formats[k].get('description','')}")

    choice = IntPrompt.ask("Format number")
    choice = max(1, min(choice, len(keys)))
    fmt = keys[choice - 1]

    n = IntPrompt.ask("How many HTML files to generate?", default=100)
    n = max(1, n)

    return n, fmt

