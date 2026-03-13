from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import random
import re


@dataclass(frozen=True)
class DomatoVariable:
    name: str
    type_name: str
    declaration: str


@dataclass(frozen=True)
class DomatoBundle:
    html: str
    css: str
    js: str


def domato_available(domato_dir: Path) -> bool:
    required = (
        "grammar.py",
        "rules/html.txt",
        "rules/css.txt",
        "rules/js.txt",
        "html_tags.py",
        "svg_tags.py",
        "mathml_tags.py",
    )
    return all((domato_dir / name).is_file() for name in required)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=None)
def _grammar_class(domato_dir: Path):
    return _load_module("fuzion_campaign_domato_grammar", domato_dir / "grammar.py").Grammar


@lru_cache(maxsize=None)
def _tag_types(domato_dir: Path) -> dict[str, str]:
    merged: dict[str, str] = {}
    modules = (
        ("fuzion_campaign_html_tags", "html_tags.py", "_HTML_TYPES"),
        ("fuzion_campaign_svg_tags", "svg_tags.py", "_SVG_TYPES"),
        ("fuzion_campaign_mathml_tags", "mathml_tags.py", "_MATHML_TYPES"),
    )
    for module_name, filename, attr in modules:
        values = getattr(_load_module(module_name, domato_dir / filename), attr)
        merged.update({key.lower(): value for key, value in values.items()})
    return merged


@lru_cache(maxsize=None)
def _grammars(domato_dir: Path):
    grammar_class = _grammar_class(domato_dir)
    html = grammar_class()
    css = grammar_class()
    js = grammar_class()
    html.parse_from_file(str(domato_dir / "rules" / "html.txt"))
    css.parse_from_file(str(domato_dir / "rules" / "css.txt"))
    js.parse_from_file(str(domato_dir / "rules" / "js.txt"))
    html.add_import("cssgrammar", css)
    js.add_import("cssgrammar", css)
    return html, css, js


def _with_seed(seed: int | None, build):
    state = random.getstate()
    try:
        if seed is not None:
            random.seed(seed)
        return build()
    finally:
        random.setstate(state)


def _variable_dicts(variables: list[DomatoVariable]) -> list[dict]:
    return [{"name": item.name, "type": item.type_name} for item in variables]


def _wrap_js(js: str, variables: list[DomatoVariable]) -> str:
    declarations = "\n".join(item.declaration for item in variables if item.declaration)
    return "\n".join(
        [
            "(function() {",
            "var fuzzervars = {};",
            "function GetVariable(vars, type) { return vars[type] || null; }",
            "function SetVariable(vars, value, type) { vars[type] = value; }",
            "try { SetVariable(fuzzervars, window, 'Window'); } catch (e) {}",
            "try { SetVariable(fuzzervars, document, 'Document'); } catch (e) {}",
            "try { SetVariable(fuzzervars, document.body && document.body.firstChild, 'Element'); } catch (e) {}",
            declarations,
            js.strip(),
            "})();",
        ]
    )


def _existing_dom_variables(domato_dir: Path, html: str, *, limit: int = 12) -> list[DomatoVariable]:
    tag_types = _tag_types(domato_dir)
    variables: list[DomatoVariable] = []
    seen_ids: set[str] = set()
    seen_positions: dict[str, int] = {}

    for match in re.finditer(r"<([a-zA-Z][\w:-]*)([^<>]*)>", html):
        tag = match.group(1).lower()
        attrs = match.group(2)
        if tag not in tag_types or tag in {"html", "head", "body", "script", "style"}:
            continue
        if len(variables) >= limit:
            break

        attr_id = re.search(r"""\bid\s*=\s*["']([^"']+)["']""", attrs, flags=re.IGNORECASE)
        name = f"htmlvar{len(variables) + 1:05d}"
        if attr_id and attr_id.group(1) not in seen_ids:
            element_id = attr_id.group(1)
            seen_ids.add(element_id)
            declaration = f"var {name} = document.getElementById({element_id!r});"
        else:
            index = seen_positions.get(tag, 0)
            seen_positions[tag] = index + 1
            declaration = f"var {name} = document.getElementsByTagName({tag!r})[{index}];"
        variables.append(DomatoVariable(name=name, type_name=tag_types[tag], declaration=declaration))
    return variables


def _annotate_fragment(domato_dir: Path, html: str, *, limit: int = 10) -> tuple[str, list[DomatoVariable]]:
    tag_types = _tag_types(domato_dir)
    replacements: list[tuple[int, int, str]] = []
    variables: list[DomatoVariable] = []
    count = 0

    for match in re.finditer(r"<([a-zA-Z][\w:-]*)([^<>]*?)(/?)>", html):
        tag = match.group(1).lower()
        if tag not in tag_types or tag in {"script", "style"} or count >= limit:
            continue

        attrs = match.group(2)
        self_close = match.group(3)
        attr_id = re.search(r"""\bid\s*=\s*["']([^"']+)["']""", attrs, flags=re.IGNORECASE)
        if attr_id:
            element_id = attr_id.group(1)
            replacement = match.group(0)
        else:
            element_id = f"fuzion_domato_{count + 1:04d}"
            insert_at = match.end() - 1 - len(self_close)
            relative = insert_at - match.start()
            replacement = match.group(0)[:relative] + f' id="{element_id}"' + match.group(0)[relative:]

        replacements.append((match.start(), match.end(), replacement))
        count += 1
        name = f"htmlvar{count:05d}"
        variables.append(
            DomatoVariable(
                name=name,
                type_name=tag_types[tag],
                declaration=f"var {name} = document.getElementById({element_id!r});",
            )
        )

    if not replacements:
        return html, variables

    parts: list[str] = []
    cursor = 0
    for start, end, replacement in replacements:
        parts.append(html[cursor:start])
        parts.append(replacement)
        cursor = end
    parts.append(html[cursor:])
    return "".join(parts), variables


def _require_grammars(domato_dir: Path):
    if not domato_available(domato_dir):
        raise FileNotFoundError(domato_dir)
    return _grammars(domato_dir)


def generate_html_fragment(domato_dir: Path, *, seed: int | None = None) -> str:
    html, _, _ = _require_grammars(domato_dir)
    return _with_seed(seed, lambda: html.generate_symbol("bodyelements"))


def generate_css_rules(domato_dir: Path, *, seed: int | None = None) -> str:
    _, css, _ = _require_grammars(domato_dir)
    return _with_seed(seed, lambda: css.generate_symbol("rules"))


def generate_js_fragment(
    domato_dir: Path,
    *,
    html: str,
    lines: int = 4,
    seed: int | None = None,
) -> str:
    _, _, js = _require_grammars(domato_dir)
    variables = _existing_dom_variables(domato_dir, html)
    body = _with_seed(seed, lambda: js._generate_code(max(1, lines), _variable_dicts(variables)))
    return _wrap_js(body, variables)


def generate_bundle(domato_dir: Path, *, js_lines: int = 4, seed: int | None = None) -> DomatoBundle:
    html, css, js = _require_grammars(domato_dir)

    def build() -> DomatoBundle:
        html_fragment = html.generate_symbol("bodyelements")
        html_fragment, variables = _annotate_fragment(domato_dir, html_fragment)
        css_rules = css.generate_symbol("rules")
        js_body = js._generate_code(max(1, js_lines), _variable_dicts(variables))
        return DomatoBundle(
            html=html_fragment,
            css=css_rules,
            js=_wrap_js(js_body, variables),
        )

    return _with_seed(seed, build)
