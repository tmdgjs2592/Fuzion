# Test Pages

Purposefully errored HTML pages to verify the output report detects
different failure types. Use these to demo the pipeline or validate that
detection logic is working after code changes.

## Pages

| File | Expected Result | What It Does |
|------|----------------|--------------|
| `crash_oom.html` | **crash** | Allocates memory in an infinite loop until Chrome's renderer runs out of memory |
| `crash_deep_dom.html` | **crash** | Creates 50,000 deeply nested divs, overwhelming the rendering engine |
| `timeout_infinite_loop.html` | **timeout** | Runs `while(true){}` before the page loads, blocking the load event |
| `ok_normal.html` | **ok** | A normal page that loads fine (control case) |

## How to Run

```bash
# Run the pipeline first so we can create the out/ folder and generates testcases
# if you already have the out/ folder, you don't need to do this
fuzion

# Copy test pages into the corpus alongside the generated files
cp test_pages/*.html out/corpus/

# Run the pipeline again so it also executes the test pages, u can enter 0 generated files
fuzion

# Generate the HTML report
python -m fuzion.report

# Open the report
open out/report.html
```
