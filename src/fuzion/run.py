import asyncio
import logging
import socket
import shutil
from dataclasses import dataclass
from functools import partial
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from threading import Thread
from typing import Any

from playwright.async_api import async_playwright

from .util import ensure_dir, write_json, safe_rmtree, now_ms

logger = logging.getLogger(__name__)


@dataclass
class RunResult:
    status: str  # "ok" | "crash" | "hang" | "timeout" | "error"
    detail: str
    elapsed_ms: int

class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):  # silence server logs
        return


def _serialize_page_error(err: Any) -> dict[str, str]:
    item: dict[str, str] = {"text": str(err)}
    for field in ("name", "message", "stack"):
        value = getattr(err, field, None)
        if value is not None:
            item[field] = str(value)
    return item


def _primary_js_error_detail(js_errors: list[dict[str, str]]) -> str:
    if not js_errors:
        return "javascript error"
    first = js_errors[0]
    return first.get("stack") or first.get("message") or first.get("text", "javascript error")


def _attach_js_errors(meta: dict, js_errors: list[dict[str, str]]) -> None:
    if js_errors:
        meta["js_errors"] = js_errors


def _attach_native_log_meta(meta: dict, native_log_path: Path) -> None:
    meta["native_log_path"] = str(native_log_path)
    meta["native_log_exists"] = native_log_path.exists()


def _attach_dump_meta(meta: dict, dumps_dir: Path) -> None:
    dump_files = sorted(str(p) for p in dumps_dir.rglob("*.dmp") if p.is_file())
    meta["dump_dir"] = str(dumps_dir)
    meta["dump_files"] = dump_files
    meta["dump_count"] = len(dump_files)


def _materialize_native_log(*, preferred_path: Path, user_data_dir: Path) -> Path:
    """
    Chromium may ignore --log-file and still write to a profile-local chrome_debug.log.
    Normalize this by copying the discovered file to preferred_path when needed.
    """
    candidates = [
        preferred_path,
        user_data_dir / "Default" / "chrome_debug.log",
        user_data_dir / "chrome_debug.log",
    ]
    discovered = next((p for p in candidates if p.exists() and p.is_file()), None)
    if discovered is None:
        return preferred_path

    if discovered != preferred_path:
        try:
            shutil.copyfile(discovered, preferred_path)
            return preferred_path
        except Exception:
            return discovered

    return preferred_path


def _finalize_failure_artifacts(
    *,
    meta: dict,
    native_log_path: Path,
    user_data_dir: Path,
    dumps_dir: Path,
) -> None:
    native_log_path = _materialize_native_log(
        preferred_path=native_log_path,
        user_data_dir=user_data_dir,
    )
    _attach_native_log_meta(meta, native_log_path)
    _attach_dump_meta(meta, dumps_dir)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        port = s.getsockname()[1]
    logger.debug("Allocated free port: %d", port)
    return port

class LocalFileServer:
    def __init__(self, root: Path):
        self.root = root
        self.port = _free_port()
        # IMPORTANT: instead of chdir, we pin directory to self.root. removes global state
        handler = partial(_QuietHandler, directory=str(self.root)) # handler factory, directory prefilled to self.root
        self.httpd = ThreadingHTTPServer(("127.0.0.1", self.port), handler)
        self.thread = Thread(target=self.httpd.serve_forever, daemon=True)
        logger.debug("LocalFileServer initialised: root=%s, port=%d", self.root, self.port)

    def __enter__(self):
        self.thread.start()
        logger.debug("LocalFileServer started: serving %s on port %d", self.root, self.port)
        return self

    def __exit__(self, exc_type, exc, tb):
        self.httpd.shutdown()
        self.httpd.server_close()
        logger.debug("LocalFileServer stopped: port %d released", self.port)

async def run_one(
    *,
    html_path: Path,
    findings_dir: Path,
    nav_timeout_s: int,
    hard_timeout_s: int,
    headed: bool = False,
    browser_channel: str | None = None,
    browser_executable_path: Path | None = None,
) -> RunResult:
    start = now_ms()
    logger.debug(
        "run_one called: html_path=%s, findings_dir=%s, nav_timeout_s=%d, hard_timeout_s=%d",
        html_path, findings_dir, nav_timeout_s, hard_timeout_s,
    )
    ensure_dir(findings_dir)

    testcase_id = html_path.stem
    run_dir = findings_dir / testcase_id
    safe_rmtree(run_dir)
    ensure_dir(run_dir)
    logger.debug("Run directory prepared: %s", run_dir)

    # Copy input always (even OK runs can be optionally kept; here we keep only if abnormal)
    input_copy = run_dir / "input.html"
    input_copy.write_bytes(html_path.read_bytes())
    logger.debug("Input HTML copied to %s (%d bytes)", input_copy, html_path.stat().st_size)

    user_data_dir = run_dir / "user-data-dir"
    ensure_dir(user_data_dir)
    logger.debug("User data dir prepared: %s", user_data_dir)
    native_log_path = run_dir / "chrome.log"
    logger.debug("Native chromium log path: %s", native_log_path)
    dumps_dir = run_dir / "dumps"
    ensure_dir(dumps_dir)
    logger.debug("Native crash dump dir prepared: %s", dumps_dir)

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
            logger.debug("Serving testcase at URL: %s", url)

            async with async_playwright() as p:
                # Launch Chromium (headless by default unless headed=True).
                logger.debug("Launching Chromium persistent context: user_data_dir=%s", user_data_dir)
                launch_kwargs: dict[str, Any] = {
                    "user_data_dir": user_data_dir,
                    "headless": not headed,
                    "ignore_default_args": ["--disable-breakpad"],
                    "args": [
                        "--no-first-run",
                        "--enable-logging",
                        "--v=1",
                        f"--log-file={native_log_path.resolve()}",
                        "--enable-crash-reporter",
                        f"--crash-dumps-dir={dumps_dir.resolve()}",
                        "--disable-background-networking",
                        "--disable-default-apps",
                        "--disable-extensions",
                        "--disable-sync",
                        "--metrics-recording-only",
                        "--no-default-browser-check",
                        "--disable-dev-shm-usage",
                        "--disable-popup-blocking",
                        "--disable-client-side-phishing-detection",
                        "--disable-features=Translate,BackForwardCache",
                        "--mute-audio",
                    ],
                }
                if browser_channel:
                    launch_kwargs["channel"] = browser_channel
                if browser_executable_path is not None:
                    launch_kwargs["executable_path"] = str(browser_executable_path)

                context = await p.chromium.launch_persistent_context(**launch_kwargs)
                logger.debug("Chromium context launched successfully")
                page = await context.new_page()
                logger.debug("New page opened")

                crashed = {"flag": False, "msg": ""}
                js_errors: list[dict[str, str]] = []

                def on_crash():
                    logger.debug("Page crash event received for testcase %s", testcase_id)
                    crashed["flag"] = True
                    crashed["msg"] = "page crash event"

                def on_pageerror(err):
                    logger.debug("JS error for testcase %s: %s", testcase_id, err)
                    js_errors.append(_serialize_page_error(err))

                page.on("crash", lambda: on_crash())
                page.on("pageerror", on_pageerror)

                # Enforce hard timeout around the whole navigation/render window
                async def do_nav():
                    logger.debug("Navigating to %s (nav_timeout_s=%d)", url, nav_timeout_s)
                    await page.goto(url, wait_until="load", timeout=nav_timeout_s * 1000)
                    logger.debug("Navigation complete, starting stress phase for testcase %s", testcase_id)

                    # dispatch common events that trigger handlers in fuzzed HTML
                    await page.evaluate("""() => {
                        window.dispatchEvent(new Event('resize'));
                        window.dispatchEvent(new Event('scroll'));
                        document.dispatchEvent(new Event('DOMContentLoaded'));
                    }""")

                    # pump the real event loop with setTimeout-based ticks
                    # rAF is unreliable in headless — use setTimeout chain instead
                    await page.evaluate("""() => new Promise(resolve => {
                        let ticks = 0;
                        function tick() {
                            if (++ticks >= 50) return resolve();
                            // force style recalc and layout on each tick
                            document.body && document.body.getBoundingClientRect();
                            setTimeout(tick, 20);
                        }
                        setTimeout(tick, 20);
                    })""")

                    # trigger GC if available to surface use-after-free bugs
                    await page.evaluate("""() => {
                        if (typeof window.gc === 'function') window.gc();
                    }""")

                    # final buffer
                    await page.wait_for_timeout(500)
                    logger.debug("Stress phase complete for testcase %s", testcase_id)

                try:
                    await asyncio.wait_for(do_nav(), timeout=hard_timeout_s)
                except asyncio.TimeoutError:
                    # HANG -> hard timeout
                    logger.debug("Hard timeout exceeded (%ds) for testcase %s — classifying as hang", hard_timeout_s, testcase_id)
                    meta["result"] = "hang"
                    _attach_js_errors(meta, js_errors)
                    await context.close()
                    _finalize_failure_artifacts(
                        meta=meta,
                        native_log_path=native_log_path,
                        user_data_dir=user_data_dir,
                        dumps_dir=dumps_dir,
                    )
                    write_json(run_dir / "meta.json", meta)
                    elapsed = now_ms() - start
                    logger.debug("run_one returning: status=hang, elapsed_ms=%d, testcase=%s", elapsed, testcase_id)
                    return RunResult("hang", f"hard timeout > {hard_timeout_s}s", elapsed)
                except Exception as e:
                    # navigation timeout or other playwright errors
                    detail = repr(e)
                    logger.debug("Exception during navigation for testcase %s: %s", testcase_id, detail)
                    # If page crashed, classify as crash
                    if crashed["flag"]:
                        logger.debug("Crash flag set for testcase %s — classifying as crash", testcase_id)
                        meta["result"] = "crash"
                        meta["detail"] = crashed["msg"]
                        _attach_js_errors(meta, js_errors)
                        await context.close()
                        _finalize_failure_artifacts(
                            meta=meta,
                            native_log_path=native_log_path,
                            user_data_dir=user_data_dir,
                            dumps_dir=dumps_dir,
                        )
                        write_json(run_dir / "meta.json", meta)
                        elapsed = now_ms() - start
                        logger.debug("run_one returning: status=crash, elapsed_ms=%d, testcase=%s", elapsed, testcase_id)
                        return RunResult("crash", crashed["msg"], elapsed)
                    if js_errors:
                        logger.debug("JS errors detected for testcase %s — classifying as error", testcase_id)
                        js_detail = _primary_js_error_detail(js_errors)
                        meta["result"] = "error"
                        meta["detail"] = js_detail
                        _attach_js_errors(meta, js_errors)
                        await context.close()
                        _finalize_failure_artifacts(
                            meta=meta,
                            native_log_path=native_log_path,
                            user_data_dir=user_data_dir,
                            dumps_dir=dumps_dir,
                        )
                        write_json(run_dir / "meta.json", meta)
                        elapsed = now_ms() - start
                        return RunResult("error", js_detail, elapsed)

                    # Heuristic: Playwright "Timeout" indicates nav timeout
                    if "Timeout" in detail or "timeout" in detail.lower():
                        logger.debug("Timeout keyword detected in exception for testcase %s — classifying as timeout", testcase_id)
                        meta["result"] = "timeout"
                        meta["detail"] = detail
                        _attach_js_errors(meta, js_errors)
                        await context.close()
                        _finalize_failure_artifacts(
                            meta=meta,
                            native_log_path=native_log_path,
                            user_data_dir=user_data_dir,
                            dumps_dir=dumps_dir,
                        )
                        write_json(run_dir / "meta.json", meta)
                        elapsed = now_ms() - start
                        logger.debug("run_one returning: status=timeout, elapsed_ms=%d, testcase=%s", elapsed, testcase_id)
                        return RunResult("timeout", detail, elapsed)

                    logger.debug("Unclassified exception for testcase %s — classifying as error", testcase_id)
                    meta["result"] = "error"
                    meta["detail"] = detail
                    _attach_js_errors(meta, js_errors)
                    await context.close()
                    _finalize_failure_artifacts(
                        meta=meta,
                        native_log_path=native_log_path,
                        user_data_dir=user_data_dir,
                        dumps_dir=dumps_dir,
                    )
                    write_json(run_dir / "meta.json", meta)
                    elapsed = now_ms() - start
                    logger.debug("run_one returning: status=error, elapsed_ms=%d, testcase=%s", elapsed, testcase_id)
                    return RunResult("error", detail, elapsed)

                # After navigation, if the page crash event fired, treat as crash
                if crashed["flag"]:
                    logger.debug("Post-navigation crash flag set for testcase %s — classifying as crash", testcase_id)
                    meta["result"] = "crash"
                    meta["detail"] = crashed["msg"]
                    _attach_js_errors(meta, js_errors)
                    await context.close()
                    _finalize_failure_artifacts(
                        meta=meta,
                        native_log_path=native_log_path,
                        user_data_dir=user_data_dir,
                        dumps_dir=dumps_dir,
                    )
                    write_json(run_dir / "meta.json", meta)
                    elapsed = now_ms() - start
                    logger.debug("run_one returning: status=crash, elapsed_ms=%d, testcase=%s", elapsed, testcase_id)
                    return RunResult("crash", crashed["msg"], elapsed)

                # OK: delete run_dir to keep disk usage minimal (only keep abnormal)
                logger.debug("Testcase %s loaded successfully — classifying as ok, removing run_dir %s", testcase_id, run_dir)
                await context.close()
                safe_rmtree(run_dir)
                elapsed = now_ms() - start
                logger.debug("run_one returning: status=ok, elapsed_ms=%d, testcase=%s", elapsed, testcase_id)
                return RunResult("ok", "loaded", elapsed)

    except Exception as e:
        logger.debug("Outer exception for testcase %s: %s — classifying as error", testcase_id, repr(e))
        meta["result"] = "error"
        meta["detail"] = repr(e)
        _finalize_failure_artifacts(
            meta=meta,
            native_log_path=native_log_path,
            user_data_dir=user_data_dir,
            dumps_dir=dumps_dir,
        )
        write_json(run_dir / "meta.json", meta)
        elapsed = now_ms() - start
        logger.debug("run_one returning: status=error, elapsed_ms=%d, testcase=%s", elapsed, testcase_id)
        return RunResult("error", repr(e), elapsed)
