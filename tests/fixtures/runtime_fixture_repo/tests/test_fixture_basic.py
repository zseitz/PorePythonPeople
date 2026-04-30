"""Minimal fixture repo test — always passes.

This file exists so that `pytest -q` run against the fixture repository
exits with code 0 (tests pass) rather than code 5 (no tests collected),
allowing the verify stage gate to resolve correctly in integration tests.
"""


def test_fixture_always_passes() -> None:
    assert True
