# Fuzion 
Fuzion is a terminal-first browser fuzzing harness for **browser developers, security engineers, and students**.  

It generates **syntactically valid** (but semantically weird) webpages using a **Domato-style grammar engine**, runs them in **headless Chromium**, and **triages** unusual behavior like **crashes, timeouts, and hangs**, saving the artifacts for debugging.


## Repo Structure
```
Fuzion/
├── README.md
├── pyproject.toml
│
├── grammars/
│   └── bundles.yaml
│
├── templates/
│   ├── html_only.html
│   ├── html_css.html
│   ├── html_js.html
│   └── html_css_js.html
│
├── src/
│   └── fuzion/
│       ├── __init__.py
│       ├── config.py
│       ├── main.py
│       ├── tui.py
│       ├── generate.py
│       ├── run.py
│       ├── triage.py
│       └── util.py
│
├── third_party/
│   └── domato/        # recommended as a git submodule
│
└── out/               # (gitignored)
    ├── corpus/        # generated HTML testcases
    └── findings/      # saved artifacts for abnormal runs
```

## Requirements
- [Domato](https://github.com/googleprojectzero/domato)
- - `git clone https://github.com/googleprojectzero/domato third_party/domato`
- Microsoft Visual C++ Redistributable
- Python 3.10 +

## Setup
Create a virtual env and install dependencies
```
python3 -m venv .venv
source .venv/bin/activate
or .venv/Scripts/activate on Windows/bash
pip install -U pip
pip install -e .
python -m playwright install chromium
```
Run `fuzion` in the repository.

You’ll be prompted for:
```
Format:
html_only
html_css
html_js
html_css_js
```
Number of HTML files to generate

Fuzion will then:

- Generate inputs into out/corpus/
- Execute them in headless Chromium
- Save artifacts for abnormal behavior into out/findings/

## Output / Artifacts
Generated corpus

```
out/corpus/*.html
```

Naming example:
```
html_only_000001.html
html_css_000123.html
```
