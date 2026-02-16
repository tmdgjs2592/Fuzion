from dotenv import load_dotenv
import os
import glob
import time
import json

from runner.chromium_runner import ChromiumRunner

load_dotenv()
chrome_path = os.getenv("CHROME_PATH")
if not chrome_path:
    raise RuntimeError("CHROME_PATH not set in .env")

debug = os.getenv("DEBUG", "false").lower() == "true"


runner = ChromiumRunner(chrome_path=chrome_path, timeout=5, debug=debug)

input_dir = "corpus/generated"
html_files = sorted(glob.glob(os.path.join(input_dir, "*.html")))

os.makedirs("corpus/runs", exist_ok=True)

results = []
stats = {
    "ok": 0,
    "crash": 0,
    "timeout": 0
}

global_start = time.time()

print(f"{len(html_files)} testcases in {input_dir}")
for i, path in enumerate(html_files, 1):
    try:
        t0 = time.time()
        res = runner.run(path)
        runtime_ms = int((time.time() - t0) * 1000)

        res["testcase"] = path
        res["runtime_ms"] = runtime_ms
        results.append(res)
        stats[res["status"]] += 1

        run_id = f"run-{i:05d}"
        run_dir = os.path.join("corpus/runs", run_id)
        os.makedirs(run_dir, exist_ok=True)

        with open(os.path.join(run_dir, "stderr.txt"), "w", encoding="utf-8") as f:
            f.write(res.get("stderr", ""))

        with open(os.path.join(run_dir, "result.json"), "w") as f:
            json.dump(res, f, indent=2)

        print(f"[{i}/{len(html_files)}] {os.path.basename(path)} -> {res['status']}")

    except Exception:
        print("\nFAILED ON:", path)
        raise

total_runtime_ms = int((time.time() - global_start) * 1000)

summary = {
    "total_testcases": len(html_files),
    "ok": stats["ok"],
    "crash": stats["crash"],
    "timeout": stats["timeout"],
    "total_runtime_ms": total_runtime_ms,
    "avg_runtime_ms": (
        sum(r["runtime_ms"] for r in results) // len(results)
        if results else 0
    )
}

with open("runs/summary.json", "w") as f:
    json.dump(summary, f, indent=2)

print("\nCreating final summary")
print(json.dumps(summary, indent=2))
print("Done. Wrote runs/summary.json")
