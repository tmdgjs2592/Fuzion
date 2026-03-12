from __future__ import annotations

from pathlib import Path

from fuzion.campaign_triage import bucket_for_path, extract_features, extract_features_from_text, normalize_detail, root_cause


def test_extract_features_tracks_shape_and_hazards(tmp_path: Path) -> None:
    path = tmp_path / "case.html"
    path.write_text(
        "<html><head><style>div{width:7px}</style><script>while(true){}</script></head><body><div>hi</div></body></html>"
    )

    features = extract_features(path)

    assert features["script_count"] == 1
    assert features["style_count"] == 1
    assert features["max_nesting"] >= 3
    assert features["has_infinite_loop"] is True
    assert root_cause(features) == "infinite_js_loop"


def test_extract_features_from_text_handles_empty_input() -> None:
    features = extract_features_from_text("")

    assert features["html_size_bytes"] == 0
    assert features["script_count"] == 0
    assert features["style_count"] == 0
    assert features["has_large_allocation"] is False


def test_bucket_uses_normalized_detail_when_root_cause_is_unknown(tmp_path: Path) -> None:
    path = tmp_path / "case.html"
    path.write_text("<html><body><p>hi</p></body></html>")

    bucket = bucket_for_path(
        path,
        status="error",
        detail="Timeout 12000ms on http://127.0.0.1:45678/a.html",
        signal="exception",
    )

    assert "error|exception|unknown" in bucket["bucket_key"]
    assert "<ms>" in bucket["bucket_key"]
    assert ":<port>" in normalize_detail("http://127.0.0.1:45678/a.html")
