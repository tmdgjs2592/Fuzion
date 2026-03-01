from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Optional

from .generate import generate_html_files
from .custom_generator import generate_custom_files


class Generator(Protocol):
    def generate(self, *, corpus_dir: Path, n: int) -> None: ...


@dataclass(frozen=True)
class DomatoGenerator:
    domato_dir: Path
    template_dir: Path
    format_key: str
    domato_format_arg: str

    def generate(self, *, corpus_dir: Path, n: int) -> None:
        generate_html_files(
            domato_dir=self.domato_dir,
            corpus_dir=corpus_dir,
            template_dir=self.template_dir,
            n=n,
            format_key=self.format_key,
            domato_format_arg=self.domato_format_arg,
        )


@dataclass(frozen=True)
class CustomGenerator:
    rules_path: Path
    seed: Optional[int] = None

    def generate(self, *, corpus_dir: Path, n: int) -> None:
        generate_custom_files(
            rules_path=self.rules_path,
            corpus_dir=corpus_dir,
            n=n,
            seed=self.seed,
        )