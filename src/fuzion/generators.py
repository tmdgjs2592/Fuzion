from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Optional

from .generate import generate_html_files
from .custom_generator import generate_custom_files

logger = logging.getLogger(__name__)


class Generator(Protocol):
    def generate(self, *, corpus_dir: Path, n: int) -> None: ...


@dataclass(frozen=True)
class DomatoGenerator:
    domato_dir: Path
    template_dir: Path
    format_key: str
    domato_format_arg: str

    def generate(self, *, corpus_dir: Path, n: int) -> None:
        logger.debug(
            "DomatoGenerator.generate called: corpus_dir=%s, n=%d, format_key=%s, domato_format_arg=%s",
            corpus_dir, n, self.format_key, self.domato_format_arg,
        )
        generate_html_files(
            domato_dir=self.domato_dir,
            corpus_dir=corpus_dir,
            template_dir=self.template_dir,
            n=n,
            format_key=self.format_key,
            domato_format_arg=self.domato_format_arg,
        )
        logger.debug(
            "DomatoGenerator.generate complete: %d file(s) written to %s",
            n, corpus_dir,
        )


@dataclass(frozen=True)
class CustomGenerator:
    rules_path: Path
    seed: Optional[int] = None

    def generate(self, *, corpus_dir: Path, n: int) -> None:
        logger.debug(
            "CustomGenerator.generate called: corpus_dir=%s, n=%d, rules_path=%s, seed=%s",
            corpus_dir, n, self.rules_path, self.seed,
        )
        generate_custom_files(
            rules_path=self.rules_path,
            corpus_dir=corpus_dir,
            n=n,
            seed=self.seed,
        )
        logger.debug(
            "CustomGenerator.generate complete: %d file(s) written to %s",
            n, corpus_dir,
        )