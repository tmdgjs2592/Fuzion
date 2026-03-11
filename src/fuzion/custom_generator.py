"""
Custom grammar-based HTML generator for Fuzion.

Reads generation rules from a YAML file (grammars/html_rules.yaml) and
randomly assembles HTML pages by combining tags and attributes.
The goal is to produce syntactically valid but semantically
unusual webpages that may trigger browser bugs.
"""

import logging
import random
import yaml
from pathlib import Path
from .util import ensure_dir

logger = logging.getLogger(__name__)


# Load grammar rules from YAML file
def load_rules(rules_path: Path) -> dict:
    logger.debug("Loading grammar rules from %s", rules_path)
    rules = yaml.safe_load(rules_path.read_text())
    logger.debug(
        "Loaded rules: %d block tags, %d inline tags, %d global attributes",
        len(rules.get("tags", {}).get("block", [])),
        len(rules.get("tags", {}).get("inline", [])),
        len(rules.get("attributes", {}).get("global", [])),
    )
    return rules


# Generate random HTML attributes for an element (0-3 attrs)
def _random_attributes(rules: dict) -> str:
    attrs = []
    global_attrs = rules["attributes"]["global"]
    values_map = rules["attributes"]["values"]

    num_attrs = random.randint(0, 3)
    chosen = random.sample(global_attrs, min(num_attrs, len(global_attrs)))
    logger.debug("Generating %d attribute(s) from pool of %d", num_attrs, len(global_attrs))

    for attr in chosen:
        if attr == "hidden":
            # only add hidden 30% of the time so not everything is invisible
            if random.random() < 0.3:
                attrs.append("hidden")
                logger.debug("Attribute 'hidden' selected (30%% chance triggered)")
            else:
                logger.debug("Attribute 'hidden' skipped (30%% chance not triggered)")
        elif attr in values_map:
            val = random.choice(values_map[attr])
            attrs.append(f'{attr}="{val}"')
            logger.debug("Attribute '%s' assigned mapped value '%s'", attr, val)
        else:
            fuzz_val = random.randint(0, 99)
            attrs.append(f'{attr}="fuzz{fuzz_val}"')
            logger.debug("Attribute '%s' assigned fuzz value 'fuzz%d'", attr, fuzz_val)

    result = " ".join(attrs)
    logger.debug("Final attribute string: %r", result)
    return result


# Pick a random tag from all block + inline tags
def _random_tag(rules: dict) -> str:
    all_tags = rules["tags"]["block"] + rules["tags"]["inline"]
    tag = random.choice(all_tags)
    logger.debug("Selected tag '%s' from pool of %d tags", tag, len(all_tags))
    return tag


# Self-closing tags that don't have children
VOID_TAGS = {"img", "input", "br", "hr", "meta", "link", "area",
             "base", "col", "embed", "source", "track", "wbr"}

def _generate_script(rules: dict) -> str:
    patterns = rules.get("js_patterns", [])
    if not patterns:
        return ""
    pattern = random.choice(patterns)
    logger.debug("Selected JS pattern: %r", pattern[:50])
    return f"<script>\n{pattern}\n</script>"

# Recursively build a random DOM node with children up to max_depth
def _generate_node(rules: dict, depth: int) -> str:
    max_depth = rules.get("max_depth", 8)
    max_children = rules.get("max_children", 5)

    tag = _random_tag(rules)
    attrs = _random_attributes(rules)
    open_tag = f"<{tag} {attrs}>" if attrs else f"<{tag}>"
    logger.debug("Generating node at depth %d: tag='%s', void=%s", depth, tag, tag in VOID_TAGS)

    # void tags like <img> and <input> are self-closing
    if tag in VOID_TAGS:
        logger.debug("Tag '%s' is void, returning self-closing element", tag)
        return open_tag

    # at max depth, just add text instead of more children
    if depth >= max_depth:
        logger.debug("Reached max_depth=%d for tag '%s', inserting text leaf", max_depth, tag)
        return f"{open_tag}{tag}content</{tag}>"

    num_children = random.randint(0, max_children)
    logger.debug("Tag '%s' at depth %d will have %d child(ren)", tag, depth, num_children)
    children = "\n".join(_generate_node(rules, depth + 1) for _ in range(num_children))

    return f"{open_tag}\n{children}\n</{tag}>"


# Build a full HTML page with a random DOM tree
def generate_page(rules: dict) -> str:
    num_top_level = random.randint(3, 8)
    logger.debug("Generating page with %d top-level node(s)", num_top_level)
    body_content = "\n".join(_generate_node(rules, 0) for _ in range(num_top_level))
    script = _generate_script(rules)
    logger.debug("Page body assembled, total body length: %d chars", len(body_content))

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Fuzion Generated</title>
</head>
<body>
{body_content}
{script}
</body>
</html>"""


# Generate n random HTML files and save to corpus_dir
def generate_custom_files(*, rules_path: Path, corpus_dir: Path, n: int, seed: int = None) -> None:
    logger.debug(
        "generate_custom_files called: rules_path=%s, corpus_dir=%s, n=%d, seed=%s",
        rules_path, corpus_dir, n, seed,
    )

    # optional seed for reproducible generation
    if seed is not None:
        random.seed(seed)
        logger.debug("Random seed set to %d for reproducible generation", seed)

    ensure_dir(corpus_dir)
    rules = load_rules(rules_path)

    for i in range(1, n + 1):
        logger.debug("Generating testcase %d of %d", i, n)
        html = generate_page(rules)
        out_file = corpus_dir / f"custom_{i:06d}.html"
        out_file.write_text(html)
        logger.debug("Wrote testcase %d to %s (%d bytes)", i, out_file, len(html))

    logger.debug("Finished generating %d testcase(s) in %s", n, corpus_dir)
    print(f"Generated {n} custom testcases in {corpus_dir}")


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    generate_custom_files(
        rules_path=root / "grammars" / "html_rules.yaml",
        corpus_dir=root / "out" / "corpus",
        n=10,
    )