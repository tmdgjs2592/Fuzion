from __future__ import annotations

import pytest
from pathlib import Path

from fuzion.config import default_config
from fuzion.generators import DomatoGenerator, CustomGenerator, CustomGeneratorV2

# Testing both generate.py and custom_generator.py- For the next components of fuzion, results need to ensure that from both functions we get:
# 1. n files generated
# 2. with the html extension
# 3. into the corpus generated directory 
# 4. and that the function returns without raising exceptions

ROOT = Path(__file__).resolve().parents[1]

def assert_generator_contract(corpus_dir: Path, n: int) -> None:
    files = list(corpus_dir.glob("*.html"))
    assert len(files) == n
    assert all(f.suffix == ".html" for f in files)
    assert all(f.parent == corpus_dir for f in files)


@pytest.fixture(params=[
    pytest.param("domato", id="DomatoGenerator"),
    pytest.param("custom", id="CustomGenerator"),
    pytest.param("custom_v2", id="CustomGeneratorV2"),
])
def generator(request, tmp_path):
    cfg = default_config(ROOT)
    if request.param == "domato":
        return DomatoGenerator(
            domato_dir=cfg.domato_dir,
            template_dir=cfg.template_dir,
            format_key="html",
            domato_format_arg="html_only.html",  # was "--html"
        )
    if request.param == "custom_v2":
        return CustomGeneratorV2(seed=42)
    return CustomGenerator(
        rules_path=ROOT / "grammars" / "html_rules.yaml",
        seed=42,
    )


@pytest.mark.parametrize("n", [1, 5, 10])
def test_generates_n_html_files_in_corpus_dir(generator, tmp_path, n):
    generator.generate(corpus_dir=tmp_path, n=n)
    assert_generator_contract(corpus_dir=tmp_path, n=n)


def test_does_not_raise(generator, tmp_path):
    generator.generate(corpus_dir=tmp_path, n=3)
