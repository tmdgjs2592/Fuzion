from __future__ import annotations

import random
from pathlib import Path

from fuzion.campaign_mutator import mutate_file, mutate_html


SAMPLE = """<!doctype html>
<html>
<head>
<style>
div { width: 7px; }
</style>
<script>
var x = 7;
console.log(x);
</script>
</head>
<body>
<div>hi</div>
</body>
</html>
"""


def test_mutate_html_returns_changed_html_and_mutator() -> None:
    mutated, mutator = mutate_html(SAMPLE, rng=random.Random(1))

    assert mutated != SAMPLE
    assert mutator


def test_mutate_file_writes_child_case(tmp_path: Path) -> None:
    source = tmp_path / "seed.html"
    child = tmp_path / "child.html"
    source.write_text(SAMPLE, encoding="utf-8")

    mutator = mutate_file(source, child, rng=random.Random(2))

    assert child.exists()
    assert child.read_text(encoding="utf-8") != SAMPLE
    assert mutator


def test_mutate_html_can_append_domato_bundle(monkeypatch) -> None:
    from fuzion import campaign_mutator as mod

    monkeypatch.setattr(
        mod,
        "_mutation_options",
        lambda html, rng, domato_dir: [
            (
                "append_domato_bundle",
                1,
                lambda: "<html><head><style>div{color:red;}</style></head><body><div id='a'></div><script>console.log('bundle');</script></body></html>",
            )
        ],
    )

    mutated, mutator = mutate_html("<html><head></head><body>hi</body></html>", rng=random.Random(0), domato_dir=Path("/tmp/domato"))

    assert mutator == "append_domato_bundle"
    assert "console.log('bundle');" in mutated
    assert "div{color:red;}" in mutated
    assert "<div id='a'></div>" in mutated


def test_mutate_html_inserts_before_real_closing_tag(monkeypatch) -> None:
    from fuzion import campaign_mutator as mod

    monkeypatch.setattr(
        mod,
        "_mutation_options",
        lambda html, rng, domato_dir: [
            ("append_domato_js_fragment", 1, lambda: mod._append_script(html, "console.log('domato');"))
        ],
    )

    html = "<html><body><script>const x = '</body>';</script><div>hi</div></body></html>"
    mutated, mutator = mutate_html(html, rng=random.Random(0), domato_dir=Path("/tmp/domato"))

    assert mutator == "append_domato_js_fragment"
    assert "<script>const x = '</body>';</script>" in mutated
    assert "<div>hi</div><script>\nconsole.log('domato');\n</script>\n</body>" in mutated


def test_mutate_html_prefers_balanced_body_fragments(monkeypatch) -> None:
    from fuzion import campaign_mutator as mod

    monkeypatch.setattr(
        mod,
        "_mutation_options",
        lambda html, rng, domato_dir: [
            (
                "duplicate_body_fragment",
                1,
                lambda: mod._mutate_span(html, mod._BODY_RE, rng, lambda block: mod._duplicate_fragment(block, rng)),
            )
        ],
    )

    html = "<html><body><div>one</div><p>two</p></body></html>"
    mutated, mutator = mutate_html(html, rng=random.Random(0), domato_dir=None)

    assert mutator == "duplicate_body_fragment"
    assert mutated.count("</div>") + mutated.count("</p>") == 3
