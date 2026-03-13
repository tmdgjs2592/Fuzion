"""
Targeted native-surface testcase generator for Fuzion.

This generator is intentionally different from the baseline grammar generator:
it biases toward browser subsystems that repeatedly appear in public Chrome
security bulletins (V8, CSS/style engine, media/WebCodecs, storage, GPU/compositor,
WebRTC).

Important: this increases pressure on native code paths, but cannot guarantee
native crashes or dump generation.
"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .util import ensure_dir

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Fragment:
    body: str
    script: str


@dataclass(frozen=True)
class _Template:
    name: str
    weight: int
    build: Callable[[random.Random, int], _Fragment]


def _js_bytes(rng: random.Random, n: int) -> str:
    return ",".join(str(rng.randrange(0, 256)) for _ in range(n))


def _case_wrapper(
    *,
    template_names: list[str],
    body_chunks: list[str],
    script_chunks: list[str],
    budget_ms: int,
) -> str:
    body = "\n".join(body_chunks)
    script = "\n".join(script_chunks)
    names = ", ".join(template_names)
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Fuzion Native Stress ({names})</title>
  <style>
    html, body {{ margin: 0; padding: 0; }}
    body {{ font-family: monospace; line-height: 1.2; }}
    #root {{ display: grid; grid-template-columns: repeat(8, 1fr); gap: 2px; }}
    .cell {{ width: 100%; aspect-ratio: 1 / 1; contain: layout style paint; }}
  </style>
</head>
<body>
  <div id="root"></div>
  {body}
  <script>
  "use strict";
  const fuzionStart = performance.now();
  const fuzionDeadline = fuzionStart + {budget_ms};
  const fuzionYield = () => new Promise((resolve) => setTimeout(resolve, 0));
  window.addEventListener("error", () => {{}});
  window.addEventListener("unhandledrejection", () => {{}});
  {script}
  </script>
</body>
</html>
"""


def _build_v8_pressure(rng: random.Random, case_index: int) -> _Fragment:
    workers = rng.randint(2, 6)
    rounds = rng.randint(200, 600)
    width = rng.choice([128, 256, 512])
    return _Fragment(
        body=f'<div id="v8-{case_index}"></div>',
        script=f"""
void async function v8Pressure() {{
  const workerSource = `
    self.onmessage = (ev) => {{
      let sink = [];
      for (let r = 0; r < {rounds}; r++) {{
        const arr = new Array({width});
        for (let i = 0; i < arr.length; i++) {{
          const obj = {{a: i, b: i + r, c: i ^ r}};
          if ((i + r) % 3 === 0) obj["k" + i] = i * r;
          if ((i + r) % 7 === 0) delete obj.b;
          if ((i + r) % 11 === 0) Object.setPrototypeOf(obj, {{p: r}});
          arr[i] = obj;
        }}
        arr.sort((x, y) => (x.a & 7) - (y.a & 7));
        sink.push(arr);
        if (sink.length > 24) sink.splice(0, 8);
      }}
      postMessage(ev.data);
    }};
  `;
  const workerURL = URL.createObjectURL(new Blob([workerSource], {{ type: "text/javascript" }}));
  const ws = [];
  for (let i = 0; i < {workers}; i++) {{
    const w = new Worker(workerURL);
    w.postMessage(i);
    ws.push(w);
  }}

  let roundsDone = 0;
  const sink = [];
  while (performance.now() < fuzionDeadline) {{
    const arr = new Array({width} * 2);
    for (let i = 0; i < arr.length; i++) {{
      const obj = {{x: i, y: i + roundsDone, z: i * 3}};
      if ((i + roundsDone) % 2 === 0) obj.extra = "v" + i;
      if ((i + roundsDone) % 5 === 0) obj.buf = new Uint8Array(64);
      if ((i + roundsDone) % 9 === 0) delete obj.y;
      arr[i] = obj;
    }}
    arr.sort((a, b) => (a.x & 3) - (b.x & 3));

    const ta = new BigInt64Array(512);
    for (let i = 0; i < ta.length; i++) ta[i] = BigInt((i + 1) * (roundsDone + 3));
    sink.push(arr, ta);
    if (sink.length > 80) sink.splice(0, 12);

    roundsDone++;
    if ((roundsDone & 3) === 0) await fuzionYield();
  }}

  for (const w of ws) w.terminate();
  URL.revokeObjectURL(workerURL);
}}();
""",
    )


def _build_css_pressure(rng: random.Random, case_index: int) -> _Fragment:
    hosts = rng.randint(8, 20)
    sheets = rng.randint(4, 12)
    per_host = rng.randint(24, 72)
    return _Fragment(
        body=f'<div id="css-hosts-{case_index}"></div>',
        script=f"""
void async function cssPressure() {{
  const root = document.getElementById("css-hosts-{case_index}") || document.body;
  const hosts = [];
  const sheets = [];

  for (let i = 0; i < {sheets}; i++) {{
    if (!("CSSStyleSheet" in window)) break;
    const sheet = new CSSStyleSheet();
    sheet.replaceSync(`
      .node-${{i}} {{ transform: translate3d(${{i}}px, 0, 0) scale(${{1 + (i % 5) / 10}}); }}
      .flip-${{i}} {{ filter: blur(${{(i % 3)}}px) contrast(${{1 + (i % 7) / 3}}); }}
      @keyframes spin-${{i}} {{ from {{ rotate: 0deg; }} to {{ rotate: 360deg; }} }}
    `);
    sheets.push(sheet);
  }}

  for (let i = 0; i < {hosts}; i++) {{
    const host = document.createElement("section");
    host.className = "cell";
    root.appendChild(host);
    const sr = host.attachShadow({{ mode: "open" }});
    sr.innerHTML = "<div class='container'></div>";
    hosts.push(host);
  }}

  let round = 0;
  while (performance.now() < fuzionDeadline) {{
    for (let i = 0; i < hosts.length; i++) {{
      const host = hosts[i];
      const sr = host.shadowRoot;
      if (!sr) continue;
      if (sheets.length && "adoptedStyleSheets" in sr) {{
        sr.adoptedStyleSheets = [sheets[(round + i) % sheets.length]];
      }}

      const n = document.createElement("div");
      n.className = `node-${{(round + i) % {sheets + 1}}} flip-${{(round * 3 + i) % {sheets + 1}}}`;
      n.textContent = String(round) + ":" + String(i);
      sr.appendChild(n);

      while (sr.childNodes.length > {per_host}) {{
        sr.removeChild(sr.firstChild);
      }}

      host.style.contain = (round % 2) ? "layout style paint" : "strict";
      host.getBoundingClientRect();
    }}
    round++;
    await new Promise(requestAnimationFrame);
  }}
}}();
""",
    )


def _build_storage_pressure(rng: random.Random, case_index: int) -> _Fragment:
    value_size = rng.randint(512, 4096)
    db_slots = rng.randint(2, 5)
    rows = rng.randint(40, 140)
    return _Fragment(
        body=f'<div id="storage-{case_index}"></div>',
        script=f"""
void async function storagePressure() {{
  const value = "X".repeat({value_size});
  const dbPrefix = "fzdb_{case_index}_";

  function idbOpen(name, version) {{
    return new Promise((resolve, reject) => {{
      const req = indexedDB.open(name, version);
      req.onupgradeneeded = () => {{
        const db = req.result;
        if (!db.objectStoreNames.contains("os")) {{
          db.createObjectStore("os", {{ keyPath: "id" }});
        }}
      }};
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    }});
  }}

  async function idbRound(name, version) {{
    let db;
    try {{
      db = await idbOpen(name, version);
      await new Promise((resolve) => {{
        const tx = db.transaction("os", "readwrite");
        const os = tx.objectStore("os");
        for (let i = 0; i < {rows}; i++) {{
          os.put({{ id: i, data: value + String(version) + ":" + String(i) }});
        }}
        tx.oncomplete = () => resolve(undefined);
        tx.onerror = () => resolve(undefined);
        tx.onabort = () => resolve(undefined);
      }});
    }} catch (_) {{
    }} finally {{
      if (db) db.close();
    }}
  }}

  let round = 1;
  while (performance.now() < fuzionDeadline) {{
    try {{
      localStorage.setItem("fz_ls_" + round, value);
      if (round % 3 === 0) localStorage.removeItem("fz_ls_" + (round - 1));
      if (round % 11 === 0) localStorage.clear();
    }} catch (_) {{
    }}

    if ("indexedDB" in window) {{
      const dbName = dbPrefix + String(round % {db_slots});
      try {{ indexedDB.deleteDatabase(dbName); }} catch (_) {{}}
      await idbRound(dbName, round + 1);
    }}

    round++;
    await fuzionYield();
  }}
}}();
""",
    )


def _build_webcodecs_media_pressure(rng: random.Random, case_index: int) -> _Fragment:
    chunk_len = rng.randint(128, 1024)
    data = _js_bytes(rng, chunk_len)
    cycle = rng.randint(6, 16)
    return _Fragment(
        body=f"""
<video id="video-{case_index}" muted playsinline style="width:320px;height:180px;background:#000"></video>
<canvas id="canvas-{case_index}" width="320" height="180"></canvas>
""",
        script=f"""
void async function mediaPressure() {{
  const bytes = new Uint8Array([{data}]);
  const video = document.getElementById("video-{case_index}");
  const canvas = document.getElementById("canvas-{case_index}");
  const ctx = canvas ? canvas.getContext("2d") : null;

  if ("VideoDecoder" in window) {{
    let decoded = 0;
    const decoder = new VideoDecoder({{
      output(frame) {{
        try {{
          if (ctx) {{
            ctx.drawImage(frame, 0, 0, canvas.width, canvas.height);
            ctx.getImageData(0, 0, 1, 1);
          }}
        }} catch (_) {{
        }} finally {{
          frame.close();
          decoded++;
        }}
      }},
      error() {{}},
    }});

    const configs = [
      {{ codec: "vp8", codedWidth: 64, codedHeight: 64 }},
      {{ codec: "vp09.00.10.08", codedWidth: 64, codedHeight: 64 }},
      {{ codec: "avc1.42E01E", codedWidth: 64, codedHeight: 64 }},
    ];

    let ts = 0;
    let iter = 0;
    while (performance.now() < fuzionDeadline) {{
      const cfg = configs[iter % configs.length];
      try {{ decoder.configure(cfg); }} catch (_) {{}}
      try {{
        decoder.decode(new EncodedVideoChunk({{
          type: (iter % 5) ? "delta" : "key",
          timestamp: ts,
          data: bytes,
        }}));
      }} catch (_) {{}}
      ts += 33333;
      iter++;
      if (iter % {cycle} === 0) {{
        try {{ await decoder.flush(); }} catch (_) {{}}
        try {{ decoder.reset(); }} catch (_) {{}}
      }}
      await fuzionYield();
    }}
    try {{ decoder.close(); }} catch (_) {{}}
  }}

  if ("MediaSource" in window && video) {{
    try {{
      const ms = new MediaSource();
      video.src = URL.createObjectURL(ms);
      ms.addEventListener("sourceopen", () => {{
        let sb;
        try {{
          sb = ms.addSourceBuffer('video/webm; codecs="vp8"');
        }} catch (_) {{
          return;
        }}
        let i = 0;
        const pump = () => {{
          if (performance.now() > fuzionDeadline || !sb || sb.updating) return;
          try {{ sb.appendBuffer(bytes); }} catch (_) {{}}
          i++;
          if (i < 32) setTimeout(pump, 8);
        }};
        pump();
      }}, {{ once: true }});
    }} catch (_) {{
    }}
  }}
}}();
""",
    )


def _build_canvas_gpu_pressure(rng: random.Random, case_index: int) -> _Fragment:
    width = rng.choice([256, 384, 512, 640])
    height = rng.choice([256, 384, 512])
    return _Fragment(
        body=f'<canvas id="gpu-{case_index}" width="{width}" height="{height}" style="border:1px solid #444"></canvas>',
        script=f"""
void async function canvasGpuPressure() {{
  const canvas = document.getElementById("gpu-{case_index}");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const gl = canvas.getContext("webgl2") || canvas.getContext("webgl");

  let bmp = null;
  if ("OffscreenCanvas" in window) {{
    try {{
      const off = new OffscreenCanvas(128, 128);
      const oc = off.getContext("2d");
      if (oc) {{
        for (let i = 0; i < 120; i++) {{
          oc.fillStyle = `rgba(${{(i * 7) % 255}}, ${{(i * 11) % 255}}, ${{(i * 17) % 255}}, 0.9)`;
          oc.fillRect((i * 3) % 128, (i * 5) % 128, 20, 20);
        }}
        bmp = off.transferToImageBitmap();
      }}
    }} catch (_) {{
    }}
  }}

  let i = 0;
  while (performance.now() < fuzionDeadline) {{
    if (ctx) {{
      ctx.filter = (i % 3 === 0) ? "blur(1px) contrast(1.4)" : "none";
      ctx.globalCompositeOperation = (i % 2 === 0) ? "screen" : "source-over";
      const g = ctx.createLinearGradient(0, 0, canvas.width, canvas.height);
      g.addColorStop(0, `hsl(${{(i * 13) % 360}} 80% 50%)`);
      g.addColorStop(1, `hsl(${{(i * 29) % 360}} 80% 50%)`);
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      for (let k = 0; k < 80; k++) {{
        ctx.beginPath();
        ctx.arc((k * 17 + i * 9) % canvas.width, (k * 13 + i * 5) % canvas.height, (k % 20) + 2, 0, Math.PI * 2);
        ctx.fill();
      }}
      if (bmp) {{
        ctx.drawImage(bmp, (i * 7) % canvas.width, (i * 11) % canvas.height);
      }}
      ctx.getImageData(0, 0, 1, 1);
    }}

    if (gl) {{
      gl.clearColor(((i * 3) % 255) / 255, ((i * 7) % 255) / 255, ((i * 11) % 255) / 255, 1.0);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      gl.finish();
    }}

    i++;
    if ((i & 7) === 0) await new Promise(requestAnimationFrame);
  }}
}}();
""",
    )


def _build_webrtc_pressure(rng: random.Random, case_index: int) -> _Fragment:
    rounds = rng.randint(10, 40)
    return _Fragment(
        body=f'<div id="rtc-{case_index}"></div>',
        script=f"""
void async function webrtcPressure() {{
  if (!("RTCPeerConnection" in window)) return;

  async function oneRound(i) {{
    const a = new RTCPeerConnection();
    const b = new RTCPeerConnection();
    a.onicecandidate = (e) => {{
      if (e.candidate) b.addIceCandidate(e.candidate).catch(() => {{}});
    }};
    b.onicecandidate = (e) => {{
      if (e.candidate) a.addIceCandidate(e.candidate).catch(() => {{}});
    }};

    a.createDataChannel("dc-" + i);
    try {{
      const offer = await a.createOffer();
      await a.setLocalDescription(offer);
      await b.setRemoteDescription(offer);
      const answer = await b.createAnswer();
      await b.setLocalDescription(answer);
      await a.setRemoteDescription(answer);
    }} catch (_) {{
    }} finally {{
      a.close();
      b.close();
    }}
  }}

  for (let i = 0; i < {rounds}; i++) {{
    if (performance.now() > fuzionDeadline) break;
    await oneRound(i);
    await fuzionYield();
  }}
}}();
""",
    )


_TEMPLATES: list[_Template] = [
    _Template(name="v8_pressure", weight=5, build=_build_v8_pressure),
    _Template(name="css_pressure", weight=4, build=_build_css_pressure),
    _Template(name="storage_pressure", weight=3, build=_build_storage_pressure),
    _Template(name="webcodecs_media_pressure", weight=4, build=_build_webcodecs_media_pressure),
    _Template(name="canvas_gpu_pressure", weight=3, build=_build_canvas_gpu_pressure),
    _Template(name="webrtc_pressure", weight=2, build=_build_webrtc_pressure),
]


def _pick_templates(rng: random.Random) -> list[_Template]:
    first = rng.choices(_TEMPLATES, weights=[t.weight for t in _TEMPLATES], k=1)[0]
    if rng.random() < 0.45:
        rest = [t for t in _TEMPLATES if t.name != first.name]
        second = rng.choices(rest, weights=[t.weight for t in rest], k=1)[0]
        return [first, second]
    return [first]


def generate_custom_files2(*, corpus_dir: Path, n: int, seed: int | None = None) -> None:
    """
    Generate n targeted native-surface fuzz HTML files in corpus_dir.
    """
    logger.debug(
        "generate_custom_files2 called: corpus_dir=%s, n=%d, seed=%s",
        corpus_dir, n, seed,
    )
    ensure_dir(corpus_dir)
    rng = random.Random(seed)

    manifest: list[dict[str, object]] = []
    for i in range(1, n + 1):
        picks = _pick_templates(rng)
        budget_ms = rng.randint(3500, 11000)
        fragments = [t.build(rng, i) for t in picks]
        html = _case_wrapper(
            template_names=[t.name for t in picks],
            body_chunks=[f.body for f in fragments],
            script_chunks=[f.script for f in fragments],
            budget_ms=budget_ms,
        )
        out = corpus_dir / f"custom_{i:06d}.html"
        out.write_text(html, encoding="utf-8")
        logger.debug(
            "Wrote testcase %s with template(s): %s",
            out.name,
            ", ".join(t.name for t in picks),
        )
        manifest.append(
            {
                "file": out.name,
                "templates": [t.name for t in picks],
                "budget_ms": budget_ms,
            }
        )

    manifest_path = corpus_dir / "custom_generator2_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    logger.debug("Wrote manifest: %s", manifest_path)
    print(f"Generated {n} custom testcases in {corpus_dir}")


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    generate_custom_files2(corpus_dir=root / "out" / "corpus", n=25, seed=None)
