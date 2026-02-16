import json
import os
import shutil
import time
from pathlib import Path

def now_ms() -> int:
    return int(time.time() * 1000)

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def write_json(p: Path, obj: dict) -> None:
    p.write_text(json.dumps(obj, indent=2, sort_keys=True))

def safe_rmtree(p: Path) -> None:
    if p.exists():
        shutil.rmtree(p, ignore_errors=True)

def copytree_if_exists(src: Path, dst: Path) -> None:
    if src.exists():
        shutil.copytree(src, dst, dirs_exist_ok=True)

