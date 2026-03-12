from __future__ import annotations

from pathlib import Path
import random
import re

from .campaign_domato import domato_available, generate_bundle, generate_css_rules, generate_html_fragment, generate_js_fragment
from .campaign_triage import extract_features_from_text


_SCRIPT_RE = r"<script[^>]*>(.*?)</script>"
_STYLE_RE = r"<style[^>]*>(.*?)</style>"
_BODY_RE = r"<body[^>]*>(.*?)</body>"
_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "source",
    "track",
    "wbr",
}


def _spans(text: str, pattern: str) -> list[tuple[int, int]]:
    return [match.span(1) for match in re.finditer(pattern, text, flags=re.IGNORECASE | re.DOTALL)]


def _pick_span(text: str, pattern: str, rng: random.Random) -> tuple[int, int] | None:
    spans = _spans(text, pattern)
    return rng.choice(spans) if spans else None


def _replace(text: str, span: tuple[int, int], replacement: str) -> str:
    return text[: span[0]] + replacement + text[span[1] :]


def _weighted_pick(options: list[tuple[str, int, callable]], rng: random.Random):
    total = sum(weight for _, weight, _ in options)
    pick = rng.randrange(total)
    for option in options:
        pick -= option[1]
        if pick < 0:
            return option
    return options[-1]


def _mutate_span(html: str, pattern: str, rng: random.Random, mutate_block) -> str | None:
    span = _pick_span(html, pattern, rng)
    if span is None:
        return None
    block = html[span[0] : span[1]]
    mutated = mutate_block(block)
    if mutated == block:
        return None
    return _replace(html, span, mutated)


def _statement_spans(text: str) -> list[tuple[int, int]]:
    spans = []
    start = 0
    parens = 0
    brackets = 0
    quote = ""
    escaped = False

    for index, char in enumerate(text):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char in {"'", '"', "`"}:
            quote = char
            continue
        if char == "(":
            parens += 1
        elif char == ")" and parens:
            parens -= 1
        elif char == "[":
            brackets += 1
        elif char == "]" and brackets:
            brackets -= 1
        elif char == ";" and not parens and not brackets:
            if text[start : index + 1].strip():
                spans.append((start, index + 1))
            start = index + 1
    if text[start:].strip():
        spans.append((start, len(text)))
    return spans


def _duplicate_statement(block: str, rng: random.Random) -> str:
    spans = _statement_spans(block)
    if not spans:
        return block
    start, end = rng.choice(spans)
    statement = block[start:end].strip()
    if not statement:
        return block
    suffix = "" if block.endswith("\n") else "\n"
    return block + suffix + statement + "\n"


def _duplicate_rule(block: str, rng: random.Random) -> str:
    rules = [match.group(0).strip() for match in re.finditer(r"[^{}]+\{[^{}]*\}", block, flags=re.DOTALL)]
    rules = [rule for rule in rules if rule]
    if not rules:
        return block
    suffix = "" if block.endswith("\n") else "\n"
    return block + suffix + rng.choice(rules) + "\n"


def _body_fragments(block: str) -> list[tuple[int, int]]:
    stack: list[tuple[str, int]] = []
    fragments: list[tuple[int, int]] = []

    for match in re.finditer(r"</?([a-zA-Z][\w:-]*)\b[^>]*>", block):
        raw = match.group(0)
        tag = match.group(1).lower()
        if raw.startswith("</"):
            while stack and stack[-1][0] != tag:
                stack.pop()
            if stack:
                _, start = stack.pop()
                fragments.append((start, match.end()))
        elif not raw.endswith("/>") and tag not in _VOID_TAGS:
            stack.append((tag, match.start()))
    return fragments


def _duplicate_fragment(block: str, rng: random.Random) -> str:
    fragments = _body_fragments(block)
    if not fragments:
        return block
    start, end = rng.choice(fragments)
    suffix = "" if block.endswith("\n") else "\n"
    return block + suffix + block[start:end] + "\n"


def _wrap_fragment(block: str, rng: random.Random) -> str:
    fragments = _body_fragments(block)
    if not fragments:
        return block
    start, end = rng.choice(fragments)
    wrapper = rng.choice(["div", "section", "article"])
    return block[:start] + f"<{wrapper} data-fuzion-wrap=\"1\">{block[start:end]}</{wrapper}>" + block[end:]


def _number_options(value: int) -> list[int]:
    options = {
        -1,
        0,
        1,
        2,
        16,
        255,
        256,
        1024,
        4096,
        65535,
        1048576,
        value - 1,
        value + 1,
        value * 2,
        value * 4,
    }
    if value < 0:
        options.update({-2, -16, -value})
    choices = [item for item in sorted(options) if item != value]
    return choices or [value + 1]


def _tweak_number(text: str, rng: random.Random) -> str:
    matches = list(re.finditer(r"(?<![\w#])-?\d+(?![\w-])", text))
    if not matches:
        return text
    match = rng.choice(matches)
    replacement = str(rng.choice(_number_options(int(match.group(0)))))
    return text[: match.start()] + replacement + text[match.end() :]


def _tweak_section_number(html: str, pattern: str, rng: random.Random) -> str | None:
    span = _pick_span(html, pattern, rng)
    if span is None:
        return None
    block = html[span[0] : span[1]]
    mutated = _tweak_number(block, rng)
    if mutated == block:
        return None
    return _replace(html, span, mutated)


def _insert_before_close(html: str, tag: str, chunk: str) -> str | None:
    close_tag = f"</{tag}>"
    index = html.lower().rfind(close_tag)
    if index < 0:
        return None
    return html[:index] + chunk + html[index:]


def _append_script(html: str, script: str) -> str | None:
    return _insert_before_close(html, "body", f"<script>\n{script}\n</script>\n") or _insert_before_close(html, "html", f"<script>\n{script}\n</script>\n")


def _append_style(html: str, css: str) -> str | None:
    return _insert_before_close(html, "head", f"<style>\n{css}\n</style>\n") or _insert_before_close(html, "html", f"<style>\n{css}\n</style>\n")


def _append_markup(html: str, fragment: str) -> str:
    chunk = fragment.rstrip() + "\n"
    return _insert_before_close(html, "body", chunk) or _insert_before_close(html, "html", chunk) or (html + "\n" + chunk)


def _append_domato_css(html: str, rng: random.Random, domato_dir: Path) -> str | None:
    css = generate_css_rules(domato_dir, seed=rng.randint(0, 2**31 - 1))
    span = _pick_span(html, _STYLE_RE, rng)
    if span is None:
        return _append_style(html, css)
    block = html[span[0] : span[1]]
    suffix = "" if block.endswith("\n") else "\n"
    return _replace(html, span, block + suffix + css + "\n")


def _append_domato_bundle(html: str, rng: random.Random, domato_dir: Path) -> str | None:
    bundle = generate_bundle(domato_dir, js_lines=rng.randint(2, 6), seed=rng.randint(0, 2**31 - 1))
    mutated = _append_markup(html, bundle.html)
    mutated = _append_style(mutated, bundle.css) or mutated
    mutated = _append_script(mutated, bundle.js) or mutated
    return mutated


def _fallback_markup(rng: random.Random) -> str:
    return rng.choice(
        [
            "<div data-fuzion=\"1\"></div>",
            "<span data-fuzion=\"1\"></span>",
            "<p data-fuzion=\"1\"></p>",
        ]
    )


def _mutation_options(html: str, rng: random.Random, domato_dir: Path | None) -> list[tuple[str, int, callable]]:
    features = extract_features_from_text(html)
    options: list[tuple[str, int, callable]] = [
        ("append_html_fragment", 1, lambda: _append_markup(html, _fallback_markup(rng))),
    ]

    has_script = bool(_spans(html, _SCRIPT_RE))
    has_style = bool(_spans(html, _STYLE_RE))
    has_body = bool(_spans(html, _BODY_RE))

    if has_script:
        options.extend(
            [
                (
                    "duplicate_js_statement",
                    5 if features["script_count"] <= 2 else 4,
                    lambda: _mutate_span(html, _SCRIPT_RE, rng, lambda block: _duplicate_statement(block, rng)),
                ),
                ("tweak_js_numeric_literal", 3, lambda: _tweak_section_number(html, _SCRIPT_RE, rng)),
            ]
        )

    if has_style:
        options.extend(
            [
                (
                    "duplicate_css_rule",
                    4,
                    lambda: _mutate_span(html, _STYLE_RE, rng, lambda block: _duplicate_rule(block, rng)),
                ),
                ("tweak_css_numeric_literal", 2, lambda: _tweak_section_number(html, _STYLE_RE, rng)),
            ]
        )

    if has_body:
        options.extend(
            [
                (
                    "duplicate_body_fragment",
                    4 if features["script_count"] == 0 else 3,
                    lambda: _mutate_span(html, _BODY_RE, rng, lambda block: _duplicate_fragment(block, rng)),
                ),
                (
                    "wrap_body_fragment",
                    3 if features["max_nesting"] < 40 else 2,
                    lambda: _mutate_span(html, _BODY_RE, rng, lambda block: _wrap_fragment(block, rng)),
                ),
            ]
        )

    if domato_dir is None or not domato_available(domato_dir):
        return options

    if _append_script(html, "") is not None:
        options.append(
            (
                "append_domato_js_fragment",
                2 if has_script else 3,
                lambda: _append_script(
                    html,
                    generate_js_fragment(
                        domato_dir,
                        html=html,
                        lines=rng.randint(2, 6),
                        seed=rng.randint(0, 2**31 - 1),
                    ),
                ),
            )
        )
        options.append(
            (
                "append_domato_bundle",
                2 if not has_script and not has_style else 1,
                lambda: _append_domato_bundle(html, rng, domato_dir),
            )
        )

    if _append_style(html, "") is not None or has_style:
        options.append(
            (
                "append_domato_css_fragment",
                1 if has_style else 2,
                lambda: _append_domato_css(html, rng, domato_dir),
            )
        )

    options.append(
        (
            "append_domato_html_fragment",
            1 if has_body else 2,
            lambda: _append_markup(
                html,
                generate_html_fragment(domato_dir, seed=rng.randint(0, 2**31 - 1)),
            ),
        )
    )
    return options


def mutate_html(
    html: str,
    *,
    rng: random.Random | None = None,
    domato_dir: Path | None = None,
) -> tuple[str, str]:
    rng = rng or random.Random()
    options = list(_mutation_options(html, rng, domato_dir))
    while options:
        name, _weight, build = _weighted_pick(options, rng)
        mutated = build()
        if mutated is not None and mutated != html:
            return mutated, name
        options = [item for item in options if item[0] != name]
    return _append_markup(html, _fallback_markup(rng)), "append_html_fragment"


def mutate_file(
    source_path: Path,
    output_path: Path,
    *,
    rng: random.Random | None = None,
    domato_dir: Path | None = None,
) -> str:
    html = source_path.read_text(encoding="utf-8", errors="ignore")
    mutated, mutator = mutate_html(html, rng=rng, domato_dir=domato_dir)
    output_path.write_text(mutated, encoding="utf-8")
    return mutator
