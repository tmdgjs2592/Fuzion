from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from pathlib import Path
import random
import shutil

from .campaign_mutator import mutate_file
from .campaign_triage import bucket_for_path, summarize_generation
from .generators import CustomGenerator, CustomGeneratorV2, DomatoGenerator
from .util import ensure_dir, safe_rmtree, write_json


@dataclass(frozen=True)
class CampaignConfig:
    project_root: Path
    out_dir: Path
    campaign_name: str
    seed_source: str
    seed_count: int
    generations: int = 1
    mutations_per_case: int = 1
    retain_per_bucket: int = 1
    nav_timeout_s: int = 10
    hard_timeout_s: int = 15
    max_concurrency: int = 1
    headed: bool = False
    browser_channel: str | None = None
    browser_executable_path: Path | None = None
    domato_format_key: str = "html"
    domato_format_arg: str = "html_only.html"
    random_seed: int = 42

    def to_dict(self) -> dict:
        data = asdict(self)
        data["project_root"] = str(self.project_root)
        data["out_dir"] = str(self.out_dir)
        if self.browser_executable_path is not None:
            data["browser_executable_path"] = str(self.browser_executable_path)
        return data


@dataclass(frozen=True)
class CampaignCase:
    case_id: str
    generation: int
    source_path: Path
    stage: str
    parent_id: str = ""
    mutator: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        data["source_path"] = str(self.source_path)
        return data


@dataclass(frozen=True)
class CampaignSummary:
    total_cases: int
    abnormal_cases: int
    unique_buckets: int


def campaign_root(config: CampaignConfig) -> Path:
    return config.out_dir / "campaigns" / config.campaign_name


def generation_dir(config: CampaignConfig, generation: int) -> Path:
    return campaign_root(config) / f"gen_{generation:04d}"


def _case_id(generation: int, index: int) -> str:
    return f"gen_{generation:04d}_case_{index:06d}"


def _validate_config(config: CampaignConfig) -> None:
    if config.seed_count < 1:
        raise ValueError("seed_count must be >= 1")
    if config.generations < 1:
        raise ValueError("generations must be >= 1")
    if config.mutations_per_case < 1:
        raise ValueError("mutations_per_case must be >= 1")
    if config.retain_per_bucket < 1:
        raise ValueError("retain_per_bucket must be >= 1")
    if config.max_concurrency < 1:
        raise ValueError("max_concurrency must be >= 1")
    if config.nav_timeout_s < 1 or config.hard_timeout_s < 1:
        raise ValueError("timeouts must be >= 1")


def _prepare_root(config: CampaignConfig) -> None:
    root = campaign_root(config)
    safe_rmtree(root)
    ensure_dir(root / "findings")
    write_json(root / "manifest.json", {"config": config.to_dict()})


def _manual_seed_files(config: CampaignConfig, out_dir: Path) -> list[Path]:
    sources = sorted((config.project_root / "manual").glob("*.html"))
    if len(sources) < config.seed_count:
        raise ValueError(f"manual seed source only has {len(sources)} HTML files, need {config.seed_count}")

    paths = []
    for index, source in enumerate(sources[: config.seed_count], start=1):
        target = out_dir / f"{_case_id(0, index)}.html"
        shutil.copyfile(source, target)
        paths.append(target)
    return paths


def _generator_for(config: CampaignConfig):
    if config.seed_source == "custom":
        return CustomGenerator(
            rules_path=config.project_root / "grammars" / "html_rules.yaml",
            seed=config.random_seed,
        )
    if config.seed_source == "custom_v2":
        return CustomGeneratorV2(seed=config.random_seed)
    if config.seed_source == "domato":
        return DomatoGenerator(
            domato_dir=config.project_root / "third_party" / "domato",
            template_dir=config.project_root / "templates",
            format_key=config.domato_format_key,
            domato_format_arg=config.domato_format_arg,
        )
    raise ValueError(f"Unsupported seed_source: {config.seed_source}")


def _generate_seed_files(config: CampaignConfig) -> list[Path]:
    out_dir = generation_dir(config, 0)
    ensure_dir(out_dir)

    if config.seed_source == "manual":
        return _manual_seed_files(config, out_dir)

    generator = _generator_for(config)
    generator.generate(corpus_dir=out_dir, n=config.seed_count)
    generated = sorted(out_dir.glob("*.html"))
    if len(generated) < config.seed_count:
        raise ValueError(f"seed source produced {len(generated)} HTML files, need {config.seed_count}")

    renamed = []
    for index, source in enumerate(generated[: config.seed_count], start=1):
        target = out_dir / f"{_case_id(0, index)}.html"
        if source != target:
            source.rename(target)
        renamed.append(target)
    return renamed


def materialize_seed_cases(config: CampaignConfig) -> list[CampaignCase]:
    return [
        CampaignCase(case_id=path.stem, generation=0, source_path=path, stage="seed")
        for path in _generate_seed_files(config)
    ]


def _signal_for_result(status: str, detail: str) -> str:
    if status == "ok":
        return "loaded"
    if status == "hang":
        return "hard_timeout"
    if status == "timeout":
        return "playwright_timeout"
    if status == "crash":
        return "crash"
    lowered = detail.lower()
    if "targetclosederror" in lowered or "target page, context or browser has been closed" in lowered:
        return "target_closed"
    if "javascript error" in lowered:
        return "js_error"
    if "net::" in lowered:
        return "navigation_error"
    return "error"


def _record_for_result(config: CampaignConfig, case: CampaignCase, result) -> dict:
    signal = _signal_for_result(result.status, result.detail)
    bucket = bucket_for_path(case.source_path, status=result.status, detail=result.detail, signal=signal)
    finding_dir = campaign_root(config) / "findings" / case.case_id
    input_snapshot = finding_dir / "input.html"
    abnormal = result.status != "ok"
    return {
        **case.to_dict(),
        "status": result.status,
        "detail": result.detail,
        "elapsed_ms": result.elapsed_ms,
        "signal": signal,
        "finding_dir": str(finding_dir) if abnormal else "",
        "input_snapshot": str(input_snapshot) if abnormal else "",
        **bucket,
    }


def _run_corpus(**kwargs):
    from .orchestrator import run_corpus

    return run_corpus(**kwargs)


async def _execute_generation(config: CampaignConfig, cases: list[CampaignCase]) -> list[dict]:
    by_name = {case.source_path.name: case for case in cases}
    _summary, results = await _run_corpus(
        corpus_dir=generation_dir(config, cases[0].generation) if cases else campaign_root(config),
        findings_dir=campaign_root(config) / "findings",
        nav_timeout_s=config.nav_timeout_s,
        hard_timeout_s=config.hard_timeout_s,
        max_concurrency=config.max_concurrency,
        headed=config.headed,
        browser_channel=config.browser_channel,
        browser_executable_path=config.browser_executable_path,
    )
    return [_record_for_result(config, by_name[path.name], result) for path, result in results]


def _write_generation(config: CampaignConfig, generation: int, records: list[dict]) -> None:
    write_json(generation_dir(config, generation) / "cases.json", {"generation": generation, "cases": records})


def _case_from_record(record: dict) -> CampaignCase:
    return CampaignCase(
        case_id=record["case_id"],
        generation=record["generation"],
        source_path=Path(record["source_path"]),
        stage=record["stage"],
        parent_id=record.get("parent_id", ""),
        mutator=record.get("mutator", ""),
    )


def _select_parents(config: CampaignConfig, records: list[dict], seen_buckets: set[str]) -> tuple[list[CampaignCase], str]:
    def collect(*, novel_only: bool) -> list[CampaignCase]:
        grouped: dict[str, list[dict]] = {}
        for record in records:
            if record["status"] == "ok":
                continue
            if novel_only and record["bucket_id"] in seen_buckets:
                continue
            grouped.setdefault(record["bucket_id"], []).append(record)

        selected: list[CampaignCase] = []
        for bucket_id in sorted(grouped):
            ranked = sorted(grouped[bucket_id], key=lambda item: item["elapsed_ms"])
            selected.extend(_case_from_record(item) for item in ranked[: config.retain_per_bucket])
        return selected

    selected = collect(novel_only=True)
    if selected:
        return selected, "novel_buckets"
    selected = collect(novel_only=False)
    if selected:
        return selected, "all_abnormal"
    return [_case_from_record(record) for record in records], "all_results"


def _mutate_cases(config: CampaignConfig, generation: int, parents: list[CampaignCase]) -> list[CampaignCase]:
    rng = random.Random(config.random_seed + generation)
    domato_dir = config.project_root / "third_party" / "domato"
    out_dir = generation_dir(config, generation)
    ensure_dir(out_dir)

    children: list[CampaignCase] = []
    index = 1
    for parent in parents:
        for _ in range(config.mutations_per_case):
            case_id = _case_id(generation, index)
            output_path = out_dir / f"{case_id}.html"
            mutator = mutate_file(parent.source_path, output_path, rng=rng, domato_dir=domato_dir)
            children.append(
                CampaignCase(
                    case_id=case_id,
                    generation=generation,
                    source_path=output_path,
                    stage="mutated",
                    parent_id=parent.case_id,
                    mutator=mutator,
                )
            )
            index += 1
    return children


def _summary_entry(generation: int, records: list[dict], selection_mode: str | None, parent_ids: list[str]) -> dict:
    return {
        "generation": generation,
        **summarize_generation(records),
        "selection_mode": selection_mode,
        "selected_parent_ids": parent_ids,
    }


def _write_summary(config: CampaignConfig, entries: list[dict]) -> None:
    write_json(
        campaign_root(config) / "summary.json",
        {
            "campaign_name": config.campaign_name,
            "config": config.to_dict(),
            "total_cases": sum(entry["total_cases"] for entry in entries),
            "abnormal_cases": sum(entry["abnormal_cases"] for entry in entries),
            "unique_buckets": len({bucket for entry in entries for bucket in entry["bucket_counts"]}),
            "generations": entries,
        },
    )


def run_campaign(config: CampaignConfig) -> CampaignSummary:
    _validate_config(config)
    _prepare_root(config)

    current_cases = materialize_seed_cases(config)
    seen_buckets: set[str] = set()
    summaries: list[dict] = []
    total_cases = 0
    abnormal_cases = 0

    for generation in range(config.generations):
        records = asyncio.run(_execute_generation(config, current_cases))
        _write_generation(config, generation, records)
        total_cases += len(records)
        abnormal_cases += sum(1 for record in records if record["status"] != "ok")

        selection_mode = None
        parent_ids: list[str] = []
        if generation + 1 < config.generations:
            parents, selection_mode = _select_parents(config, records, seen_buckets)
            parent_ids = [case.case_id for case in parents]
            current_cases = _mutate_cases(config, generation + 1, parents)

        seen_buckets.update(record["bucket_id"] for record in records if record["status"] != "ok")
        summaries.append(_summary_entry(generation, records, selection_mode, parent_ids))

    _write_summary(config, summaries)
    return CampaignSummary(total_cases=total_cases, abnormal_cases=abnormal_cases, unique_buckets=len(seen_buckets))
