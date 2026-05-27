"""Sequence designer GUI inspired by MATLAB SequenceDesigner controls."""

from __future__ import annotations

import json
import os
import random
import tkinter as tk
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from tkinter import filedialog

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


ALLOWED_BASES = {"A", "C", "G", "T"}
DISPLAY_53 = "5'- 3'"
DISPLAY_35 = "3'- 5'"
FEED_53 = "5'"
FEED_35 = "3'"
PORE_FORWARDS = "Forwards"
PORE_BACKWARDS = "Backwards"
QMER_MAP_FILENAMES = {
    "forwards_5p": "qmerdatabase_500mM150mM_forwards_phi29_5primefirst_phixhandclicked160603_withnoise.mat",
    "forwards_3p": "qmerdatabase_500mM100mM_forwards_pcrax_3primefirst_phiX174handalignment180731_withnoise.mat",
    "backwards_5p": "qmerdatabase_500mM150mM_backwards_phi29_5primefirst_phixhandclicked160603_withnoise.mat",
    "backwards_3p": "qmerdatabase_500mM50mM_backwards_3prime.mat",
    "hel308": "qmerdatabase_400mM400mM_forwards_hel308_5primefirst_DC170321_empirical_extraction.mat",
}
QMER_MAP_FIELDS = {
    "forwards_5p": "qmerdatabase",
    "forwards_3p": "qmerdatabase35map",
    "backwards_5p": "qmerdatabase",
    "backwards_3p": "qmerdb",
    "hel308": "qmerdatabase",
}
MAP_WARNING_TEXT = {
    0: "",
    1: "Warning: This map is not yet finished, using first draft with dimer-model in-fill",
    2: "Warning: hel308 only works with 5' to 3' feeding orientation and forwards pore orientation",
}
QMER_MAP_PATH_ENV = "NANOPORETHON_QMER_MAP_PATH"
QMER_DISABLE_AUTODETECT_ENV = "NANOPORETHON_DISABLE_QMER_AUTODETECT"


def sanitize_sequence(text: str) -> str:
    return "".join(base for base in text.upper() if base in ALLOWED_BASES)


def reverse_complement(sequence: str) -> str:
    return sequence.translate(str.maketrans("ACGT", "TGCA"))[::-1]


def _display_sequence(sequence: str, order: str) -> str:
    return sequence[::-1] if order == DISPLAY_35 else sequence


def _select_map_profile(*, feeding_orientation: str, pore_orientation: str, hel308: bool) -> tuple[str, int, int, str]:
    if hel308:
        warning = 0
        if pore_orientation != PORE_FORWARDS or feeding_orientation != FEED_53:
            warning = 2
        return "hel308", warning, 2, "Hel308 prediction forwards pore 5p feeding"

    if pore_orientation == PORE_FORWARDS and feeding_orientation == FEED_53:
        return "forwards_5p", 0, 1, "Forwards pore 5p feeding"
    if pore_orientation == PORE_FORWARDS and feeding_orientation == FEED_35:
        return "forwards_3p", 0, 1, "Forwards pore 3p feeding"
    if pore_orientation == PORE_BACKWARDS and feeding_orientation == FEED_53:
        return "backwards_5p", 0, 1, "Backwards pore 5p feeding"
    return "backwards_3p", 1, 1, "Backwards pore 3p feeding"


def _clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(upper, value))


def _canonical_index_from_display_position(sequence_length: int, display_position: int, order: str) -> int | None:
    if sequence_length <= 0:
        return None
    display_position = _clamp(display_position, 1, sequence_length + 1)
    if display_position == sequence_length + 1:
        return None
    return sequence_length - display_position if order == DISPLAY_35 else display_position - 1


def _insertion_index_from_display_position(sequence_length: int, display_position: int, order: str) -> int:
    display_position = _clamp(display_position, 1, sequence_length + 1)
    if order == DISPLAY_35:
        return 0 if display_position == sequence_length + 1 else sequence_length - display_position
    return sequence_length if display_position == sequence_length + 1 else display_position - 1


def _kmer_current(kmer: str, hel308: bool) -> float:
    base_current = {"A": 0.18, "C": 0.43, "G": 0.67, "T": 0.88, "N": 0.5}
    raw = 0.0
    for index, base in enumerate(kmer):
        raw += base_current.get(base, 0.5) * (1.0 + 0.08 * index)
    if "G" in kmer and "C" in kmer:
        raw += 0.03
    if hel308:
        raw += 0.04
    return raw


def _sliding_windows(sequence: str, window: int) -> list[str]:
    if not sequence:
        return []
    pad = max(1, window // 2)
    padded = "N" * pad + sequence + "N" * pad
    return [padded[index : index + window] for index in range(len(sequence))]


def _normalize_current(values: list[float]) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return arr
    minimum = float(np.min(arr))
    maximum = float(np.max(arr))
    if np.isclose(minimum, maximum):
        return np.full_like(arr, 0.5, dtype=float)
    arr = (arr - minimum) / (maximum - minimum)
    return 0.12 + 0.76 * arr


def _phase_shift_levels(levels: list[float] | np.ndarray, phase_shift: float) -> np.ndarray:
    arr = np.asarray(levels, dtype=float)
    if arr.size <= 1:
        return arr
    shift = float(np.clip(phase_shift, 0.0, 1.0))
    x = np.arange(arr.size, dtype=float)
    return np.interp(x, x - shift, arr, left=arr[0], right=arr[-1])


def _unwrap_singleton(value: object) -> object:
    current = value
    while isinstance(current, np.ndarray) and current.size == 1:
        current = current.item()
    return current


def _extract_field(container: object, field: str) -> object | None:
    target = _unwrap_singleton(container)
    if hasattr(target, field):
        return getattr(target, field)
    if isinstance(target, dict):
        return target.get(field)
    if isinstance(target, np.ndarray) and target.dtype.names and field in target.dtype.names:
        return target[field]
    return None


def _candidate_qmer_map_paths(profile_key: str) -> list[Path]:
    candidates: list[Path] = []
    filename = QMER_MAP_FILENAMES[profile_key]

    env_path = os.environ.get(QMER_MAP_PATH_ENV, "").strip()
    if env_path:
        env_candidate = Path(env_path).expanduser()
        if env_candidate.is_dir():
            candidates.append(env_candidate / filename)
        else:
            candidates.append(env_candidate)

    if os.environ.get(QMER_DISABLE_AUTODETECT_ENV, "").strip().lower() in {"1", "true", "yes", "on"}:
        return candidates

    repo_root = Path(__file__).resolve().parents[2]
    candidates.extend(
        [
            repo_root / "MATLABcode" / filename,
            repo_root / filename,
            Path.cwd() / filename,
            Path.home() / "Downloads" / "NanoporeRepository" / filename,
        ]
    )

    deduped: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        normalized = str(path.expanduser())
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(path)
    return deduped


@lru_cache(maxsize=1)
def _load_qmer_map(profile_key: str) -> tuple[int, dict[str, float], dict[str, float]] | None:
    if profile_key not in QMER_MAP_FILENAMES:
        return None

    try:
        from scipy import io as scipy_io  # type: ignore
    except Exception:
        return None

    field_name = QMER_MAP_FIELDS[profile_key]

    for path in _candidate_qmer_map_paths(profile_key):
        resolved = path.expanduser()
        if not resolved.exists() or not resolved.is_file():
            continue
        try:
            mat = scipy_io.loadmat(resolved, squeeze_me=True, struct_as_record=False)
        except Exception:
            continue

        payload = mat.get(field_name)
        if payload is None:
            payload = mat.get("qmerdatabase")
        if payload is None:
            for candidate_field in ("qmerdatabase", "qmerdatabase35map", "qmerdb"):
                payload = mat.get(candidate_field)
                if payload is not None:
                    break
        if payload is None:
            continue

        qmer_raw = _extract_field(payload, "qmer")
        mean_raw = _extract_field(payload, "mean")
        error_raw = _extract_field(payload, "error")
        if qmer_raw is None or mean_raw is None:
            continue

        qmers = [str(item) for item in np.asarray(_unwrap_singleton(qmer_raw), dtype=object).ravel().tolist()]
        if not qmers:
            continue

        mean_arr = np.asarray(_unwrap_singleton(mean_raw), dtype=float)
        if mean_arr.ndim == 1:
            means = mean_arr
        elif mean_arr.ndim >= 2:
            means = mean_arr[0]
        else:
            continue

        error_lookup: dict[str, float] = {}
        if error_raw is not None:
            err_arr = np.asarray(_unwrap_singleton(error_raw), dtype=float)
            if err_arr.ndim == 1:
                errs = err_arr
            elif err_arr.ndim >= 2:
                errs = err_arr[0]
            else:
                errs = np.asarray([], dtype=float)
            for qmer, val in zip(qmers, errs.tolist()):
                error_lookup[qmer] = float(val)

        if len(qmers) != len(means):
            continue

        level_lookup = {qmer: float(level) for qmer, level in zip(qmers, means.tolist())}
        kmer_size = len(qmers[0])
        if kmer_size <= 0:
            continue
        return kmer_size, level_lookup, error_lookup

    return None


def _qmer_lookup_levels(sequence: str, profile_key: str) -> np.ndarray | None:
    loaded = _load_qmer_map(profile_key)
    if loaded is None:
        return None

    kmer_size, lookup, _errors = loaded
    if len(sequence) < kmer_size:
        return np.asarray([], dtype=float)

    kmers = [sequence[index : index + kmer_size] for index in range(len(sequence) - kmer_size + 1)]
    values: list[float] = []
    for kmer in kmers:
        if kmer not in lookup:
            return None
        values.append(lookup[kmer])
    return np.asarray(values, dtype=float)


def build_predicted_currents(sequence: str, *, display_order: str, feeding_orientation: str, pore_orientation: str, hel308: bool, phase_shift: float) -> np.ndarray:
    sequence = sanitize_sequence(sequence)
    if not sequence:
        return np.asarray([], dtype=float)

    working = _display_sequence(sequence, display_order)
    if feeding_orientation == FEED_35:
        working = working[::-1]
    if pore_orientation == PORE_BACKWARDS:
        working = reverse_complement(working)

    profile_key, _warning, _numstep, _details = _select_map_profile(
        feeding_orientation=feeding_orientation,
        pore_orientation=pore_orientation,
        hel308=hel308,
    )

    mapped = _qmer_lookup_levels(working, profile_key)
    if mapped is not None:
        return _phase_shift_levels(mapped, phase_shift)

    # Synthetic fallback when q-mer map is unavailable.
    window = 6 if hel308 else 5
    raw = [_kmer_current(kmer, hel308) for kmer in _sliding_windows(working, window)]
    return _phase_shift_levels(_normalize_current(raw), phase_shift)


def prediction_context(*, feeding_orientation: str, pore_orientation: str, hel308: bool) -> dict[str, object]:
    profile_key, warning_code, numstep, details = _select_map_profile(
        feeding_orientation=feeding_orientation,
        pore_orientation=pore_orientation,
        hel308=hel308,
    )
    return {
        "profile_key": profile_key,
        "map_filename": QMER_MAP_FILENAMES[profile_key],
        "map_field": QMER_MAP_FIELDS[profile_key],
        "warning_code": warning_code,
        "warning_text": MAP_WARNING_TEXT[warning_code],
        "numstep": numstep,
        "details": details,
    }


@dataclass
class SequenceDesignerModel:
    sequence: str = ""
    editing_position: int = 1
    feeding_orientation: str = FEED_53
    pore_orientation: str = PORE_FORWARDS
    display_order: str = DISPLAY_53
    hel308: bool = False
    phase_shift: float = 0.0

    def sanitized_sequence(self) -> str:
        return sanitize_sequence(self.sequence)

    def display_sequence(self) -> str:
        return _display_sequence(self.sanitized_sequence(), self.display_order)

    def displayed_length(self) -> int:
        return len(self.sanitized_sequence())

    def max_edit_position(self) -> int:
        return max(1, self.displayed_length() + 1)

    def clamp_editing_position(self) -> int:
        self.editing_position = _clamp(self.editing_position, 1, self.max_edit_position())
        return self.editing_position

    def set_sequence(self, text: str) -> None:
        self.sequence = sanitize_sequence(text)
        self.clamp_editing_position()

    def move_edit_position(self, position: int) -> None:
        self.editing_position = _clamp(int(position), 1, self.max_edit_position())

    def selected_display_index(self) -> int | None:
        return _canonical_index_from_display_position(self.displayed_length(), self.clamp_editing_position(), self.display_order)

    def insertion_index(self) -> int:
        return _insertion_index_from_display_position(self.displayed_length(), self.clamp_editing_position(), self.display_order)

    def mutate_selected_base(self, new_base: str) -> None:
        base = new_base.upper()
        if base not in ALLOWED_BASES:
            raise ValueError(f"Unsupported nucleotide: {new_base!r}")
        sequence = self.sanitized_sequence()
        insert_index = self.insertion_index()
        selected_index = self.selected_display_index()
        if selected_index is None or insert_index == len(sequence):
            if self.display_order == DISPLAY_35 and selected_index is None:
                self.sequence = base + sequence
            else:
                self.sequence = sequence[:insert_index] + base + sequence[insert_index:]
        else:
            chars = list(sequence)
            chars[selected_index] = base
            self.sequence = "".join(chars)
        self.clamp_editing_position()

    def randomize_selected_base(self) -> None:
        self.mutate_selected_base(random.choice(sorted(ALLOWED_BASES)))

    def delete_selected_base(self) -> None:
        sequence = self.sanitized_sequence()
        if not sequence:
            return
        insert_index = self.insertion_index()
        selected_index = self.selected_display_index()
        if selected_index is None or insert_index == len(sequence):
            self.sequence = sequence[:-1] if self.display_order == DISPLAY_53 else sequence[1:]
        else:
            chars = list(sequence)
            del chars[selected_index]
            self.sequence = "".join(chars)
        self.clamp_editing_position()

    def export_payload(self) -> dict[str, object]:
        return {
            "sequence": self.sanitized_sequence(),
            "display_sequence": self.display_sequence(),
            "levels": build_predicted_currents(
                self.sequence,
                display_order=self.display_order,
                feeding_orientation=self.feeding_orientation,
                pore_orientation=self.pore_orientation,
                hel308=self.hel308,
                phase_shift=self.phase_shift,
            ).tolist(),
        }


class SequenceDesignerGui:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Sequence Designer")
        self.model = SequenceDesignerModel()
        self.sequence_var = tk.StringVar(value="")
        self.editing_var = tk.IntVar(value=1)
        self.feeding_orientation_var = tk.StringVar(value=FEED_53)
        self.pore_orientation_var = tk.StringVar(value=PORE_FORWARDS)
        self.display_order_var = tk.StringVar(value=DISPLAY_53)
        self.hel308_var = tk.BooleanVar(value=False)
        self.phase_shift_var = tk.DoubleVar(value=0.0)
        self.status_var = tk.StringVar(value="Ready")
        self.sequence_preview_var = tk.StringVar(value="Sequence (displayed order): —")
        self.editing_label_var = tk.StringVar(value="Editing: position 1 of 2")
        self._build_ui()
        self.updateFig()

    def _build_ui(self) -> None:
        outer = tk.Frame(self.root, padx=12, pady=12)
        outer.pack(fill=tk.BOTH, expand=True)
        controls = tk.Frame(outer)
        controls.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 14))
        seq_frame = tk.LabelFrame(controls, text="Sequence 5'-")
        seq_frame.pack(fill=tk.X, pady=(0, 8))
        self.sequence_entry = tk.Entry(seq_frame, textvariable=self.sequence_var, width=34)
        self.sequence_entry.pack(fill=tk.X, padx=8, pady=8)
        self.sequence_entry.bind("<Return>", self.Sequence5EditFieldValueChanged)
        self.sequence_entry.bind("<FocusOut>", self.Sequence5EditFieldValueChanged)
        edit_frame = tk.LabelFrame(controls, text="Editing")
        edit_frame.pack(fill=tk.X, pady=(0, 8))
        self.editing_scale = tk.Scale(
            edit_frame,
            from_=1,
            to=2,
            orient=tk.HORIZONTAL,
            resolution=1,
            variable=self.editing_var,
            command=self.EditingSliderValueChanged,
            length=260,
        )
        self.editing_scale.pack(fill=tk.X, padx=8, pady=(8, 2))
        tk.Label(edit_frame, textvariable=self.editing_label_var, anchor="w").pack(fill=tk.X, padx=8, pady=(0, 8))
        tk.Label(controls, text="Select nucleotide 'N'", anchor="w").pack(fill=tk.X, pady=(0, 4))
        buttons = tk.Frame(controls)
        buttons.pack(fill=tk.X, pady=(0, 8))
        for base in ("A", "C", "G", "T"):
            tk.Button(buttons, text=base, width=5, command=lambda b=base: self._mutate_and_refresh(b)).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(buttons, text="Random", width=7, command=self.RandomButtonPushed).pack(side=tk.LEFT, padx=(4, 4))
        tk.Button(buttons, text="Delete", width=7, command=self.DeleteButtonPushed).pack(side=tk.LEFT)
        orient = tk.LabelFrame(controls, text="Orientation controls")
        orient.pack(fill=tk.X, pady=(0, 8))
        self._option_row(orient, "Feeding orientation", self.feeding_orientation_var, [FEED_53, FEED_35])
        self._option_row(orient, "Pore orientation", self.pore_orientation_var, [PORE_FORWARDS, PORE_BACKWARDS])
        self._option_row(orient, "Display order", self.display_order_var, [DISPLAY_53, DISPLAY_35])
        tk.Checkbutton(orient, text="Hel308", variable=self.hel308_var, command=self.Hel308SwitchValueChanged).pack(anchor="w", padx=8, pady=(4, 4))
        phase = tk.LabelFrame(controls, text="Phase Shift")
        phase.pack(fill=tk.X, pady=(0, 8))
        self.phase_scale = tk.Scale(
            phase,
            from_=0.0,
            to=1.0,
            orient=tk.HORIZONTAL,
            resolution=0.01,
            variable=self.phase_shift_var,
            command=self.PhaseShiftSliderValueChanged,
            length=260,
        )
        self.phase_scale.pack(fill=tk.X, padx=8, pady=8)
        action = tk.Frame(controls)
        action.pack(fill=tk.X, pady=(0, 8))
        tk.Button(action, text="Save Figure", command=self.SaveFigureButtonPushed).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(action, text="Export Levels", command=self.ExportLevelsButtonPushed).pack(side=tk.LEFT)
        tk.Label(controls, textvariable=self.status_var, anchor="w", wraplength=330, fg="#444").pack(fill=tk.X, pady=(4, 0))
        plot = tk.Frame(outer)
        plot.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        tk.Label(plot, text="Predicted currents", font=("TkDefaultFont", 13, "bold"), anchor="w").pack(fill=tk.X)
        self.figure = Figure(figsize=(8.0, 5.8), dpi=100, tight_layout=True)
        self.axes = self.figure.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.figure, master=plot)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        tk.Label(plot, textvariable=self.sequence_preview_var, anchor="w", wraplength=760).pack(fill=tk.X, pady=(8, 0))

    def _option_row(self, parent: tk.Widget, label: str, variable: tk.StringVar, values: list[str]) -> None:
        row = tk.Frame(parent)
        row.pack(fill=tk.X, padx=8, pady=(4, 0))
        tk.Label(row, text=label, anchor="w").pack(side=tk.LEFT)
        tk.OptionMenu(row, variable, *values, command=lambda _value: self.updateFig()).pack(side=tk.RIGHT)

    def _sync_from_widgets(self) -> None:
        self.model.sequence = self.sequence_var.get()
        self.model.editing_position = int(self.editing_var.get())
        self.model.feeding_orientation = self.feeding_orientation_var.get()
        self.model.pore_orientation = self.pore_orientation_var.get()
        self.model.display_order = self.display_order_var.get()
        self.model.hel308 = bool(self.hel308_var.get())
        self.model.phase_shift = float(self.phase_shift_var.get())
        self.model.clamp_editing_position()
        self.editing_var.set(self.model.editing_position)

    def _sync_widgets_from_model(self) -> None:
        self.sequence_var.set(self.model.sanitized_sequence())
        self.editing_var.set(self.model.clamp_editing_position())
        self.feeding_orientation_var.set(self.model.feeding_orientation)
        self.pore_orientation_var.set(self.model.pore_orientation)
        self.display_order_var.set(self.model.display_order)
        self.hel308_var.set(bool(self.model.hel308))
        self.phase_shift_var.set(float(self.model.phase_shift))

    def _refresh_status(self) -> None:
        sequence = self.model.sanitized_sequence()
        context = prediction_context(
            feeding_orientation=self.model.feeding_orientation,
            pore_orientation=self.model.pore_orientation,
            hel308=self.model.hel308,
        )
        levels = build_predicted_currents(
            sequence,
            display_order=self.model.display_order,
            feeding_orientation=self.model.feeding_orientation,
            pore_orientation=self.model.pore_orientation,
            hel308=self.model.hel308,
            phase_shift=self.model.phase_shift,
        )
        self.editing_label_var.set(f"Editing: position {self.model.clamp_editing_position()} of {self.model.max_edit_position()}")
        self.sequence_preview_var.set(f"Sequence (displayed order): {self.model.display_sequence() or '—'}")
        status = (
            f"Length={len(sequence)} | Editing={self.model.editing_position} | Levels={len(levels)} | "
            f"Feeding={self.model.feeding_orientation} | Pore={self.model.pore_orientation} | "
            f"Map={context['map_filename']}"
        )
        warning_text = str(context["warning_text"]).strip()
        if warning_text:
            status = f"{status} | {warning_text}"
        self.status_var.set(status)
        self.editing_scale.configure(from_=1, to=self.model.max_edit_position())
        self.editing_scale.configure(state=tk.DISABLED if self.model.max_edit_position() <= 1 else tk.NORMAL)
        self.editing_scale.set(self.model.clamp_editing_position())

    def _mutate_and_refresh(self, base: str) -> None:
        self._sync_from_widgets()
        self.model.mutate_selected_base(base)
        self._sync_widgets_from_model()
        self.updateFig()

    def updateFig(self) -> None:
        self._sync_from_widgets()
        levels = build_predicted_currents(
            self.model.sequence,
            display_order=self.model.display_order,
            feeding_orientation=self.model.feeding_orientation,
            pore_orientation=self.model.pore_orientation,
            hel308=self.model.hel308,
            phase_shift=self.model.phase_shift,
        )
        self.axes.clear()
        self.axes.set_title("Predicted currents", loc="left")
        self.axes.set_xlabel("Sequence position")
        self.axes.set_ylabel("Normalized current")
        if levels.size == 0:
            self.axes.text(0.5, 0.5, "Enter a DNA sequence to generate a trace", ha="center", va="center", transform=self.axes.transAxes)
            self.axes.set_xlim(0, 1)
            self.axes.set_ylim(0, 1)
        else:
            x = np.arange(1, levels.size + 1)
            self.axes.plot(x, levels, color="#1f4aa8", linewidth=2.0, marker="o", markersize=3.5)
            self.axes.axhline(float(np.min(levels)), color="#888", linestyle="--", linewidth=1.0)
            self.axes.axhline(float(np.max(levels)), color="#888", linestyle="--", linewidth=1.0)
            self.axes.set_xlim(1, max(1, levels.size))
            self.axes.set_ylim(0.0, 1.0)
            self.axes.text(0.5, -0.16, self.model.display_sequence(), ha="center", va="top", transform=self.axes.transAxes, fontsize=10, family="monospace")
        self.axes.grid(True, alpha=0.18)
        self.canvas.draw_idle()
        self._refresh_status()

    def Sequence5EditFieldValueChanged(self, event: tk.Event | None = None) -> None:
        del event
        self._sync_from_widgets()
        self.model.set_sequence(self.sequence_var.get())
        self._sync_widgets_from_model()
        self.updateFig()

    def EditingSliderValueChanged(self, value: str | float | int | None = None) -> None:
        if value is not None:
            self.editing_var.set(int(float(value)))
        self._sync_from_widgets()
        self.model.move_edit_position(self.editing_var.get())
        self._sync_widgets_from_model()
        self.updateFig()

    def PhaseShiftSliderValueChanged(self, value: str | float | int | None = None) -> None:
        if value is not None:
            self.phase_shift_var.set(float(value))
        self._sync_from_widgets()
        self.updateFig()

    def FeedingorientationSwitchValueChanged(self, *_args: object) -> None:
        self._sync_from_widgets()
        self.updateFig()

    def PoreorientationSwitchValueChanged(self, *_args: object) -> None:
        self._sync_from_widgets()
        self.updateFig()

    def DisplayorderSwitchValueChanged(self, *_args: object) -> None:
        self._sync_from_widgets()
        self.updateFig()

    def Hel308SwitchValueChanged(self) -> None:
        self._sync_from_widgets()
        self.updateFig()

    def AButtonPushed(self) -> None:
        self._mutate_and_refresh("A")

    def CButtonPushed(self) -> None:
        self._mutate_and_refresh("C")

    def GButtonPushed(self) -> None:
        self._mutate_and_refresh("G")

    def TButtonPushed(self) -> None:
        self._mutate_and_refresh("T")

    def RandomButtonPushed(self) -> None:
        self._mutate_and_refresh(random.choice(sorted(ALLOWED_BASES)))

    def DeleteButtonPushed(self) -> None:
        self._sync_from_widgets()
        self.model.delete_selected_base()
        self._sync_widgets_from_model()
        self.updateFig()

    def SaveFigureButtonPushed(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Save predicted currents figure",
            defaultextension=".png",
            filetypes=[("PNG image", "*.png"), ("PDF file", "*.pdf"), ("SVG file", "*.svg"), ("All files", "*.*")],
        )
        if path:
            self.figure.savefig(Path(path), dpi=160)

    def ExportLevelsButtonPushed(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Export predicted levels",
            defaultextension=".json",
            filetypes=[("JSON file", "*.json"), ("All files", "*.*")],
        )
        if path:
            Path(path).write_text(json.dumps(self.model.export_payload(), indent=2), encoding="utf-8")

    def run(self) -> None:
        self.root.mainloop()


def run_gui() -> None:
    root = tk.Tk()
    SequenceDesignerGui(root).run()


if __name__ == "__main__":
    run_gui()
