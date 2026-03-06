# Fuzion: Grammar-Based Browser Fuzzing Automation

## 1. Introduction

Modern web browsers are among the most complex software systems in existence. They implement massive rendering engines, JavaScript runtimes, networking stacks, and sandboxed multi-process architectures. Given this complexity, browsers remain a target for security vulnerabilities, including memory corruption, renderer crashes, and denial-of-service bugs.

Fuzion was developed as a lightweight, terminal-based fuzzing harness designed for browser developers, security engineers, and students. Its primary goal is to discover stability and memory safety issues in modern browsers by automatically generating diverse and unexpected webpage inputs and executing them in a controlled headless environment.

---

## 2. Design Goals

Fuzion was built with the following design principles:

1. Fully automated input generation  
    No manual editing of testcases during fuzzing runs.
2. Isolation and reproducibility  
    Each testcase runs in its own browser profile directory.
3. Deterministic classification  
    Each run is categorized into one of:
    - ok
    - crash
    - timeout
    - hang
    - error
4. Terminal-first workflow  
    Users specify:
    - number of HTML files
    - desired format (HTML-only, HTML+CSS, HTML+JS, HTML+CSS+JS, or custom)

---
## 3. System Architecture

### 3.1 High-Level Pipeline

The fuzzing pipeline consists of three main stages:

1. Generation  
    Domato generates N syntactically valid HTML testcases using grammar templates.

2. Execution  
    Each HTML file is:
    - Served via a local HTTP server
    - Loaded in headless Chromium
    - Executed within an isolated persistent context

3. Triage  
    Execution results are classified and artifacts are saved for abnormal behavior.

### 3.2 Repository Structure

```
Fuzion/  
├── README.md  
├── pyproject.toml  
├── grammars/  
│   └── bundles.yaml  
├── templates/  
│   ├── html_only.html  
│   ├── html_css.html  
│   ├── html_js.html  
│   └── html_css_js.html  
├── src/  
│   └── fuzion/  
│       ├── config.py  
│       ├── main.py  
│       ├── tui.py  
│       ├── generate.py  
│       ├── run.py  
│       ├── triage.py  
│       └── util.py  
├── third_party/  
│   └── domato/  
└── out/  
    ├── corpus/  
    └── findings/
```

The `out/` directory is not version-controlled and contains generated inputs and saved artifacts.

---
## 4. Input Generation ([Domato][https://github.com/googleprojectzero/domato])

Fuzion leverages Domato, a grammar-based generator originally developed by Google Project Zero. Domato produces syntactically valid but structurally diverse HTML, CSS, and JavaScript.

### 4.1 Template-Based Injection

Fuzion selects a template based on user input:

- html_only
- html_css
- html_js
- html_css_js

Each template contains placeholders recognized by Domato like `<cssfuzzer>`. During generation, Domato replaces those placeholders with generated content.

Example template
```
<!doctype html>
<html>
<head>
	<meta charset="utf-8">
	<style><cssfuzzer></style>
</head>
<body>
	<script><jsfuzzer></script>
</body>
</html>
```

Example command used:
	`python generator.py -o OUTPUT_DIR -n N -t TEMPLATE

---
## 5. Execution Engine

### 5.1 Headless Chromium

Fuzion uses Playwright to launch headless Chromium.

Two approaches considered:
- `launch()` → manual context creation
- `launch_persistent_context()` → profile-backed context

Fuzion uses:

`launch_persistent_context(user_data_dir, headless=True, ...)`

This enables:
- Per-testcase isolated profile directories
- Crash artifacts tied to that testcase
- More realistic browser execution state

### 5.2 Local HTTP Server

Testcases are served via a local HTTP server rather than `file://` URLs to:

- Avoid origin restrictions
- Enable proper resource loading behavior
- Simulate realistic browser networking conditions

---
## 6. Timeout and Hang Detection

Fuzion implements two distinct timeout mechanisms:
- Navigation Timeout
- Hard Timeout
### 6.1 Navigation Timeout

Purpose:
- Detect slow or incomplete page loads
Classification:
- timeout
- Hard Timeout
### 6.2 Hard Timeout

Purpose:
- Detect infinite loops
- Detect renderer freezes
- Prevent fuzzer stalling

Classification:
- hang

---
## 7. Crash and Error Classification

Each testcase is classified as:
- ok  
    Page loaded without crash or timeout.
- crash  
    Playwright page crash event triggered.
- timeout  
    Navigation exceeded configured navigation timeout.
- hang  
    Hard watchdog timeout exceeded.
- error  
    Unexpected runner or browser exception.

Abnormal testcases (like timeout status) are preserved in:
	`out/findings/<testcase_id>/`

Artifacts include:
- input.html
- meta.json
- user-data-dir/

---
## 8. Test Results

During testing:
- All grammar-generated pages executed without browser crashes.
- Artificially constructed stress pages successfully triggered:
    - Infinite loop hangs
    - Navigation timeouts
    - Uncaught JS exceptions
    - Resource load failures

This confirms:
- The classification system functions correctly.
- The watchdog prevents fuzzer stalling.
- Artifact capture works as expected.

No memory corruption crashes were observed in stock Chromium builds during limited testing. This is expected without ASAN-enabled builds or large-scale corpus mutation.

---
## 9. Challenges Encountered

### 9.1 Domato CLI Mismatch

Initial attempts passed incorrect CLI arguments (e.g., `htmlgrammar` positional argument). This caused exit code 2 errors.

Resolution:
- Verified generator flags using `--help`
- Switched to `-o`, `-n`, `-t` format

### 9.2 Playwright Launch Error

Initially, `Playwright.chromium.launch` was called for runner with `user_data_dir`. This produces errors as `launch()` function creates a browser process, not a persistent profile.

Resolution:
- Switched to `Playwright.chromium.launch_persistent_context`
- Verified it working by the returned meta data.

### 9.3 Template Placeholder Issues

Generated outputs initially matched templates exactly.

Root cause:
- Templates did not contain Domato placeholder markers.

Resolution:
- Identified required slot strings in generator.py
- Updated templates accordingly

---
## 10. Future Work

Potential improvements include:
- Vigorous generator
- Crash signature hashing and bucketing
- CDP-level crash event tracking
- Coverage feedback integration
- Corpus minimization
- Docker-based Linux-x64 runner
- Replay command for saved artifacts

---
## 12. Conclusion

Fuzion successfully demonstrates a modular, reproducible grammar-based browser fuzzing harness capable of generating diverse HTML inputs and classifying execution outcomes in headless Chromium.

While not yet a full-scale production fuzzer, it provides:
- Educational insight into browser fuzzing architecture
- A practical testbed for experimentation
- A foundation for future research into browser stability and memory safety

The project highlights the importance of structured input generation, strict execution isolation, and deterministic classification when building fuzzing infrastructure.