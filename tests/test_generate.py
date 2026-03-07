from __future__ import annotations

from pathlib import Path

import pytest

from fuzion.generate import generate_html_files


def _write_fake_domato_generator(domato_dir: Path) -> None:
    generator = domato_dir / "generator.py"
    generator.write_text(
        """import argparse
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--output_dir", dest="output_dir", required=True)
    parser.add_argument("-n", "--num_files", dest="num_files", type=int, default=1)
    parser.add_argument("-t", "--template")
    args = parser.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    count = int(os.environ.get("FAKE_DOMATO_COUNT", str(args.num_files)))
    for i in range(count):
        (out / f"zzz_generated_{i:06d}.html").write_text(f"fresh-{i}")


if __name__ == "__main__":
    main()
""",
        encoding="utf-8",
    )


def test_generate_html_files_ignores_stale_tmp_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    domato_dir = tmp_path / "domato"
    domato_dir.mkdir()
    _write_fake_domato_generator(domato_dir)

    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "html_only.html").write_text("template", encoding="utf-8")

    corpus_dir = tmp_path / "corpus"
    tmp_domato_out = corpus_dir / "_tmp_domato_out"
    tmp_domato_out.mkdir(parents=True)
    (tmp_domato_out / "aaa_stale.html").write_text("stale", encoding="utf-8")

    monkeypatch.setenv("FAKE_DOMATO_COUNT", "1")
    generate_html_files(
        domato_dir=domato_dir,
        corpus_dir=corpus_dir,
        template_dir=template_dir,
        n=1,
        format_key="html_only",
        domato_format_arg="html_only.html",
    )

    generated = corpus_dir / "html_only_000001.html"
    assert generated.read_text(encoding="utf-8") == "fresh-0"
    assert not tmp_domato_out.exists()


def test_generate_html_files_fails_when_domato_underproduces(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    domato_dir = tmp_path / "domato"
    domato_dir.mkdir()
    _write_fake_domato_generator(domato_dir)

    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "html_only.html").write_text("template", encoding="utf-8")

    corpus_dir = tmp_path / "corpus"
    monkeypatch.setenv("FAKE_DOMATO_COUNT", "1")

    with pytest.raises(RuntimeError, match="expected at least 2"):
        generate_html_files(
            domato_dir=domato_dir,
            corpus_dir=corpus_dir,
            template_dir=template_dir,
            n=2,
            format_key="html_only",
            domato_format_arg="html_only.html",
        )

    assert not (corpus_dir / "_tmp_domato_out").exists()
