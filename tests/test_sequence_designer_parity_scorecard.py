from __future__ import annotations

import json
from pathlib import Path

from runtime.sequence_designer_parity_scorecard import build_scorecard, write_scorecard_artifacts


def test_build_scorecard_has_no_failed_checks() -> None:
    scorecard = build_scorecard()

    assert scorecard["component"] == "sequence_designer_gui"
    assert scorecard["summary"]["failed"] == 0
    assert scorecard["summary"]["passed"] >= 5
    assert len(scorecard["checks"]) >= 6
    assert all(check["status"] in {"passed", "skipped"} for check in scorecard["checks"])


def test_write_scorecard_artifacts_creates_json_and_markdown(tmp_path: Path) -> None:
    scorecard = build_scorecard()

    paths = write_scorecard_artifacts(scorecard, tmp_path)

    json_path = paths["json"]
    markdown_path = paths["markdown"]

    assert json_path.exists()
    assert markdown_path.exists()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["summary"]["failed"] == 0
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "# Sequence Designer Parity Scorecard" in markdown
    assert "Graduation ready" in markdown
