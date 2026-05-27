import numpy as np
import pytest
from pathlib import Path

from nanoporethon.sequence_designer_gui import (
    DISPLAY_53,
    FEED_53,
    PORE_FORWARDS,
    _load_qmer_map,
    build_predicted_currents,
)


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
