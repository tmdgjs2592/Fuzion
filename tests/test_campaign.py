from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from fuzion.campaign import CampaignConfig, _select_parents, _splice_donor, materialize_seed_cases, run_campaign


def test_materialize_manual_seed_cases(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    manual_dir = project_root / "manual"
    manual_dir.mkdir(parents=True)
    (manual_dir / "a.html").write_text("<html></html>", encoding="utf-8")
    (manual_dir / "b.html").write_text("<html></html>", encoding="utf-8")

    cases = materialize_seed_cases(
        CampaignConfig(
            project_root=project_root,
            out_dir=tmp_path / "out",
            campaign_name="smoke",
            seed_source="manual",
            seed_count=1,
        )
    )

    assert len(cases) == 1
    assert cases[0].case_id == "gen_0000_case_000001"


def test_materialize_manual_seed_cases_requires_enough_files(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    manual_dir = project_root / "manual"
    manual_dir.mkdir(parents=True)
    (manual_dir / "a.html").write_text("<html></html>", encoding="utf-8")

    with pytest.raises(ValueError, match="manual seed source only has 1 HTML files, need 2"):
        materialize_seed_cases(
            CampaignConfig(
                project_root=project_root,
                out_dir=tmp_path / "out",
                campaign_name="smoke",
                seed_source="manual",
                seed_count=2,
            )
        )


def test_run_campaign_writes_cases_and_summary(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    manual_dir = project_root / "manual"
    manual_dir.mkdir(parents=True)
    (manual_dir / "seed.html").write_text(
        "<html><head><script>while(true){}</script></head><body><div>hi</div></body></html>",
        encoding="utf-8",
    )

    async def fake_run_corpus(**kwargs):
        html_path = sorted(kwargs["corpus_dir"].glob("*.html"))[0]
        result = SimpleNamespace(status="timeout", detail="Timeout 10000ms exceeded", elapsed_ms=12)
        return SimpleNamespace(ok=0, timeout=1), [(html_path, result)]

    monkeypatch.setattr("fuzion.campaign._run_corpus", fake_run_corpus)

    summary = run_campaign(
        CampaignConfig(
            project_root=project_root,
            out_dir=tmp_path / "out",
            campaign_name="smoke",
            seed_source="manual",
            seed_count=1,
        )
    )

    root = tmp_path / "out" / "campaigns" / "smoke"
    payload = json.loads((root / "gen_0000" / "cases.json").read_text(encoding="utf-8"))
    campaign_summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))

    assert summary.total_cases == 1
    assert summary.abnormal_cases == 1
    assert payload["cases"][0]["signal"] == "playwright_timeout"
    assert payload["cases"][0]["root_cause"] == "infinite_js_loop"
    assert campaign_summary["total_cases"] == 1


def test_run_campaign_writes_mutated_second_generation(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    manual_dir = project_root / "manual"
    manual_dir.mkdir(parents=True)
    (manual_dir / "seed.html").write_text(
        "<html><head><style>div{width:7px;}</style><script>var x = 7;</script></head><body><div>hi</div></body></html>",
        encoding="utf-8",
    )

    async def fake_run_corpus(**kwargs):
        html_path = sorted(kwargs["corpus_dir"].glob("*.html"))[0]
        result = SimpleNamespace(status="error", detail="boom 10000ms", elapsed_ms=7)
        return SimpleNamespace(ok=0, error=1), [(html_path, result)]

    monkeypatch.setattr("fuzion.campaign._run_corpus", fake_run_corpus)

    run_campaign(
        CampaignConfig(
            project_root=project_root,
            out_dir=tmp_path / "out",
            campaign_name="multi",
            seed_source="manual",
            seed_count=1,
            generations=2,
            mutations_per_case=1,
        )
    )

    root = tmp_path / "out" / "campaigns" / "multi"
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    gen1 = json.loads((root / "gen_0001" / "cases.json").read_text(encoding="utf-8"))

    assert len(summary["generations"]) == 2
    assert summary["generations"][0]["selection_mode"] == "novel_buckets"
    assert summary["generations"][1]["mutator_counts"]
    assert gen1["cases"][0]["parent_id"] == "gen_0000_case_000001"


def test_run_campaign_forwards_runner_options(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    manual_dir = project_root / "manual"
    manual_dir.mkdir(parents=True)
    (manual_dir / "seed.html").write_text("<html><body>hi</body></html>", encoding="utf-8")

    seen = {}

    async def fake_run_corpus(**kwargs):
        seen["kwargs"] = kwargs
        html_path = sorted(kwargs["corpus_dir"].glob("*.html"))[0]
        result = SimpleNamespace(status="ok", detail="loaded", elapsed_ms=5)
        return SimpleNamespace(ok=1), [(html_path, result)]

    monkeypatch.setattr("fuzion.campaign._run_corpus", fake_run_corpus)

    run_campaign(
        CampaignConfig(
            project_root=project_root,
            out_dir=tmp_path / "out",
            campaign_name="opts",
            seed_source="manual",
            seed_count=1,
            headed=True,
            browser_channel="chrome",
            max_concurrency=3,
        )
    )

    assert seen["kwargs"]["headed"] is True
    assert seen["kwargs"]["browser_channel"] == "chrome"
    assert seen["kwargs"]["browser_executable_path"] is None
    assert seen["kwargs"]["max_concurrency"] == 3


def test_run_campaign_records_splice_parent_for_splice_mutation(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    manual_dir = project_root / "manual"
    manual_dir.mkdir(parents=True)
    (manual_dir / "a.html").write_text(
        "<html><head><script>while(true){}</script></head><body><div>one</div></body></html>",
        encoding="utf-8",
    )
    (manual_dir / "b.html").write_text(
        "<html><head><script>new ArrayBuffer(1000000);</script></head><body><div>two</div></body></html>",
        encoding="utf-8",
    )

    async def fake_run_corpus(**kwargs):
        results = []
        for html_path in sorted(kwargs["corpus_dir"].glob("*.html")):
            results.append((html_path, SimpleNamespace(status="error", detail="boom", elapsed_ms=7)))
        return SimpleNamespace(ok=0, error=len(results)), results

    def fake_mutate_file(source_path, output_path, **kwargs):
        output_path.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
        return "splice_js_section"

    monkeypatch.setattr("fuzion.campaign._run_corpus", fake_run_corpus)
    monkeypatch.setattr("fuzion.campaign.mutate_file", fake_mutate_file)

    run_campaign(
        CampaignConfig(
            project_root=project_root,
            out_dir=tmp_path / "out",
            campaign_name="splice",
            seed_source="manual",
            seed_count=2,
            generations=2,
            mutations_per_case=1,
            retain_per_bucket=1,
        )
    )

    gen1 = json.loads((tmp_path / "out" / "campaigns" / "splice" / "gen_0001" / "cases.json").read_text(encoding="utf-8"))
    ids = {case["parent_id"]: case["splice_parent_id"] for case in gen1["cases"]}

    assert ids["gen_0000_case_000001"] == "gen_0000_case_000002"
    assert ids["gen_0000_case_000002"] == "gen_0000_case_000001"


def test_splice_donor_rotates_across_other_parents() -> None:
    parents = [
        SimpleNamespace(case_id="a"),
        SimpleNamespace(case_id="b"),
        SimpleNamespace(case_id="c"),
    ]

    assert _splice_donor(parents, 0, 0).case_id == "b"
    assert _splice_donor(parents, 0, 1).case_id == "c"
    assert _splice_donor(parents, 1, 0).case_id == "c"
    assert _splice_donor(parents, 1, 1).case_id == "a"


def test_select_parents_prefers_novel_buckets(tmp_path: Path) -> None:
    config = CampaignConfig(
        project_root=tmp_path,
        out_dir=tmp_path / "out",
        campaign_name="novel",
        seed_source="manual",
        seed_count=1,
        retain_per_bucket=1,
    )
    records = [
        {
            "case_id": "a",
            "generation": 0,
            "source_path": str(tmp_path / "a.html"),
            "stage": "seed",
            "parent_id": "",
            "mutator": "",
            "status": "timeout",
            "elapsed_ms": 10,
            "bucket_id": "known",
        },
        {
            "case_id": "b",
            "generation": 0,
            "source_path": str(tmp_path / "b.html"),
            "stage": "seed",
            "parent_id": "",
            "mutator": "",
            "status": "timeout",
            "elapsed_ms": 8,
            "bucket_id": "novel",
        },
    ]

    selected, mode = _select_parents(config, records, {"known"})

    assert mode == "novel_buckets"
    assert [case.case_id for case in selected] == ["b"]
