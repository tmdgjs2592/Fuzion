from __future__ import annotations

from pathlib import Path

import pytest

from fuzion import tui


def test_manual_prompt_user_returns_selected_sorted_html(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "z_last.html").write_text("z", encoding="utf-8")
    (tmp_path / "a_first.html").write_text("a", encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("x", encoding="utf-8")

    class StubIntPrompt:
        @staticmethod
        def ask(*args, **kwargs) -> int:
            return 1

    monkeypatch.setattr(tui, "IntPrompt", StubIntPrompt)
    assert tui.manual_prompt_user(tmp_path) == "a_first.html"


def test_manual_prompt_user_reprompts_on_out_of_range_choice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "only.html").write_text("x", encoding="utf-8")
    answers = iter([9, 1])

    class StubIntPrompt:
        @staticmethod
        def ask(*args, **kwargs) -> int:
            return next(answers)

    monkeypatch.setattr(tui, "IntPrompt", StubIntPrompt)
    assert tui.manual_prompt_user(tmp_path) == "only.html"


def test_manual_prompt_user_raises_when_no_html_files(tmp_path: Path) -> None:
    (tmp_path / "not_html.txt").write_text("x", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match=r"No \.html files found"):
        tui.manual_prompt_user(tmp_path)
