import numpy as np
import pytest
from pathlib import Path

from nanoporethon.sequence_designer_gui import (
    DISPLAY_53,
    DISPLAY_35,
    FEED_53,
    FEED_35,
    PORE_BACKWARDS,
    PORE_FORWARDS,
    SequenceDesignerModel,
    _load_qmer_map,
    build_predicted_currents,
    prediction_context,
)


def _write_qmer_map(path: Path, *, field_name: str, value: float) -> None:
    scipy_io = pytest.importorskip("scipy.io")
    qmers = np.array(["AAAA", "TTTT"], dtype=object)
    means = np.array([[value, value + 0.5]], dtype=float)
    errs = np.array([[0.001, 0.001]], dtype=float)
    payload = {
        field_name: {
            "qmer": qmers,
            "mean": means,
            "error": errs,
        }
    }
    scipy_io.savemat(path, payload)


def test_build_predicted_currents_falls_back_when_qmer_map_disabled(monkeypatch):
    _load_qmer_map.cache_clear()
    monkeypatch.setenv("NANOPORETHON_DISABLE_QMER_AUTODETECT", "1")
    monkeypatch.setenv("NANOPORETHON_QMER_MAP_PATH", "/definitely/missing/map.mat")

    levels = build_predicted_currents(
        "ATGCGATCGACTACTGCGACTACG",
        display_order=DISPLAY_53,
        feeding_orientation=FEED_53,
        pore_orientation=PORE_FORWARDS,
        hel308=False,
        phase_shift=0.0,
    )

    assert len(levels) == 24
    assert np.all((levels >= 0.0) & (levels <= 1.0))


def test_build_predicted_currents_matches_real_qmer_map_when_available(monkeypatch):
    _load_qmer_map.cache_clear()
    scipy = pytest.importorskip("scipy.io")
    del scipy

    map_path = "/Users/zachseitz/Downloads/NanoporeRepository/qmerdatabase_500mM150mM_forwards_phi29_5primefirst_phixhandclicked160603_withnoise.mat"
    if not Path(map_path).exists():
        pytest.skip("Local q-mer map file not available on this machine")

    monkeypatch.delenv("NANOPORETHON_DISABLE_QMER_AUTODETECT", raising=False)
    monkeypatch.setenv("NANOPORETHON_QMER_MAP_PATH", map_path)

    levels = build_predicted_currents(
        "ATGCGATCGACTACTGCGACTACG",
        display_order=DISPLAY_53,
        feeding_orientation=FEED_53,
        pore_orientation=PORE_FORWARDS,
        hel308=False,
        phase_shift=0.0,
    )

    expected = np.asarray(
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

    assert levels.shape == expected.shape
    assert np.allclose(levels, expected, atol=1e-6)


def test_prediction_context_matches_mlapp_branch_metadata():
    c1 = prediction_context(feeding_orientation=FEED_53, pore_orientation=PORE_FORWARDS, hel308=False)
    c2 = prediction_context(feeding_orientation=FEED_35, pore_orientation=PORE_FORWARDS, hel308=False)
    c3 = prediction_context(feeding_orientation=FEED_53, pore_orientation=PORE_BACKWARDS, hel308=False)
    c4 = prediction_context(feeding_orientation=FEED_35, pore_orientation=PORE_BACKWARDS, hel308=False)
    c5 = prediction_context(feeding_orientation=FEED_53, pore_orientation=PORE_FORWARDS, hel308=True)
    c6 = prediction_context(feeding_orientation=FEED_35, pore_orientation=PORE_BACKWARDS, hel308=True)

    assert c1["profile_key"] == "forwards_5p"
    assert c2["profile_key"] == "forwards_3p"
    assert c3["profile_key"] == "backwards_5p"
    assert c4["profile_key"] == "backwards_3p"
    assert c4["warning_code"] == 1

    assert c5["profile_key"] == "hel308"
    assert c5["warning_code"] == 0
    assert c5["numstep"] == 2

    assert c6["profile_key"] == "hel308"
    assert c6["warning_code"] == 2
    assert "hel308 only works" in str(c6["warning_text"]).lower()


def test_build_predicted_currents_uses_map_selected_by_profile(monkeypatch, tmp_path: Path):
    _load_qmer_map.cache_clear()

    map_specs = {
        "qmerdatabase_500mM150mM_forwards_phi29_5primefirst_phixhandclicked160603_withnoise.mat": ("qmerdatabase", 0.11),
        "qmerdatabase_500mM100mM_forwards_pcrax_3primefirst_phiX174handalignment180731_withnoise.mat": ("qmerdatabase35map", 0.21),
        "qmerdatabase_500mM150mM_backwards_phi29_5primefirst_phixhandclicked160603_withnoise.mat": ("qmerdatabase", 0.31),
        "qmerdatabase_500mM50mM_backwards_3prime.mat": ("qmerdb", 0.41),
        "qmerdatabase_400mM400mM_forwards_hel308_5primefirst_DC170321_empirical_extraction.mat": ("qmerdatabase", 0.51),
    }
    for filename, (field_name, value) in map_specs.items():
        _write_qmer_map(tmp_path / filename, field_name=field_name, value=value)

    monkeypatch.delenv("NANOPORETHON_DISABLE_QMER_AUTODETECT", raising=False)
    monkeypatch.setenv("NANOPORETHON_QMER_MAP_PATH", str(tmp_path))

    sequence = "AAAAAAA"

    _load_qmer_map.cache_clear()
    lv_f5 = build_predicted_currents(
        sequence,
        display_order=DISPLAY_53,
        feeding_orientation=FEED_53,
        pore_orientation=PORE_FORWARDS,
        hel308=False,
        phase_shift=0.0,
    )

    _load_qmer_map.cache_clear()
    lv_f3 = build_predicted_currents(
        sequence,
        display_order=DISPLAY_53,
        feeding_orientation=FEED_35,
        pore_orientation=PORE_FORWARDS,
        hel308=False,
        phase_shift=0.0,
    )

    _load_qmer_map.cache_clear()
    lv_b5 = build_predicted_currents(
        sequence,
        display_order=DISPLAY_53,
        feeding_orientation=FEED_53,
        pore_orientation=PORE_BACKWARDS,
        hel308=False,
        phase_shift=0.0,
    )

    _load_qmer_map.cache_clear()
    lv_h = build_predicted_currents(
        sequence,
        display_order=DISPLAY_53,
        feeding_orientation=FEED_53,
        pore_orientation=PORE_FORWARDS,
        hel308=True,
        phase_shift=0.0,
    )

    assert lv_f5.size > 0 and np.allclose(lv_f5[0], 0.11)
    assert lv_f3.size > 0 and np.allclose(lv_f3[0], 0.21)
    assert lv_b5.size > 0 and np.allclose(lv_b5[0], 0.31)
    assert lv_h.size > 0 and np.allclose(lv_h[0], 0.51)


def test_orientation_switches_select_map_profile_without_sequence_transform(monkeypatch, tmp_path: Path):
    _load_qmer_map.cache_clear()

    scipy_io = pytest.importorskip("scipy.io")
    qmers = np.array(["AAAA", "AAAT", "AATC", "ATCG"], dtype=object)
    means = np.array([[0.2, 0.3, 0.4, 0.5]], dtype=float)
    errs = np.array([[0.01, 0.01, 0.01, 0.01]], dtype=float)

    payload = {"qmer": qmers, "mean": means, "error": errs}
    scipy_io.savemat(tmp_path / "qmerdatabase_500mM150mM_forwards_phi29_5primefirst_phixhandclicked160603_withnoise.mat", {"qmerdatabase": payload})
    scipy_io.savemat(tmp_path / "qmerdatabase_500mM100mM_forwards_pcrax_3primefirst_phiX174handalignment180731_withnoise.mat", {"qmerdatabase35map": payload})
    scipy_io.savemat(tmp_path / "qmerdatabase_500mM150mM_backwards_phi29_5primefirst_phixhandclicked160603_withnoise.mat", {"qmerdatabase": payload})
    scipy_io.savemat(tmp_path / "qmerdatabase_500mM50mM_backwards_3prime.mat", {"qmerdb": payload})

    monkeypatch.setenv("NANOPORETHON_QMER_MAP_PATH", str(tmp_path))
    monkeypatch.delenv("NANOPORETHON_DISABLE_QMER_AUTODETECT", raising=False)

    sequence = "AAAATCG"
    combos = [
        (FEED_53, PORE_FORWARDS),
        (FEED_35, PORE_FORWARDS),
        (FEED_53, PORE_BACKWARDS),
        (FEED_35, PORE_BACKWARDS),
    ]
    outputs = []
    for feed, pore in combos:
        _load_qmer_map.cache_clear()
        outputs.append(
            build_predicted_currents(
                sequence,
                display_order=DISPLAY_53,
                feeding_orientation=feed,
                pore_orientation=pore,
                hel308=False,
                phase_shift=0.0,
            )
        )

    for arr in outputs[1:]:
        assert np.allclose(arr, outputs[0])


def test_display_order_reverses_levels(monkeypatch, tmp_path: Path):
    _load_qmer_map.cache_clear()
    scipy_io = pytest.importorskip("scipy.io")

    qmers = np.array(["AAAA", "AAAT", "AATC", "ATCG"], dtype=object)
    means = np.array([[0.1, 0.2, 0.3, 0.4]], dtype=float)
    errs = np.array([[0.01, 0.02, 0.03, 0.04]], dtype=float)
    scipy_io.savemat(
        tmp_path / "qmerdatabase_500mM150mM_forwards_phi29_5primefirst_phixhandclicked160603_withnoise.mat",
        {"qmerdatabase": {"qmer": qmers, "mean": means, "error": errs}},
    )

    monkeypatch.setenv("NANOPORETHON_QMER_MAP_PATH", str(tmp_path))
    monkeypatch.delenv("NANOPORETHON_DISABLE_QMER_AUTODETECT", raising=False)

    seq = "AAAATCG"
    _load_qmer_map.cache_clear()
    levels_53 = build_predicted_currents(
        seq,
        display_order=DISPLAY_53,
        feeding_orientation=FEED_53,
        pore_orientation=PORE_FORWARDS,
        hel308=False,
        phase_shift=0.0,
    )
    _load_qmer_map.cache_clear()
    levels_35 = build_predicted_currents(
        seq,
        display_order=DISPLAY_35,
        feeding_orientation=FEED_53,
        pore_orientation=PORE_FORWARDS,
        hel308=False,
        phase_shift=0.0,
    )

    assert np.allclose(levels_35, levels_53[::-1])


def test_export_payload_includes_mlapp_style_metadata(monkeypatch, tmp_path: Path):
    _load_qmer_map.cache_clear()
    scipy_io = pytest.importorskip("scipy.io")

    qmers = np.array(["AAAA", "AAAT", "AATC", "ATCG"], dtype=object)
    means = np.array([[0.1, 0.2, 0.3, 0.4]], dtype=float)
    errs = np.array([[0.01, 0.02, 0.03, 0.04]], dtype=float)
    scipy_io.savemat(
        tmp_path / "qmerdatabase_500mM150mM_forwards_phi29_5primefirst_phixhandclicked160603_withnoise.mat",
        {"qmerdatabase": {"qmer": qmers, "mean": means, "error": errs}},
    )

    monkeypatch.setenv("NANOPORETHON_QMER_MAP_PATH", str(tmp_path))
    monkeypatch.delenv("NANOPORETHON_DISABLE_QMER_AUTODETECT", raising=False)

    model = SequenceDesignerModel(
        sequence="AAAATCG",
        display_order=DISPLAY_35,
        feeding_orientation=FEED_53,
        pore_orientation=PORE_FORWARDS,
        hel308=False,
        phase_shift=0.0,
    )
    payload = model.export_payload()

    assert payload["details"].endswith("ordered 3p to 5p")
    assert payload["numstep"] == 1
    assert "map_filename" in payload and str(payload["map_filename"]).endswith("withnoise.mat")
    assert len(payload["levels"]) == len(payload["error"])
    assert len(payload["x"]) == len(payload["levels"]) + 1
