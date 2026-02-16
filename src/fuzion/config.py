from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class FuzionConfig:
    project_root: Path
    domato_dir: Path
    out_dir: Path
    corpus_dir: Path
    findings_dir: Path
    template_dir: Path
    bundles_yaml: Path

    nav_timeout_s: int = 10
    hard_timeout_s: int = 15  # kill browser if stuck past this
    max_concurrency: int = 1  # start simple; raise later

def default_config(project_root: Path) -> FuzionConfig:
    out_dir = project_root / "out"
    return FuzionConfig(
        project_root=project_root,
        domato_dir=project_root / "third_party" / "domato",
        out_dir=out_dir,
        corpus_dir=out_dir / "corpus",
        findings_dir=out_dir / "findings",
        template_dir= project_root / "templates",
        bundles_yaml=project_root / "grammars" / "bundles.yaml",
    )

