# tests/test_config.py
from pathlib import Path

from fuzion.config import default_config


# Nothing to do here but ensure that some subdirectories are contained w ithin the correct top level directories
def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def test_default_config_relationships(tmp_path):
    cfg = default_config(tmp_path)

    assert cfg.project_root == tmp_path
    assert _is_within(cfg.corpus_dir, cfg.out_dir)
    assert _is_within(cfg.findings_dir, cfg.out_dir)
    assert _is_within(cfg.domato_dir, cfg.project_root)
