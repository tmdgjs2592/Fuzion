from __future__ import annotations

from argparse import Namespace
from io import StringIO
from pathlib import Path

from rich.console import Console

from fuzion import campaign_cli
from fuzion.campaign import CampaignSummary
from fuzion.config import default_config


def test_maybe_run_campaign_builds_config_and_generates_report(monkeypatch, tmp_path: Path) -> None:
    cfg = default_config(tmp_path)
    captured = {}
    console = Console(file=StringIO())

    def fake_run_campaign(config):
        captured["config"] = config
        return CampaignSummary(total_cases=4, abnormal_cases=1, unique_buckets=1)

    def fake_generate_report(root):
        captured["report_root"] = root
        return root / "report.html"

    monkeypatch.setattr(campaign_cli, "run_campaign", fake_run_campaign)
    monkeypatch.setattr(campaign_cli, "generate_campaign_report", fake_generate_report)

    args = Namespace(
        campaign_name="smoke",
        seed_source="manual",
        seed_count=3,
        generations=2,
        mutations_per_case=2,
        retain_per_bucket=1,
        campaign_format="html",
        random_seed=7,
        headed=True,
        browser_channel="chrome",
        browser_executable=None,
    )

    ran = campaign_cli.maybe_run_campaign(args=args, cfg=cfg, console=console, jobs=3)

    assert ran is True
    assert captured["config"].campaign_name == "smoke"
    assert captured["config"].seed_source == "manual"
    assert captured["config"].seed_count == 3
    assert captured["config"].generations == 2
    assert captured["config"].mutations_per_case == 2
    assert captured["config"].random_seed == 7
    assert captured["config"].max_concurrency == 3
    assert captured["config"].headed is True
    assert captured["config"].browser_channel == "chrome"
    assert captured["report_root"] == campaign_cli.campaign_root(captured["config"])


def test_maybe_run_campaign_validates_domato_format(monkeypatch, tmp_path: Path) -> None:
    cfg = default_config(tmp_path)
    console = Console(file=StringIO())
    monkeypatch.setattr(campaign_cli, "load_formats", lambda path: {"html": {"domato_arg": "html_only.html"}})

    args = Namespace(
        campaign_name="domato",
        seed_source="domato",
        seed_count=1,
        generations=1,
        mutations_per_case=1,
        retain_per_bucket=1,
        campaign_format="html",
        random_seed=1,
        headed=False,
        browser_channel=None,
        browser_executable=None,
    )

    seen = {}

    def fake_run(config):
        seen["config"] = config
        return CampaignSummary(total_cases=1, abnormal_cases=0, unique_buckets=0)

    monkeypatch.setattr(campaign_cli, "run_campaign", fake_run)
    monkeypatch.setattr(campaign_cli, "generate_campaign_report", lambda root: root / "report.html")

    assert campaign_cli.maybe_run_campaign(args=args, cfg=cfg, console=console, jobs=1) is True
    assert seen["config"].domato_format_arg == "html_only.html"
