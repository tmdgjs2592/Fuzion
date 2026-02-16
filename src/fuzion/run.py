import asyncio
import socket
from dataclasses import dataclass
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from threading import Thread
from typing import Optional

from playwright.async_api import async_playwright

from .util import ensure_dir, write_json, safe_rmtree, copytree_if_exists, now_ms

@dataclass
class RunResult:
    status: str  # "ok" | "crash" | "hang" | "timeout" | "error"
    detail: str
    elapsed_ms: int

class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):  # silence server logs
        return

def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

class LocalFileServer:
    def __init__(self, root: Path):
        self.root = root
        self.port = _free_port()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", self.port), _QuietHandler)
        self.thread = Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self._old = Path.cwd()
        # SimpleHTTPRequestHandler serves from cwd
        import os
        os.chdir(self.root)
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.httpd.shutdown()
        self.httpd.server_close()
        import os
        os.chdir(self._old)

async def run_one(
    *,
    html_path: Path,
    findings_dir: Path,
    nav_timeout_s: int,
    hard_timeout_s: int,
) -> RunResult:
    start = now_ms()
    ensure_dir(findings_dir)

    testcase_id = html_path.stem
    run_dir = findings_dir / testcase_id
    safe_rmtree(run_dir)
    ensure_dir(run_dir)

    # Copy input always (even OK runs can be optionally kept; here we keep only if abnormal)
    input_copy = run_dir / "input.html"
    input_copy.write_bytes(html_path.read_bytes())

    user_data_dir = run_dir / "user-data-dir"
    ensure_dir(user_data_dir)

    meta = {
        "testcase": str(html_path),
        "started_ms": start,
        "nav_timeout_s": nav_timeout_s,
        "hard_timeout_s": hard_timeout_s,
    }

    try:
        with LocalFileServer(root=html_path.parent) as srv:
            url = f"http://127.0.0.1:{srv.port}/{html_path.name}"
            meta["url"] = url

            async with async_playwright() as p:
                # Launch Chromium headless.
                # Chrome’s headless mode is documented by Chromium team. :contentReference[oaicite:7]{index=7}
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-first-run",
                        "--disable-background-networking",
                        "--disable-default-apps",
                        "--disable-extensions",
                        "--disable-sync",
                        "--metrics-recording-only",
                        "--no-default-browser-check",
                        "--disable-dev-shm-usage",
                        "--disable-popup-blocking",
                        "--disable-renderer-backgrounding",
                        "--disable-background-timer-throttling",
                        "--disable-client-side-phishing-detection",
                        "--disable-features=Translate,BackForwardCache",
                        "--mute-audio",
                        f"--user-data-dir={str(user_data_dir)}",
                    ],
                )
                context = await browser.new_context()
                page = await context.new_page()

                crashed = {"flag": False, "msg": ""}

                def on_crash():
                    crashed["flag"] = True
                    crashed["msg"] = "page crash event"

                page.on("crash", lambda: on_crash())

                # Enforce hard timeout around the whole navigation/render window
                async def do_nav():
                    await page.goto(url, wait_until="load", timeout=nav_timeout_s * 1000)
                    # Give it a tiny post-load window to trigger weird behavior
                    await page.wait_for_timeout(250)

                try:
                    await asyncio.wait_for(do_nav(), timeout=hard_timeout_s)
                except asyncio.TimeoutError:
                    # HANG -> hard timeout
                    meta["result"] = "hang"
                    write_json(run_dir / "meta.json", meta)
                    await context.close()
                    await browser.close()
                    return RunResult("hang", f"hard timeout > {hard_timeout_s}s", now_ms() - start)
                except Exception as e:
                    # navigation timeout or other playwright errors
                    detail = repr(e)
                    # If page crashed, classify as crash
                    if crashed["flag"]:
                        meta["result"] = "crash"
                        meta["detail"] = crashed["msg"]
                        write_json(run_dir / "meta.json", meta)
                        await context.close()
                        await browser.close()
                        return RunResult("crash", crashed["msg"], now_ms() - start)

                    # Heuristic: Playwright "Timeout" indicates nav timeout
                    if "Timeout" in detail or "timeout" in detail.lower():
                        meta["result"] = "timeout"
                        meta["detail"] = detail
                        write_json(run_dir / "meta.json", meta)
                        await context.close()
                        await browser.close()
                        return RunResult("timeout", detail, now_ms() - start)

                    meta["result"] = "error"
                    meta["detail"] = detail
                    write_json(run_dir / "meta.json", meta)
                    await context.close()
                    await browser.close()
                    return RunResult("error", detail, now_ms() - start)

                # After navigation, if the page crash event fired, treat as crash
                if crashed["flag"]:
                    meta["result"] = "crash"
                    meta["detail"] = crashed["msg"]
                    write_json(run_dir / "meta.json", meta)
                    await context.close()
                    await browser.close()
                    return RunResult("crash", crashed["msg"], now_ms() - start)

                # OK: delete run_dir to keep disk usage minimal (only keep abnormal)
                await context.close()
                await browser.close()
                safe_rmtree(run_dir)
                return RunResult("ok", "loaded", now_ms() - start)

    except Exception as e:
        meta["result"] = "error"
        meta["detail"] = repr(e)
        write_json(run_dir / "meta.json", meta)
        return RunResult("error", repr(e), now_ms() - start)

