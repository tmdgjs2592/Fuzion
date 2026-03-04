import json
import logging
import os
import shutil
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def now_ms() -> int:
    ms = int(time.time() * 1000)
    logger.debug("now_ms: %d", ms)
    return ms

def ensure_dir(p: Path) -> None:
    logger.debug("ensure_dir: %s", p)
    p.mkdir(parents=True, exist_ok=True)

def write_json(p: Path, obj: dict) -> None:
    logger.debug("write_json: writing to %s", p)
    p.write_text(json.dumps(obj, indent=2, sort_keys=True))
    logger.debug("write_json: wrote %d bytes to %s", p.stat().st_size, p)

def safe_rmtree(p: Path) -> None:
    if p.exists():
        logger.debug("safe_rmtree: removing %s", p)
        shutil.rmtree(p, ignore_errors=True)
        logger.debug("safe_rmtree: removed %s", p)
    else:
        logger.debug("safe_rmtree: path does not exist, skipping: %s", p)

def copytree_if_exists(src: Path, dst: Path) -> None:
    if src.exists():
        logger.debug("copytree_if_exists: copying %s -> %s", src, dst)
        shutil.copytree(src, dst, dirs_exist_ok=True)
        logger.debug("copytree_if_exists: copy complete %s -> %s", src, dst)
    else:
        logger.debug("copytree_if_exists: source does not exist, skipping: %s", src)