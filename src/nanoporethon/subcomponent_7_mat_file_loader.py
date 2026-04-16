"""
Subcomponent 5a: MAT File Loader
Description: Handles loading and parsing MAT files (reduced.mat, event.mat, meta.mat).
Provides robust extraction of data with fallback strategies for different MAT file formats.
Extracted from SC5 to be reusable for other components.
"""

import os
from typing import Dict, Optional, List
import numpy as np
import h5py

try:
    from scipy import io as scipy_io
except Exception:
    scipy_io = None


# Data extraction helpers

def _safe_get_scalar(dataset_or_value) -> Optional[float]:
    """Safely extract a scalar float from HDF5 scalar/array-like values."""
    if dataset_or_value is None:
        return None
    try:
        value = dataset_or_value[()]
        arr = np.array(value).flatten()
        if arr.size == 0:
            return None
        return float(arr[0])
    except Exception:
        try:
            arr = np.array(dataset_or_value).flatten()
            if arr.size == 0:
                return None
            return float(arr[0])
        except Exception:
            return None


def _normalize_key(key: str) -> str:
    """Normalize field names for robust matching across naming variants."""
    return ''.join(ch for ch in str(key).lower() if ch.isalnum())


def _first_matching_key(container, candidates: List[str]) -> Optional[str]:
    """Return first key in container matching any candidate after normalization."""
    if not hasattr(container, 'keys'):
        return None
    normalized_candidates = {_normalize_key(c) for c in candidates}
    for key in container.keys():
        if _normalize_key(key) in normalized_candidates:
            return key
    return None


def _extract_numeric_from_dataset(dataset, h5file) -> np.ndarray:
    """Extract numeric values from an HDF5 dataset, resolving object refs when needed."""
    try:
        value = dataset[()]
    except Exception:
        return np.array([])

    arr = np.array(value)
    if arr.size == 0:
        return np.array([])

    # MATLAB v7.3 struct fields are often object references.
    if arr.dtype == object:
        extracted = []
        for ref in arr.flatten():
            try:
                if isinstance(ref, np.ndarray):
                    for sub in ref.flatten():
                        try:
                            obj = h5file[sub]
                            obj_val = np.array(obj[()]).flatten()
                            if obj_val.size > 0:
                                extracted.extend(obj_val.tolist())
                        except Exception:
                            continue
                    continue
                if not ref:
                    continue
                obj = h5file[ref]
                obj_val = np.array(obj[()]).flatten()
                if obj_val.size > 0:
                    extracted.extend(obj_val.tolist())
            except Exception:
                continue
        if extracted:
            return np.array(extracted, dtype=float).flatten()
        return np.array([])

    try:
        return arr.astype(float).flatten()
    except Exception:
        return np.array([])


def _find_dataset_case_insensitive(group, target_key: str):
    """Find a dataset by key (case-insensitive), searching recursively."""
    target = _normalize_key(target_key)

    if not hasattr(group, 'keys'):
        return None

    # Direct children first.
    for key in group.keys():
        if _normalize_key(key) == target:
            return group[key]

    # Then recurse into nested groups.
    for key in group.keys():
        child = group[key]
        if isinstance(child, (h5py.Group, dict)):
            found = _find_dataset_case_insensitive(child, target_key)
            if found is not None:
                return found
    return None


def _load_event_vector(h5file, root_group, key: str) -> np.ndarray:
    """Load a vector from event.mat by key with robust fallback behavior."""
    ds = _find_dataset_case_insensitive(root_group, key)
    if ds is None:
        return np.array([])

    # Fast path for plain arrays/dict-backed test doubles.
    if not isinstance(ds, h5py.Dataset):
        try:
            arr = np.array(ds).astype(float).flatten()
            return arr if arr.size > 0 else np.array([])
        except Exception:
            try:
                arr = np.array(ds[()]).astype(float).flatten()
                return arr if arr.size > 0 else np.array([])
            except Exception:
                return np.array([])

    return _extract_numeric_from_dataset(ds, h5file)


# MATLAB structure parsing (for scipy.io)

def _mat_iter_children(obj):
    """Yield child objects for recursive MATLAB-structure field search."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and not k.startswith('__'):
                yield k, v
        return

    if isinstance(obj, np.ndarray):
        for item in obj.flatten():
            yield None, item
        return

    # MATLAB struct_as_record=False objects expose fields as attributes.
    if hasattr(obj, '__dict__'):
        for k, v in vars(obj).items():
            if isinstance(k, str) and not k.startswith('_'):
                yield k, v


def _mat_find_field(obj, field_name: str, depth: int = 0):
    """Recursively find a field in MATLAB-loaded structures (case-insensitive)."""
    if obj is None or depth > 4:
        return None

    target = field_name.lower()
    for k, v in _mat_iter_children(obj):
        if isinstance(k, str) and k.lower() == target:
            return v

    for _k, v in _mat_iter_children(obj):
        found = _mat_find_field(v, field_name, depth + 1)
        if found is not None:
            return found
    return None


def _mat_to_numeric_array(value) -> np.ndarray:
    """Convert MATLAB-loaded value to a flat numeric numpy array when possible."""
    if value is None:
        return np.array([])

    try:
        arr = np.array(value)
    except Exception:
        return np.array([])

    if arr.size == 0:
        return np.array([])

    if arr.dtype == object:
        vals = []
        for item in arr.flatten():
            sub = _mat_to_numeric_array(item)
            if sub.size > 0:
                vals.extend(sub.tolist())
        return np.array(vals, dtype=float) if vals else np.array([])

    try:
        return arr.astype(float).flatten()
    except Exception:
        return np.array([])


def _mat_extract_numeric_vector(root_obj, field_name: str) -> np.ndarray:
    """Extract a numeric vector for a field from scipy-loaded MATLAB content."""
    value = _mat_find_field(root_obj, field_name)
    return _mat_to_numeric_array(value)


# Import scipy for fallback loading
try:
    from scipy import io as scipy_io
except Exception:
    scipy_io = None


# Public API: Loading functions

def load_reduced_mat(mat_file_path: str) -> tuple:
    """
    Load data from reduced.mat file.
    
    Args:
        mat_file_path (str): Path to the reduced.mat file.
    
    Returns:
        tuple: (data, pt, downsample_factor) where data and pt are numpy arrays,
               or (None, None, None) if loading fails.
    """
    if not os.path.exists(mat_file_path):
        return None, None, None
    
    try:
        with h5py.File(mat_file_path, 'r') as f:
            if 'reduced' not in f:
                return None, None, None
            
            reduced_group = f['reduced']
            if 'data' not in reduced_group or 'pt' not in reduced_group:
                return None, None, None
            
            data = np.array(reduced_group['data'][:]).flatten()
            pt = np.array(reduced_group['pt'][:]).flatten()
            
            # Detect downsample factor
            candidate_keys = ['downsampleFactor', 'downsample', 'dwnspl', 'ds', 'dsFactor']
            downsample_factor = 1.0
            for key in candidate_keys:
                if key in reduced_group:
                    value = _safe_get_scalar(reduced_group.get(key))
                    if value and value > 0:
                        downsample_factor = float(value)
                        break
            
            return data, pt, downsample_factor
    except Exception:
        return None, None, None


def load_event_data(event_file_path: str) -> Dict[str, np.ndarray]:
    """
    Load event metadata from event.mat.
    
    Args:
        event_file_path (str): Path to the event.mat file.
    
    Returns:
        Dict[str, np.ndarray]: Dictionary with keys like 'eventnum', 'eventStartPt', etc.
                              Returns empty dict-like object with all keys set to empty arrays if load fails.
    """
    empty = {
        'eventnum': np.array([]),
        'eventStartPt': np.array([]),
        'eventEndPt': np.array([]),
        'eventStartNdx': np.array([]),
        'eventEndNdx': np.array([]),
        'quality': np.array([]),
        'localIOS': np.array([]),
    }

    if not os.path.exists(event_file_path):
        return empty

    # First attempt: MATLAB v7.3 (HDF5-backed) via h5py.
    try:
        with h5py.File(event_file_path, 'r') as f:
            event_group = f['event'] if 'event' in f else f
            out = {
                'eventnum': _load_event_vector(f, event_group, 'eventnum'),
                'eventStartPt': _load_event_vector(f, event_group, 'eventStartPt'),
                'eventEndPt': _load_event_vector(f, event_group, 'eventEndPt'),
                'eventStartNdx': _load_event_vector(f, event_group, 'eventStartNdx'),
                'eventEndNdx': _load_event_vector(f, event_group, 'eventEndNdx'),
                'quality': _load_event_vector(f, event_group, 'quality'),
                'localIOS': _load_event_vector(f, event_group, 'localIOS'),
            }
            return out
    except Exception:
        pass

    # Fallback: MATLAB v5/v7 (non-HDF5) via scipy.io.loadmat.
    if scipy_io is None:
        return empty

    try:
        mat = scipy_io.loadmat(event_file_path, squeeze_me=True, struct_as_record=False)
        event_obj = mat.get('event', mat)
        out = {
            'eventnum': _mat_extract_numeric_vector(event_obj, 'eventnum'),
            'eventStartPt': _mat_extract_numeric_vector(event_obj, 'eventStartPt'),
            'eventEndPt': _mat_extract_numeric_vector(event_obj, 'eventEndPt'),
            'eventStartNdx': _mat_extract_numeric_vector(event_obj, 'eventStartNdx'),
            'eventEndNdx': _mat_extract_numeric_vector(event_obj, 'eventEndNdx'),
            'quality': _mat_extract_numeric_vector(event_obj, 'quality'),
            'localIOS': _mat_extract_numeric_vector(event_obj, 'localIOS'),
        }
        return out
    except Exception:
        return empty


def load_fsamp_from_event_mat(event_file_path: str) -> Optional[float]:
    """
    Extract sampling frequency from event.mat.
    
    Args:
        event_file_path (str): Path to the event.mat file.
    
    Returns:
        Optional[float]: Sampling frequency in Hz, or None if not found or invalid.
    """
    if not os.path.exists(event_file_path):
        return None

    candidate_keys = ['fsamp', 'Fsamp', 'f_samp', 'samplingFrequency', 'sampleRate', 'fs', 'Fs']

    try:
        with h5py.File(event_file_path, 'r') as f:
            groups_to_check = []
            if 'event' in f:
                groups_to_check.append(f['event'])
            groups_to_check.append(f)

            for group in groups_to_check:
                if not hasattr(group, 'keys'):
                    continue
                matched_key = _first_matching_key(group, candidate_keys)
                if matched_key is not None:
                    obj = group[matched_key]
                    if isinstance(obj, h5py.Dataset):
                        vals = _extract_numeric_from_dataset(obj, f)
                        value = float(vals[0]) if vals.size > 0 else None
                    else:
                        try:
                            value = float(np.array(obj).flatten()[0])
                        except Exception:
                            value = _safe_get_scalar(obj)
                    if value and value > 0:
                        return float(value)

            # Fallback: one-level nested groups.
            for group in groups_to_check:
                if not hasattr(group, 'keys'):
                    continue
                for child_key in group.keys():
                    child = group[child_key]
                    if isinstance(child, (h5py.Group, dict)):
                        if not hasattr(child, 'keys'):
                            continue
                        matched_key = _first_matching_key(child, candidate_keys)
                        if matched_key is not None:
                            obj = child[matched_key]
                            if isinstance(obj, h5py.Dataset):
                                vals = _extract_numeric_from_dataset(obj, f)
                                value = float(vals[0]) if vals.size > 0 else None
                            else:
                                try:
                                    value = float(np.array(obj).flatten()[0])
                                except Exception:
                                    value = _safe_get_scalar(obj)
                            if value and value > 0:
                                return float(value)
    except Exception:
        pass

    # Fallback for non-HDF5 MAT files.
    if scipy_io is not None:
        try:
            mat = scipy_io.loadmat(event_file_path, squeeze_me=True, struct_as_record=False)
            event_obj = mat.get('event', mat)
            for key in candidate_keys:
                vals = _mat_extract_numeric_vector(event_obj, key)
                if vals.size > 0 and float(vals[0]) > 0:
                    return float(vals[0])
        except Exception:
            pass

    return None


def load_fsamp_from_meta_mat(meta_file_path: str) -> Optional[float]:
    """
    Extract sampling frequency from meta.mat.
    
    Args:
        meta_file_path (str): Path to the meta.mat file.
    
    Returns:
        Optional[float]: Sampling frequency in Hz, or None if not found or invalid.
    """
    if not os.path.exists(meta_file_path):
        return None

    candidate_keys = ['fsamp', 'Fsamp', 'f_samp', 'samplingFrequency', 'sampleRate', 'fs', 'Fs']

    try:
        with h5py.File(meta_file_path, 'r') as f:
            groups_to_check = []
            if 'meta' in f:
                groups_to_check.append(f['meta'])
            groups_to_check.append(f)

            for group in groups_to_check:
                if not hasattr(group, 'keys'):
                    continue
                matched_key = _first_matching_key(group, candidate_keys)
                if matched_key is not None:
                    obj = group[matched_key]
                    if isinstance(obj, h5py.Dataset):
                        vals = _extract_numeric_from_dataset(obj, f)
                        value = float(vals[0]) if vals.size > 0 else None
                    else:
                        try:
                            value = float(np.array(obj).flatten()[0])
                        except Exception:
                            value = _safe_get_scalar(obj)
                    if value and value > 0:
                        return float(value)

            # Fallback: one-level nested groups.
            for group in groups_to_check:
                if not hasattr(group, 'keys'):
                    continue
                for child_key in group.keys():
                    child = group[child_key]
                    if isinstance(child, (h5py.Group, dict)):
                        if not hasattr(child, 'keys'):
                            continue
                        matched_key = _first_matching_key(child, candidate_keys)
                        if matched_key is not None:
                            obj = child[matched_key]
                            if isinstance(obj, h5py.Dataset):
                                vals = _extract_numeric_from_dataset(obj, f)
                                value = float(vals[0]) if vals.size > 0 else None
                            else:
                                try:
                                    value = float(np.array(obj).flatten()[0])
                                except Exception:
                                    value = _safe_get_scalar(obj)
                            if value and value > 0:
                                return float(value)
    except Exception:
        pass

    # Fallback for non-HDF5 MAT files.
    if scipy_io is not None:
        try:
            mat = scipy_io.loadmat(meta_file_path, squeeze_me=True, struct_as_record=False)
            meta_obj = mat.get('meta', mat)
            for key in candidate_keys:
                vals = _mat_extract_numeric_vector(meta_obj, key)
                if vals.size > 0 and float(vals[0]) > 0:
                    return float(vals[0])
        except Exception:
            pass

    return None
