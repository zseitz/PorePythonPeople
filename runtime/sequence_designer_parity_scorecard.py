from __future__ import annotations

import argparse
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np

from nanoporethon.sequence_designer_gui import (
    DISPLAY_35,
    DISPLAY_53,
    FEED_35,
    FEED_53,
    PORE_BACKWARDS,
    PORE_FORWARDS,
    QMER_MAP_FILENAMES,
    SequenceDesignerModel,
    _load_qmer_map,
    build_predicted_currents,
    prediction_context,
)

TARGET_SEQUENCE = "ATGCGATCGACTACTGCGACTACG"
TARGET_LEVELS = np.asarray(
    [
        0.389701,
        0.483719,
        0.552898,
        0.521455,
        0.419356,
        0.472623,
        0.532044,
        0.498272,
        0.484212,
        0.500863,
        0.481133,
        0.511718,
        0.473181,
        0.358636,
        0.483719,
        0.552898,
        0.498272,
        0.484212,
        0.500863,
        0.481133,
        0.504552,
    ],
    dtype=float,
)
DEFAULT_OUTPUT_DIR = Path(".nanopore-runtime/parity/sequence_designer/latest")
DEFAULT_REAL_MAP = Path.home() / "Downloads" / "NanoporeRepository" / QMER_MAP_FILENAMES["forwards_5p"]


@dataclass
class CheckResult:
    check_id: str
    category: str
    status: str
    summary: str
    evidence: dict[str, Any]


class CheckSkipped(RuntimeError):
    pass


class _MapEnv:
    def __init__(self, path: Path | str | None = None):
        self.path = None if path is None else str(path)
        self._old_map_path: str | None = None
        self._old_disable: str | None = None

    def __enter__(self) -> None:
        self._old_map_path = os.environ.get("NANOPORETHON_QMER_MAP_PATH")
        self._old_disable = os.environ.get("NANOPORETHON_DISABLE_QMER_AUTODETECT")
        if self.path is None:
            os.environ.pop("NANOPORETHON_QMER_MAP_PATH", None)
        else:
            os.environ["NANOPORETHON_QMER_MAP_PATH"] = self.path
        os.environ.pop("NANOPORETHON_DISABLE_QMER_AUTODETECT", None)
        _load_qmer_map.cache_clear()

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._old_map_path is None:
            os.environ.pop("NANOPORETHON_QMER_MAP_PATH", None)
        else:
            os.environ["NANOPORETHON_QMER_MAP_PATH"] = self._old_map_path
        if self._old_disable is None:
            os.environ.pop("NANOPORETHON_DISABLE_QMER_AUTODETECT", None)
        else:
            os.environ["NANOPORETHON_DISABLE_QMER_AUTODETECT"] = self._old_disable
        _load_qmer_map.cache_clear()


def _import_scipy_io():
    try:
        from scipy import io as scipy_io  # type: ignore
    except Exception as exc:  # pragma: no cover - environment-dependent
        raise CheckSkipped(f"scipy.io unavailable: {exc}") from exc
    return scipy_io


def _write_qmer_map(path: Path, *, field_name: str, qmers: np.ndarray, means: np.ndarray, errs: np.ndarray) -> None:
    scipy_io = _import_scipy_io()
    payload = {field_name: {"qmer": qmers, "mean": means, "error": errs}}
    scipy_io.savemat(path, payload)


def _resolve_real_map_path() -> Path:
    env_path = os.environ.get("NANOPORETHON_QMER_MAP_PATH", "").strip()
    if env_path:
        candidate = Path(env_path).expanduser()
        if candidate.is_dir():
            candidate = candidate / QMER_MAP_FILENAMES["forwards_5p"]
        if candidate.exists():
            return candidate
    return DEFAULT_REAL_MAP


def _run_check(check_id: str, category: str, fn: Callable[[], dict[str, Any]]) -> CheckResult:
    try:
        evidence = fn()
        return CheckResult(check_id=check_id, category=category, status="passed", summary=evidence.pop("summary"), evidence=evidence)
    except CheckSkipped as exc:
        return CheckResult(check_id=check_id, category=category, status="skipped", summary=str(exc), evidence={})
    except Exception as exc:
        return CheckResult(check_id=check_id, category=category, status="failed", summary=str(exc), evidence={})


def _check_real_map_default_parity() -> dict[str, Any]:
    _import_scipy_io()
    real_map = _resolve_real_map_path()
    if not real_map.exists():
        raise CheckSkipped(f"real q-mer map not found at {real_map}")

    with _MapEnv(real_map):
        levels = build_predicted_currents(
            TARGET_SEQUENCE,
            display_order=DISPLAY_53,
            feeding_orientation=FEED_53,
            pore_orientation=PORE_FORWARDS,
            hel308=False,
            phase_shift=0.0,
        )
    if levels.shape != TARGET_LEVELS.shape:
        raise AssertionError(f"shape mismatch: got {levels.shape}, expected {TARGET_LEVELS.shape}")
    if not np.allclose(levels, TARGET_LEVELS, atol=1e-6):
        raise AssertionError(f"max abs error={float(np.max(np.abs(levels - TARGET_LEVELS)))}")
    return {
        "summary": "Real-map default sequence parity matches MATLAB golden levels.",
        "map_path": str(real_map),
        "max_abs_error": float(np.max(np.abs(levels - TARGET_LEVELS))),
        "levels_count": int(levels.size),
    }


def _check_branch_metadata() -> dict[str, Any]:
    contexts = {
        "forwards_5p": prediction_context(feeding_orientation=FEED_53, pore_orientation=PORE_FORWARDS, hel308=False),
        "forwards_3p": prediction_context(feeding_orientation=FEED_35, pore_orientation=PORE_FORWARDS, hel308=False),
        "backwards_5p": prediction_context(feeding_orientation=FEED_53, pore_orientation=PORE_BACKWARDS, hel308=False),
        "backwards_3p": prediction_context(feeding_orientation=FEED_35, pore_orientation=PORE_BACKWARDS, hel308=False),
        "hel308_default": prediction_context(feeding_orientation=FEED_53, pore_orientation=PORE_FORWARDS, hel308=True),
        "hel308_warning": prediction_context(feeding_orientation=FEED_35, pore_orientation=PORE_BACKWARDS, hel308=True),
    }
    assert contexts["forwards_5p"]["profile_key"] == "forwards_5p"
    assert contexts["forwards_3p"]["profile_key"] == "forwards_3p"
    assert contexts["backwards_5p"]["profile_key"] == "backwards_5p"
    assert contexts["backwards_3p"]["profile_key"] == "backwards_3p"
    assert contexts["backwards_3p"]["warning_code"] == 1
    assert contexts["hel308_default"]["numstep"] == 2
    assert contexts["hel308_warning"]["warning_code"] == 2
    return {
        "summary": "Prediction context reports expected MLAPP branch metadata and warnings.",
        "profiles": {name: ctx["profile_key"] for name, ctx in contexts.items()},
        "warning_codes": {name: int(ctx["warning_code"]) for name, ctx in contexts.items()},
    }


def _check_profile_map_selection() -> dict[str, Any]:
    qmers = np.array(["AAAA", "TTTT"], dtype=object)
    means = {
        "forwards_5p": np.array([[0.11, 0.61]], dtype=float),
        "forwards_3p": np.array([[0.21, 0.71]], dtype=float),
        "backwards_5p": np.array([[0.31, 0.81]], dtype=float),
        "backwards_3p": np.array([[0.41, 0.91]], dtype=float),
        "hel308": np.array([[0.51, 1.01]], dtype=float),
    }
    errs = np.array([[0.001, 0.001]], dtype=float)
    fields = {
        "forwards_5p": "qmerdatabase",
        "forwards_3p": "qmerdatabase35map",
        "backwards_5p": "qmerdatabase",
        "backwards_3p": "qmerdb",
        "hel308": "qmerdatabase",
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        for profile_key, filename in QMER_MAP_FILENAMES.items():
            _write_qmer_map(root / filename, field_name=fields[profile_key], qmers=qmers, means=means[profile_key], errs=errs)

        with _MapEnv(root):
            outputs = {
                "forwards_5p": build_predicted_currents("AAAAAAA", display_order=DISPLAY_53, feeding_orientation=FEED_53, pore_orientation=PORE_FORWARDS, hel308=False, phase_shift=0.0),
                "forwards_3p": build_predicted_currents("AAAAAAA", display_order=DISPLAY_53, feeding_orientation=FEED_35, pore_orientation=PORE_FORWARDS, hel308=False, phase_shift=0.0),
                "backwards_5p": build_predicted_currents("AAAAAAA", display_order=DISPLAY_53, feeding_orientation=FEED_53, pore_orientation=PORE_BACKWARDS, hel308=False, phase_shift=0.0),
                "hel308": build_predicted_currents("AAAAAAA", display_order=DISPLAY_53, feeding_orientation=FEED_53, pore_orientation=PORE_FORWARDS, hel308=True, phase_shift=0.0),
            }
        assert np.allclose(outputs["forwards_5p"][0], 0.11)
        assert np.allclose(outputs["forwards_3p"][0], 0.21)
        assert np.allclose(outputs["backwards_5p"][0], 0.31)
        assert np.allclose(outputs["hel308"][0], 0.51)
    return {
        "summary": "Profile-selected maps drive first-level outputs for each major branch.",
        "first_levels": {name: float(values[0]) for name, values in outputs.items()},
    }


def _check_orientation_no_sequence_transform() -> dict[str, Any]:
    qmers = np.array(["AAAA", "AAAT", "AATC", "ATCG"], dtype=object)
    means = np.array([[0.2, 0.3, 0.4, 0.5]], dtype=float)
    errs = np.array([[0.01, 0.01, 0.01, 0.01]], dtype=float)
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _write_qmer_map(root / QMER_MAP_FILENAMES["forwards_5p"], field_name="qmerdatabase", qmers=qmers, means=means, errs=errs)
        _write_qmer_map(root / QMER_MAP_FILENAMES["forwards_3p"], field_name="qmerdatabase35map", qmers=qmers, means=means, errs=errs)
        _write_qmer_map(root / QMER_MAP_FILENAMES["backwards_5p"], field_name="qmerdatabase", qmers=qmers, means=means, errs=errs)
        _write_qmer_map(root / QMER_MAP_FILENAMES["backwards_3p"], field_name="qmerdb", qmers=qmers, means=means, errs=errs)
        sequence = "AAAATCG"
        combos = [
            (FEED_53, PORE_FORWARDS),
            (FEED_35, PORE_FORWARDS),
            (FEED_53, PORE_BACKWARDS),
            (FEED_35, PORE_BACKWARDS),
        ]
        with _MapEnv(root):
            outputs = [
                build_predicted_currents(sequence, display_order=DISPLAY_53, feeding_orientation=feed, pore_orientation=pore, hel308=False, phase_shift=0.0)
                for feed, pore in combos
            ]
        for arr in outputs[1:]:
            assert np.allclose(arr, outputs[0])
    return {
        "summary": "Feed/pore mode selects map profile without transforming sequence-level lookup semantics.",
        "output_length": int(outputs[0].size),
    }


def _check_display_order_reversal() -> dict[str, Any]:
    qmers = np.array(["AAAA", "AAAT", "AATC", "ATCG"], dtype=object)
    means = np.array([[0.1, 0.2, 0.3, 0.4]], dtype=float)
    errs = np.array([[0.01, 0.02, 0.03, 0.04]], dtype=float)
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _write_qmer_map(root / QMER_MAP_FILENAMES["forwards_5p"], field_name="qmerdatabase", qmers=qmers, means=means, errs=errs)
        seq = "AAAATCG"
        with _MapEnv(root):
            levels_53 = build_predicted_currents(seq, display_order=DISPLAY_53, feeding_orientation=FEED_53, pore_orientation=PORE_FORWARDS, hel308=False, phase_shift=0.0)
            levels_35 = build_predicted_currents(seq, display_order=DISPLAY_35, feeding_orientation=FEED_53, pore_orientation=PORE_FORWARDS, hel308=False, phase_shift=0.0)
        assert np.allclose(levels_35, levels_53[::-1])
    return {
        "summary": "Display-order switch reverses output levels the MATLAB way.",
        "levels_53": levels_53.tolist(),
        "levels_35": levels_35.tolist(),
    }


def _check_export_payload_metadata() -> dict[str, Any]:
    qmers = np.array(["AAAA", "AAAT", "AATC", "ATCG"], dtype=object)
    means = np.array([[0.1, 0.2, 0.3, 0.4]], dtype=float)
    errs = np.array([[0.01, 0.02, 0.03, 0.04]], dtype=float)
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _write_qmer_map(root / QMER_MAP_FILENAMES["forwards_5p"], field_name="qmerdatabase", qmers=qmers, means=means, errs=errs)
        with _MapEnv(root):
            payload = SequenceDesignerModel(
                sequence="AAAATCG",
                display_order=DISPLAY_35,
                feeding_orientation=FEED_53,
                pore_orientation=PORE_FORWARDS,
                hel308=False,
                phase_shift=0.0,
            ).export_payload()
    assert str(payload["details"]).endswith("ordered 3p to 5p")
    assert int(payload["numstep"]) == 1
    assert len(payload["levels"]) == len(payload["error"])
    assert len(payload["x"]) == len(payload["levels"]) + 1
    return {
        "summary": "Export payload contains MATLAB-style metadata needed for golden acceptance checks.",
        "details": payload["details"],
        "numstep": int(payload["numstep"]),
        "map_filename": payload["map_filename"],
    }


def build_scorecard() -> dict[str, Any]:
    checks = [
        _run_check("real_map_default_parity", "numeric", _check_real_map_default_parity),
        _run_check("branch_metadata", "branching", _check_branch_metadata),
        _run_check("profile_map_selection", "branching", _check_profile_map_selection),
        _run_check("orientation_no_transform", "semantics", _check_orientation_no_sequence_transform),
        _run_check("display_order_reversal", "display", _check_display_order_reversal),
        _run_check("export_payload_metadata", "export", _check_export_payload_metadata),
    ]
    passed = sum(1 for check in checks if check.status == "passed")
    failed = sum(1 for check in checks if check.status == "failed")
    skipped = sum(1 for check in checks if check.status == "skipped")
    return {
        "component": "sequence_designer_gui",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": len(checks),
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "graduation_ready": failed == 0,
        },
        "checks": [asdict(check) for check in checks],
    }


def _render_markdown(scorecard: dict[str, Any]) -> str:
    summary = scorecard["summary"]
    lines = [
        "# Sequence Designer Parity Scorecard",
        "",
        f"Generated: `{scorecard['generated_at']}`",
        "",
        f"- Passed: **{summary['passed']}**",
        f"- Failed: **{summary['failed']}**",
        f"- Skipped: **{summary['skipped']}**",
        f"- Graduation ready: **{'yes' if summary['graduation_ready'] else 'no'}**",
        "",
        "| Check | Category | Status | Summary |",
        "|---|---|---|---|",
    ]
    for check in scorecard["checks"]:
        lines.append(f"| `{check['check_id']}` | {check['category']} | {check['status']} | {check['summary']} |")
    return "\n".join(lines) + "\n"


def write_scorecard_artifacts(scorecard: dict[str, Any], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "sequence_designer_parity_scorecard.json"
    markdown_path = output_dir / "sequence_designer_parity_scorecard.md"
    json_path.write_text(json.dumps(scorecard, indent=2), encoding="utf-8")
    markdown_path.write_text(_render_markdown(scorecard), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate sequence designer parity scorecard artifacts.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for generated JSON/Markdown artifacts.")
    args = parser.parse_args(argv)

    scorecard = build_scorecard()
    paths = write_scorecard_artifacts(scorecard, Path(args.output_dir))
    print(json.dumps({
        "summary": scorecard["summary"],
        "artifacts": {name: str(path) for name, path in paths.items()},
    }, indent=2))
    return 0 if scorecard["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
