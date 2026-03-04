import logging
import subprocess
from pathlib import Path
from .util import ensure_dir
import sys

logger = logging.getLogger(__name__)


def _domato_generator(domato_dir: Path) -> Path:
    gen = domato_dir / "generator.py"
    logger.debug("Looking for Domato generator at %s", gen)
    if not gen.exists():
        logger.debug("Domato generator.py not found at %s", gen)
        raise FileNotFoundError(f"Domato generator.py not found at: {gen}")
    logger.debug("Found Domato generator at %s", gen)
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
    logger.debug(
        "generate_html_files called: domato_dir=%s, corpus_dir=%s, template_dir=%s, n=%d, format_key=%s, domato_format_arg=%s",
        domato_dir, corpus_dir, template_dir, n, format_key, domato_format_arg,
    )

    ensure_dir(corpus_dir)
    gen = _domato_generator(domato_dir)

    # Domato generator storage
    tmp_out = corpus_dir / "_tmp_domato_out"
    ensure_dir(tmp_out)
    logger.debug("Temporary Domato output directory: %s", tmp_out)

    # Build domato generator cmd
    # Add grammar selections (Domato uses flags like --grammar or direct args depending on version).
    # We support both patterns by trying a modern flag style first, then falling back.
    args = [sys.executable, str(gen)]
    template_grammar = template_dir / domato_format_arg
    logger.debug("Resolved template grammar path: %s", template_grammar)

    # Pattern A (common): generator.py -o OUT -n N -t template.html
    cmd_a = args + ["-o", str(tmp_out), "-n", str(n), "-t", template_grammar]
    logger.debug("Attempting Pattern A command: %s", cmd_a)

    try:
        result = subprocess.run(
            cmd_a,
            cwd=str(domato_dir),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        logger.debug("Pattern A succeeded (exit 0)")
        logger.debug("Domato stdout: %s", result.stdout.strip())
        logger.debug("Domato stderr: %s", result.stderr.strip())
    except subprocess.CalledProcessError as e:
        """ 
        # DEBUG PRINT
        raise RuntimeError(
            f"Domato failed (exit {e.returncode}).\n"
            f"CMD: {e.cmd}\n\nSTDERR:\n{e.stderr}\n\nSTDOUT:\n{e.stdout}\n"
        ) from e
        """
        logger.debug(
            "Pattern A failed (exit %d); stdout=%r stderr=%r — falling back to Pattern B",
            e.returncode, e.stdout.strip(), e.stderr.strip(),
        )
        # Fall back to Pattern B: generator.py --output_dir OUT --num_files N --grammar ...
        cmd_b = args + ["--output_dir", str(tmp_out), "--num_files", str(n), "--template", template_grammar]
        logger.debug("Attempting Pattern B command: %s", cmd_b)
        result = subprocess.run(
            cmd_b,
            cwd=str(domato_dir),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        logger.debug("Pattern B succeeded (exit 0)")
        logger.debug("Domato stdout: %s", result.stdout.strip())
        logger.debug("Domato stderr: %s", result.stderr.strip())

    # Normalize names into corpus_dir as {format_key}_{i}.html
    produced = sorted(tmp_out.glob("*.html"))
    logger.debug("Domato produced %d .html file(s) in %s", len(produced), tmp_out)
    if len(produced) == 0:
        logger.debug("No .html files found in %s — raising RuntimeError", tmp_out)
        raise RuntimeError("Domato produced no .html files. Check grammar args / domato version.")

    files_to_copy = produced[:n]
    logger.debug("Copying %d file(s) into corpus_dir %s with format_key '%s'", len(files_to_copy), corpus_dir, format_key)
    for i, src in enumerate(files_to_copy, start=1):
        dst = corpus_dir / f"{format_key}_{i:06d}.html"
        dst.write_bytes(src.read_bytes())
        logger.debug("Copied %s -> %s (%d bytes)", src.name, dst.name, src.stat().st_size)

    logger.debug("generate_html_files complete: %d file(s) written to %s", len(files_to_copy), corpus_dir)