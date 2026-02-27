"""
Custom grammar-based HTML generator for Fuzion.

Reads generation rules from a YAML file (grammars/html_rules.yaml) and
randomly assembles HTML pages by combining tags and attributes.
The goal is to produce syntactically valid but semantically
unusual webpages that may trigger browser bugs.
"""

import random
import yaml
from pathlib import Path
from .util import ensure_dir


# Load grammar rules from YAML file
def load_rules(rules_path: Path) -> dict:
    return yaml.safe_load(rules_path.read_text())


# Generate random HTML attributes for an element (0-3 attrs)
def _random_attributes(rules: dict) -> str:
    attrs = []
    global_attrs = rules["attributes"]["global"]
    values_map = rules["attributes"]["values"]

    num_attrs = random.randint(0, 3)
    chosen = random.sample(global_attrs, min(num_attrs, len(global_attrs)))

    for attr in chosen:
        if attr == "hidden":
            # only add hidden 30% of the time so not everything is invisible
            if random.random() < 0.3:
                attrs.append("hidden")
        elif attr in values_map:
            val = random.choice(values_map[attr])
            attrs.append(f'{attr}="{val}"')
        else:
            attrs.append(f'{attr}="fuzz{random.randint(0, 99)}"')

    return " ".join(attrs)


# Pick a random tag from all block + inline tags
def _random_tag(rules: dict) -> str:
    all_tags = rules["tags"]["block"] + rules["tags"]["inline"]
    return random.choice(all_tags)


# Self-closing tags that don't have children
VOID_TAGS = {"img", "input", "br", "hr", "meta", "link", "area",
             "base", "col", "embed", "source", "track", "wbr"}


# Recursively build a random DOM node with children up to max_depth
def _generate_node(rules: dict, depth: int) -> str:
    max_depth = rules.get("max_depth", 8)
    max_children = rules.get("max_children", 5)

    tag = _random_tag(rules)
    attrs = _random_attributes(rules)
    open_tag = f"<{tag} {attrs}>" if attrs else f"<{tag}>"

    # void tags like <img> and <input> are self-closing
    if tag in VOID_TAGS:
        return open_tag

    # at max depth, just add text instead of more children
    if depth >= max_depth:
        return f"{open_tag}{tag}content</{tag}>"

    num_children = random.randint(0, max_children)
    children = "\n".join(_generate_node(rules, depth + 1) for _ in range(num_children))

    return f"{open_tag}\n{children}\n</{tag}>"


# Build a full HTML page with a random DOM tree
def generate_page(rules: dict) -> str:
    num_top_level = random.randint(3, 8)
    body_content = "\n".join(_generate_node(rules, 0) for _ in range(num_top_level))

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Fuzion Generated</title>
</head>
<body>
{body_content}
</body>
</html>"""


# Generate n random HTML files and save to corpus_dir
def generate_custom_files(*, rules_path: Path, corpus_dir: Path, n: int, seed: int = None) -> None:
    # optional seed for reproducible generation
    if seed is not None:
        random.seed(seed)

    ensure_dir(corpus_dir)
    rules = load_rules(rules_path)

    for i in range(1, n + 1):
        html = generate_page(rules)
        out_file = corpus_dir / f"custom_{i:06d}.html"
        out_file.write_text(html)

    print(f"Generated {n} custom testcases in {corpus_dir}")


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    generate_custom_files(
        rules_path=root / "grammars" / "html_rules.yaml",
        corpus_dir=root / "out" / "corpus",
        n=10,
    )
