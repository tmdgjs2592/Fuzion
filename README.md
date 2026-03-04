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
│       ├── orchestrator.py
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
```

or on Windows Powershell use 
```
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\.venv\Scripts\Activate.ps1
```
And then for both systems use
```
pip install -U pip
pip install -e .
python -m playwright install chromium
```
Run `fuzion` in the repository.
For developers only:
Run `fuzion --debug` to get extremely verbose logging statements for debugging purposes.

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

## Disclaimer of AI-Usage 
We chose to utilize AI in our project purely for the task of adding repetitive low impact but verbose logging statements in late stages of development. The AI model used was Claude’s Sonnet 4.6. 
All generated code was human reviewed to ensure functionality was not touched and only logging statements were added. 
The chat logs can be reviewed here: https://claude.ai/share/9e7e4d65-4903-45a4-81ae-9f7503332f0c 
