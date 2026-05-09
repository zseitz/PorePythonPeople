from __future__ import annotations

import builtins
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import h5py
import numpy as np
import pytest

import nanoporethon.subcomponent_4_config_manager as sub4
import nanoporethon.subcomponent_5_directory_utilities as sub5
import nanoporethon.subcomponent_6_search_log_utilities as sub6
import nanoporethon.subcomponent_7_mat_file_loader as sub7


def test_config_manager_handles_write_and_remove_failures(monkeypatch, tmp_path):
    cfg_path = tmp_path / "cfg.json"
    monkeypatch.setattr(sub4, "CONFIG_FILE", str(cfg_path))

    def boom_open(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("builtins.open", boom_open)
    # Should not raise
    sub4.save_config({"a": 1})

    cfg_path.write_text("{}", encoding="utf-8")

    def boom_remove(_path):
        raise PermissionError("locked")

    monkeypatch.setattr(sub4.os, "remove", boom_remove)
    # Should not raise
    sub4.clear_config()


def test_directory_utilities_no_prompt_and_validation_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(sub5, "get_database_directory", lambda: None)
    monkeypatch.setattr(sub5, "get_logs_directory", lambda: None)

    assert sub5.select_database_directory(allow_prompt=False) is None
    assert sub5.select_logs_directory(allow_prompt=False) is None

    monkeypatch.setattr(sub5, "browse_for_directory", lambda _title: None)
    assert sub5.select_database_directory(allow_prompt=True) is None
    assert sub5.select_logs_directory(allow_prompt=True) is None

    assert sub5.validate_directory(None) is False
    assert sub5.validate_directory(str(tmp_path / "missing")) is False


def test_search_log_utilities_exception_fallbacks(monkeypatch, tmp_path):
    log_path = tmp_path / "search_query.txt"

    def boom_open(*_args, **_kwargs):
        raise OSError("cannot read")

    monkeypatch.setattr("builtins.open", boom_open)
    source, files = sub6.load_search_log(str(log_path))
    assert source is None
    assert files == []

    monkeypatch.setattr(sub6.os.path, "isdir", lambda _p: True)

    def boom_listdir(_p):
        raise OSError("cannot list")

    monkeypatch.setattr(sub6.os, "listdir", boom_listdir)
    assert sub6.find_search_queries(str(tmp_path)) == []


def test_extract_numeric_from_dataset_handles_object_references(tmp_path):
    mat_path = tmp_path / "refs.mat"
    with h5py.File(mat_path, "w") as f:
        target = f.create_dataset("target", data=np.array([1.25, 2.5]))
        refs = f.create_dataset("refs", (1,), dtype=h5py.ref_dtype)
        refs[0] = target.ref
        out = sub7._extract_numeric_from_dataset(refs, f)

    assert np.allclose(out, np.array([1.25, 2.5]))


def test_find_dataset_case_insensitive_recurses_groups(tmp_path):
    mat_path = tmp_path / "nested.mat"
    with h5py.File(mat_path, "w") as f:
        g1 = f.create_group("Event")
        g2 = g1.create_group("Inner")
        g2.create_dataset("Quality", data=np.array([7]))
        found = sub7._find_dataset_case_insensitive(f, "quality")
        assert found is not None
        assert int(np.array(found[()]).flatten()[0]) == 7


def test_load_event_vector_handles_non_dataset_branch():
    root = {"eventnum": [1, 2, 3]}
    out = sub7._load_event_vector(None, root, "eventnum")
    assert np.allclose(out, np.array([1.0, 2.0, 3.0]))


def test_mat_recursive_field_extract_helpers_cover_object_and_nested_paths():
    nested = {
        "outer": np.array([
            {"eventStartPt": np.array([5, 6])},
            {"other": np.array([1])},
        ], dtype=object)
    }

    found = sub7._mat_find_field(nested, "eventStartPt")
    arr = sub7._mat_to_numeric_array(found)

    assert found is not None
    assert np.allclose(arr, np.array([5.0, 6.0]))


def test_load_event_data_falls_back_to_scipy_when_h5_fails(monkeypatch, tmp_path):
    event_path = tmp_path / "event_nonhdf5.mat"
    event_path.write_text("placeholder", encoding="utf-8")

    class FakeScipy:
        @staticmethod
        def loadmat(_path, squeeze_me=True, struct_as_record=False):
            event_obj = SimpleNamespace(
                eventnum=np.array([1, 2]),
                eventStartPt=np.array([10, 20]),
                eventEndPt=np.array([11, 21]),
                eventStartNdx=np.array([100, 200]),
                eventEndNdx=np.array([110, 210]),
                quality=np.array([0.1, 0.9]),
                localIOS=np.array([9.0, 8.0]),
            )
            return {"event": event_obj}

    def boom_h5(*_args, **_kwargs):
        raise OSError("not an hdf5 file")

    monkeypatch.setattr(sub7.h5py, "File", boom_h5)
    monkeypatch.setattr(sub7, "scipy_io", FakeScipy)

    out = sub7.load_event_data(str(event_path))
    assert np.allclose(out["eventnum"], np.array([1.0, 2.0]))
    assert np.allclose(out["quality"], np.array([0.1, 0.9]))


def test_load_fsamp_from_event_mat_nested_group_and_scipy_fallback(monkeypatch, tmp_path):
    # HDF5 nested-group lookup path
    h5_path = tmp_path / "event_nested.mat"
    with h5py.File(h5_path, "w") as f:
        event_group = f.create_group("event")
        nested = event_group.create_group("nested")
        nested.create_dataset("Fs", data=np.array([2500.0]))

    assert sub7.load_fsamp_from_event_mat(str(h5_path)) == 2500.0

    # scipy fallback path
    fallback_path = tmp_path / "event_fallback.mat"
    fallback_path.write_text("placeholder", encoding="utf-8")

    class FakeScipy:
        @staticmethod
        def loadmat(_path, squeeze_me=True, struct_as_record=False):
            return {"event": SimpleNamespace(fsamp=np.array([4000.0]))}

    def boom_h5(*_args, **_kwargs):
        raise OSError("not hdf5")

    monkeypatch.setattr(sub7.h5py, "File", boom_h5)
    monkeypatch.setattr(sub7, "scipy_io", FakeScipy)

    assert sub7.load_fsamp_from_event_mat(str(fallback_path)) == 4000.0


def test_load_fsamp_from_meta_mat_nested_group_and_scipy_fallback(monkeypatch, tmp_path):
    # HDF5 nested-group lookup path
    h5_path = tmp_path / "meta_nested.mat"
    with h5py.File(h5_path, "w") as f:
        meta_group = f.create_group("meta")
        nested = meta_group.create_group("level2")
        nested.create_dataset("samplingFrequency", data=np.array([1200.0]))

    assert sub7.load_fsamp_from_meta_mat(str(h5_path)) == 1200.0

    # scipy fallback path
    fallback_path = tmp_path / "meta_fallback.mat"
    fallback_path.write_text("placeholder", encoding="utf-8")

    class FakeScipy:
        @staticmethod
        def loadmat(_path, squeeze_me=True, struct_as_record=False):
            return {"meta": SimpleNamespace(sampleRate=np.array([800.0]))}

    def boom_h5(*_args, **_kwargs):
        raise OSError("not hdf5")

    monkeypatch.setattr(sub7.h5py, "File", boom_h5)
    monkeypatch.setattr(sub7, "scipy_io", FakeScipy)

    assert sub7.load_fsamp_from_meta_mat(str(fallback_path)) == 800.0


def test_load_reduced_mat_handles_h5_open_failure(monkeypatch, tmp_path):
    reduced_path = tmp_path / "broken_reduced.mat"
    reduced_path.write_text("placeholder", encoding="utf-8")

    def boom_h5(*_args, **_kwargs):
        raise OSError("cannot open")

    monkeypatch.setattr(sub7.h5py, "File", boom_h5)
    assert sub7.load_reduced_mat(str(reduced_path)) == (None, None, None)


def test_internal_scalar_and_key_helpers_edge_cases():
    assert sub7._safe_get_scalar(None) is None
    assert sub7._normalize_key("Fs_amp-Rate") == "fsamprate"

    class NoKeys:
        pass

    assert sub7._first_matching_key(NoKeys(), ["fsamp"]) is None


def test_mat_loader_import_path_when_scipy_is_unavailable(monkeypatch):
    module_path = Path(sub7.__file__)
    spec = importlib.util.spec_from_file_location("_tmp_sub7_no_scipy", module_path)
    assert spec and spec.loader

    real_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "scipy" or name.startswith("scipy."):
            raise ImportError("simulated missing scipy")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.scipy_io is None


def test_extract_numeric_handles_dataset_errors_and_empty_values():
    class BadDataset:
        def __getitem__(self, _key):
            raise RuntimeError("cannot read")

    class EmptyDataset:
        def __getitem__(self, _key):
            return np.array([])

    assert sub7._extract_numeric_from_dataset(BadDataset(), {}) .size == 0
    assert sub7._extract_numeric_from_dataset(EmptyDataset(), {}) .size == 0


def test_extract_numeric_object_nested_reference_array_branch(tmp_path):
    mat_path = tmp_path / "nested_refs.mat"
    with h5py.File(mat_path, "w") as f:
        target = f.create_dataset("target", data=np.array([9.0]))
        refs = f.create_dataset("refs", (1, 1), dtype=h5py.ref_dtype)
        refs[0, 0] = target.ref

        class WrappedDataset:
            def __getitem__(self, _key):
                # Force arr.dtype == object and item is np.ndarray path.
                return np.array([np.array([refs[0, 0]], dtype=object)], dtype=object)

        out = sub7._extract_numeric_from_dataset(WrappedDataset(), f)
        assert np.allclose(out, np.array([9.0]))


def test_extract_numeric_object_invalid_refs_returns_empty(tmp_path):
    mat_path = tmp_path / "invalid_refs.mat"
    with h5py.File(mat_path, "w") as f:
        class WrappedDataset:
            def __getitem__(self, _key):
                return np.array([object()], dtype=object)

        out = sub7._extract_numeric_from_dataset(WrappedDataset(), f)
        assert out.size == 0


def test_mat_find_field_depth_cutoff_and_mat_to_numeric_failures():
    # Depth cutoff branch
    deep = {"a": {"b": {"c": {"d": {"e": {"field": 1}}}}}}
    assert sub7._mat_find_field(deep, "field", depth=5) is None

    class NoArray:
        def __array__(self, *_args, **_kwargs):
            raise TypeError("no array conversion")

    assert sub7._mat_to_numeric_array(NoArray()).size == 0
    assert sub7._mat_to_numeric_array(np.array(["x", "y"])) .size == 0
    assert sub7._mat_extract_numeric_vector({"other": 1}, "missing").size == 0


def test_load_event_data_scipy_fallback_failure_returns_empty(monkeypatch, tmp_path):
    event_path = tmp_path / "event_fail.mat"
    event_path.write_text("placeholder", encoding="utf-8")

    def boom_h5(*_args, **_kwargs):
        raise OSError("not hdf5")

    class FakeScipy:
        @staticmethod
        def loadmat(*_args, **_kwargs):
            raise ValueError("bad mat")

    monkeypatch.setattr(sub7.h5py, "File", boom_h5)
    monkeypatch.setattr(sub7, "scipy_io", FakeScipy)

    out = sub7.load_event_data(str(event_path))
    assert out["eventnum"].size == 0
    assert out["quality"].size == 0


def test_load_fsamp_event_and_meta_nonpositive_or_bad_fallback_return_none(monkeypatch, tmp_path):
    event_path = tmp_path / "event_nonpositive.mat"
    with h5py.File(event_path, "w") as f:
        event_group = f.create_group("event")
        event_group.create_dataset("fsamp", data=np.array([0.0]))

    meta_path = tmp_path / "meta_nonpositive.mat"
    with h5py.File(meta_path, "w") as f:
        meta_group = f.create_group("meta")
        meta_group.create_dataset("sampleRate", data=np.array([-1.0]))

    assert sub7.load_fsamp_from_event_mat(str(event_path)) is None
    assert sub7.load_fsamp_from_meta_mat(str(meta_path)) is None

    # Force scipy fallback exception branches too.
    fallback_path = tmp_path / "fallback_bad.mat"
    fallback_path.write_text("placeholder", encoding="utf-8")

    def boom_h5(*_args, **_kwargs):
        raise OSError("not hdf5")

    class FakeScipy:
        @staticmethod
        def loadmat(*_args, **_kwargs):
            raise RuntimeError("cannot parse mat")

    monkeypatch.setattr(sub7.h5py, "File", boom_h5)
    monkeypatch.setattr(sub7, "scipy_io", FakeScipy)

    assert sub7.load_fsamp_from_event_mat(str(fallback_path)) is None
    assert sub7.load_fsamp_from_meta_mat(str(fallback_path)) is None


@pytest.mark.parametrize(
    "value,expected",
    [
        (np.array([1, 2, 3]), np.array([1.0, 2.0, 3.0])),
        (np.array([[1], [2]]), np.array([1.0, 2.0])),
    ],
)
def test_mat_to_numeric_array_basic_numeric_paths(value, expected):
    out = sub7._mat_to_numeric_array(value)
    assert np.allclose(out, expected)
