import subprocess
from pathlib import Path
from .util import ensure_dir
import sys

def _domato_generator(domato_dir: Path) -> Path:
    gen = domato_dir / "generator.py"
    if not gen.exists():
        raise FileNotFoundError(f"Domato generator.py not found at: {gen}")
    return gen

def generate_html_files(
    *,
    domato_dir: Path,
    corpus_dir: Path,
    template_dir: Path,
    n: int,
    format_key: str,
    domato_format_arg: str,
) -> None:
    """
    domato_format_arg example:
      {"html": "htmlgrammar", "css": "cssgrammar", "js": "jsgrammar"}
    """
    ensure_dir(corpus_dir)
    gen = _domato_generator(domato_dir)

    # Domato generator storage
    tmp_out = corpus_dir / "_tmp_domato_out"
    ensure_dir(tmp_out)

    # Build domato generator cmd
    # Add grammar selections (Domato uses flags like --grammar or direct args depending on version).
    # We support both patterns by trying a modern flag style first, then falling back.
    args = [sys.executable, str(gen)]
    template_grammar = template_dir / domato_format_arg

    # Pattern A (common): generator.py -o OUT -n N -t template.html
    cmd_a = args + ["-o", str(tmp_out), "-n", str(n), "-t", template_grammar]

    try:
        subprocess.run(
            cmd_a,
            cwd=str(domato_dir),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        """ 
        # DEBUG PRINT
        raise RuntimeError(
            f"Domato failed (exit {e.returncode}).\n"
            f"CMD: {e.cmd}\n\nSTDERR:\n{e.stderr}\n\nSTDOUT:\n{e.stdout}\n"
        ) from e
        """
        # Fall back to Pattern B: generator.py --output_dir OUT --num_files N --grammar ...
        cmd_b = args + ["--output_dir", str(tmp_out), "--num_files", str(n), "--template", template_grammar]
        subprocess.run(
            cmd_b,
            cwd=str(domato_dir),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    # Normalize names into corpus_dir as {format_key}_{i}.html
    produced = sorted(tmp_out.glob("*.html"))
    if len(produced) == 0:
        raise RuntimeError("Domato produced no .html files. Check grammar args / domato version.")

    for i, src in enumerate(produced[:n], start=1):
        dst = corpus_dir / f"{format_key}_{i:06d}.html"
        dst.write_bytes(src.read_bytes())

