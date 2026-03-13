from __future__ import annotations

from pathlib import Path

from fuzion.campaign_domato import domato_available, generate_bundle, generate_css_rules, generate_html_fragment, generate_js_fragment


def _write_fake_domato(domato_dir: Path) -> None:
    rules_dir = domato_dir / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "html.txt").write_text("html", encoding="utf-8")
    (rules_dir / "css.txt").write_text("css", encoding="utf-8")
    (rules_dir / "js.txt").write_text("js", encoding="utf-8")
    (domato_dir / "html_tags.py").write_text(
        "_HTML_TYPES = {'div': 'HTMLDivElement', 'span': 'HTMLSpanElement'}\n",
        encoding="utf-8",
    )
    (domato_dir / "svg_tags.py").write_text("_SVG_TYPES = {}\n", encoding="utf-8")
    (domato_dir / "mathml_tags.py").write_text("_MATHML_TYPES = {}\n", encoding="utf-8")
    (domato_dir / "grammar.py").write_text(
        """from pathlib import Path

class Grammar:
    def __init__(self):
        self.kind = None

    def parse_from_file(self, path):
        name = Path(path).name
        if name == 'html.txt':
            self.kind = 'html'
        elif name == 'css.txt':
            self.kind = 'css'
        elif name == 'js.txt':
            self.kind = 'js'
        return 0

    def add_import(self, name, grammar):
        return None

    def generate_symbol(self, symbol):
        if self.kind == 'html':
            return '<div><span></span></div>'
        if self.kind == 'css':
            return 'div { color: red; }'
        raise AssertionError(symbol)

    def _generate_code(self, lines, initial_variables):
        return 'var generated = %d; var seen = %d;' % (lines, len(initial_variables))
""",
        encoding="utf-8",
    )


def test_domato_available_requires_expected_files(tmp_path: Path) -> None:
    domato_dir = tmp_path / "domato"
    domato_dir.mkdir()

    assert not domato_available(domato_dir)

    _write_fake_domato(domato_dir)
    assert domato_available(domato_dir)


def test_generate_fragments_and_bundle_use_context(tmp_path: Path) -> None:
    domato_dir = tmp_path / "domato"
    _write_fake_domato(domato_dir)

    html = generate_html_fragment(domato_dir, seed=1)
    css = generate_css_rules(domato_dir, seed=2)
    js = generate_js_fragment(
        domato_dir,
        html="<html><body><div id='a'></div><span></span></body></html>",
        lines=3,
        seed=3,
    )
    bundle = generate_bundle(domato_dir, js_lines=4, seed=4)

    assert html == "<div><span></span></div>"
    assert css == "div { color: red; }"
    assert "var generated = 3;" in js
    assert "var seen = 2;" in js
    assert "document.getElementById('a')" in js or 'document.getElementById("a")' in js
    assert 'id="fuzion_domato_0001"' in bundle.html
    assert "var generated = 4;" in bundle.js
    assert "document.getElementById('fuzion_domato_0001')" in bundle.js or 'document.getElementById("fuzion_domato_0001")' in bundle.js
