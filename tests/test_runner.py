#The runner needs to 
# 1. always return a RunResult for the orchestrator, 
# 2. never raise an exception, 
# 3. preserve evidence of any failings (input.html and meta.json) inside findings_dir/<testname>
# 4. run_dir is cleaned and doesn't exist
# 5. elapsed_ms is non negative
# The job of the runner is only status flags
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest


class FakePage:
    def __init__(self, *, goto_raises=None, crash_during_goto=False, crash_during_wait=False):
        self._handlers = {}
        self._goto_raises = goto_raises
        self._crash_during_goto = crash_during_goto
        self._crash_during_wait = crash_during_wait

    def on(self, event, cb):
        self._handlers.setdefault(event, []).append(cb)

    def _fire(self, event):
        for cb in self._handlers.get(event, []):
            cb()

    async def evaluate(self, js):  
        pass

    async def goto(self, url, wait_until, timeout):
        if self._crash_during_goto:
            self._fire("crash")
        if self._goto_raises is not None:
            raise self._goto_raises

    async def wait_for_timeout(self, ms):
        if self._crash_during_wait:
            self._fire("crash")


class FakeContext:
    def __init__(self, page):
        self._page = page

    async def new_page(self):
        return self._page

    async def close(self):
        pass


class FakeChromium:
    def __init__(self, ctx):
        self._ctx = ctx

    async def launch_persistent_context(self, user_data_dir, headless, args):
        return self._ctx


class FakePlaywright:
    def __init__(self, chromium):
        self.chromium = chromium


class FakeAsyncPlaywrightCM:
    def __init__(self, p):
        self._p = p

    async def __aenter__(self):
        return self._p

    async def __aexit__(self, *_):
        return False


class FakeLocalFileServer:
    def __init__(self, root):
        self.root = root
        self.port = 12345

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _write_html(path):
    path.write_text("<!DOCTYPE html><html><body>hi</body></html>", encoding="utf-8")


def _read_meta(run_dir):
    return json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))


def _patch(monkeypatch, runner, page):
    p = FakePlaywright(FakeChromium(FakeContext(page)))
    monkeypatch.setattr(runner, "LocalFileServer", FakeLocalFileServer)
    monkeypatch.setattr(runner, "async_playwright", lambda: FakeAsyncPlaywrightCM(p))


@pytest.mark.asyncio
async def test_ok_returns_run_result(tmp_path, monkeypatch):
    import fuzion.run as runner
    html = tmp_path / "case_000001.html"
    _write_html(html)
    _patch(monkeypatch, runner, FakePage())

    res = await runner.run_one(html_path=html, findings_dir=tmp_path / "findings", nav_timeout_s=1, hard_timeout_s=1)

    assert res.status == "ok"
    assert res.elapsed_ms >= 0


@pytest.mark.asyncio
async def test_ok_cleans_up_run_dir(tmp_path, monkeypatch):
    import fuzion.run as runner
    html = tmp_path / "case_000001.html"
    _write_html(html)
    findings_dir = tmp_path / "findings"
    _patch(monkeypatch, runner, FakePage())

    await runner.run_one(html_path=html, findings_dir=findings_dir, nav_timeout_s=1, hard_timeout_s=1)

    assert not (findings_dir / html.stem).exists()


@pytest.mark.asyncio
async def test_hang_returns_run_result(tmp_path, monkeypatch):
    import fuzion.run as runner
    html = tmp_path / "case_000002.html"
    _write_html(html)
    _patch(monkeypatch, runner, FakePage())

    async def fake_wait_for(coro, timeout):
        coro.close()
        raise asyncio.TimeoutError()

    monkeypatch.setattr(runner.asyncio, "wait_for", fake_wait_for)

    res = await runner.run_one(html_path=html, findings_dir=tmp_path / "findings", nav_timeout_s=1, hard_timeout_s=1)

    assert res.status == "hang"
    assert res.elapsed_ms >= 0


@pytest.mark.asyncio
async def test_hang_preserves_evidence(tmp_path, monkeypatch):
    import fuzion.run as runner
    html = tmp_path / "case_000002.html"
    _write_html(html)
    findings_dir = tmp_path / "findings"
    _patch(monkeypatch, runner, FakePage())

    async def fake_wait_for(coro, timeout):
        coro.close()
        raise asyncio.TimeoutError()

    monkeypatch.setattr(runner.asyncio, "wait_for", fake_wait_for)

    await runner.run_one(html_path=html, findings_dir=findings_dir, nav_timeout_s=1, hard_timeout_s=1)

    run_dir = findings_dir / html.stem
    assert run_dir.exists()
    assert (run_dir / "input.html").exists()
    assert _read_meta(run_dir)["result"] == "hang"


@pytest.mark.asyncio
async def test_crash_during_nav_returns_run_result(tmp_path, monkeypatch):
    import fuzion.run as runner
    html = tmp_path / "case_000003.html"
    _write_html(html)
    _patch(monkeypatch, runner, FakePage(goto_raises=RuntimeError("boom"), crash_during_goto=True))

    res = await runner.run_one(html_path=html, findings_dir=tmp_path / "findings", nav_timeout_s=1, hard_timeout_s=1)

    assert res.status == "crash"
    assert res.elapsed_ms >= 0


@pytest.mark.asyncio
async def test_crash_during_nav_preserves_evidence(tmp_path, monkeypatch):
    import fuzion.run as runner
    html = tmp_path / "case_000003.html"
    _write_html(html)
    findings_dir = tmp_path / "findings"
    _patch(monkeypatch, runner, FakePage(goto_raises=RuntimeError("boom"), crash_during_goto=True))

    await runner.run_one(html_path=html, findings_dir=findings_dir, nav_timeout_s=1, hard_timeout_s=1)

    run_dir = findings_dir / html.stem
    assert run_dir.exists()
    assert (run_dir / "input.html").exists()
    assert _read_meta(run_dir)["result"] == "crash"


@pytest.mark.asyncio
async def test_crash_after_nav_returns_run_result(tmp_path, monkeypatch):
    import fuzion.run as runner
    html = tmp_path / "case_000004.html"
    _write_html(html)
    _patch(monkeypatch, runner, FakePage(crash_during_wait=True))

    res = await runner.run_one(html_path=html, findings_dir=tmp_path / "findings", nav_timeout_s=1, hard_timeout_s=1)

    assert res.status == "crash"
    assert res.elapsed_ms >= 0


@pytest.mark.asyncio
async def test_crash_after_nav_preserves_evidence(tmp_path, monkeypatch):
    import fuzion.run as runner
    html = tmp_path / "case_000004.html"
    _write_html(html)
    findings_dir = tmp_path / "findings"
    _patch(monkeypatch, runner, FakePage(crash_during_wait=True))

    await runner.run_one(html_path=html, findings_dir=findings_dir, nav_timeout_s=1, hard_timeout_s=1)

    run_dir = findings_dir / html.stem
    assert run_dir.exists()
    assert (run_dir / "input.html").exists()
    assert _read_meta(run_dir)["result"] == "crash"


@pytest.mark.asyncio
async def test_timeout_returns_run_result(tmp_path, monkeypatch):
    import fuzion.run as runner
    html = tmp_path / "case_000005.html"
    _write_html(html)
    _patch(monkeypatch, runner, FakePage(goto_raises=RuntimeError("Timeout 30000ms exceeded")))

    res = await runner.run_one(html_path=html, findings_dir=tmp_path / "findings", nav_timeout_s=1, hard_timeout_s=1)

    assert res.status == "timeout"
    assert res.elapsed_ms >= 0


@pytest.mark.asyncio
async def test_timeout_preserves_evidence(tmp_path, monkeypatch):
    import fuzion.run as runner
    html = tmp_path / "case_000005.html"
    _write_html(html)
    findings_dir = tmp_path / "findings"
    _patch(monkeypatch, runner, FakePage(goto_raises=RuntimeError("Timeout 30000ms exceeded")))

    await runner.run_one(html_path=html, findings_dir=findings_dir, nav_timeout_s=1, hard_timeout_s=1)

    run_dir = findings_dir / html.stem
    assert run_dir.exists()
    assert (run_dir / "input.html").exists()
    assert _read_meta(run_dir)["result"] == "timeout"


@pytest.mark.asyncio
async def test_error_returns_run_result(tmp_path, monkeypatch):
    import fuzion.run as runner
    html = tmp_path / "case_000006.html"
    _write_html(html)
    _patch(monkeypatch, runner, FakePage(goto_raises=ValueError("unexpected")))

    res = await runner.run_one(html_path=html, findings_dir=tmp_path / "findings", nav_timeout_s=1, hard_timeout_s=1)

    assert res.status == "error"
    assert res.elapsed_ms >= 0


@pytest.mark.asyncio
async def test_error_preserves_evidence(tmp_path, monkeypatch):
    import fuzion.run as runner
    html = tmp_path / "case_000006.html"
    _write_html(html)
    findings_dir = tmp_path / "findings"
    _patch(monkeypatch, runner, FakePage(goto_raises=ValueError("unexpected")))

    await runner.run_one(html_path=html, findings_dir=findings_dir, nav_timeout_s=1, hard_timeout_s=1)

    run_dir = findings_dir / html.stem
    assert run_dir.exists()
    assert (run_dir / "input.html").exists()
    assert _read_meta(run_dir)["result"] == "error"


@pytest.mark.asyncio
async def test_never_raises(tmp_path, monkeypatch):
    import fuzion.run as runner
    html = tmp_path / "case_000007.html"
    _write_html(html)

    def bad_server(root):
        raise RuntimeError("server exploded")

    monkeypatch.setattr(runner, "LocalFileServer", bad_server)
    monkeypatch.setattr(runner, "async_playwright", lambda: FakeAsyncPlaywrightCM(FakePlaywright(FakeChromium(FakeContext(FakePage())))))

    res = await runner.run_one(html_path=html, findings_dir=tmp_path / "findings", nav_timeout_s=1, hard_timeout_s=1)

    assert isinstance(res, runner.RunResult)
    assert res.elapsed_ms >= 0