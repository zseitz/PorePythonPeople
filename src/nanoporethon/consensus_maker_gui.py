"""Consensus signal GUI inspired by MATLAB ``consensusMaker.m`` workflow.

This module provides a lightweight, deterministic approximation for expected
nanopore consensus current levels from an input DNA sequence.
"""

from __future__ import annotations

import hashlib
import tkinter as tk
from tkinter import messagebox, scrolledtext

import matplotlib.pyplot as plt
import numpy as np


def sanitize_sequence(sequence: str) -> str:
    """Normalize and validate a DNA sequence.

    Returns an uppercase A/C/G/T-only string, or raises ValueError.
    """
    normalized = "".join(sequence.upper().split())
    if not normalized:
        raise ValueError("DNA sequence is empty.")

    invalid = sorted({base for base in normalized if base not in {"A", "C", "G", "T"}})
    if invalid:
        raise ValueError(
            "DNA sequence contains invalid characters: " + ", ".join(invalid)
        )
    return normalized


def _kmer_level(kmer: str) -> float:
    """Map a k-mer to a deterministic normalized current level in [0.2, 0.9]."""
    digest = hashlib.sha256(kmer.encode("utf-8")).digest()
    value = int.from_bytes(digest[:4], byteorder="big", signed=False)
    unit = value / float(2**32 - 1)
    return 0.2 + 0.7 * unit


def consensus_signal(sequence: str, kmer_size: int = 5) -> np.ndarray:
    """Compute expected consensus signal levels for a DNA sequence.

    The returned vector is one level per k-mer window.
    """
    seq = sanitize_sequence(sequence)
    if kmer_size < 1:
        raise ValueError("kmer_size must be >= 1")
    if len(seq) < kmer_size:
        raise ValueError(
            f"DNA sequence length ({len(seq)}) must be at least kmer_size ({kmer_size})."
        )

    levels = [_kmer_level(seq[i : i + kmer_size]) for i in range(len(seq) - kmer_size + 1)]
    return np.asarray(levels, dtype=float)


class ConsensusMakerGUI:
    """Simple GUI to estimate expected nanopore consensus signal from sequence."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Consensus Maker")
        self.root.geometry("880x520")

        main = tk.Frame(root, padx=10, pady=10)
        main.pack(fill=tk.BOTH, expand=True)

        tk.Label(main, text="DNA sequence (A/C/G/T):", anchor="w").pack(fill=tk.X)
        self.sequence_box = scrolledtext.ScrolledText(main, height=7, wrap=tk.WORD)
        self.sequence_box.pack(fill=tk.BOTH, expand=False, pady=(4, 8))

        controls = tk.Frame(main)
        controls.pack(fill=tk.X)

        tk.Label(controls, text="k-mer size:").pack(side=tk.LEFT)
        self.kmer_var = tk.StringVar(value="5")
        tk.Entry(controls, textvariable=self.kmer_var, width=6).pack(side=tk.LEFT, padx=(6, 12))

        tk.Button(
            controls,
            text="Generate Consensus Signal",
            command=self._generate,
        ).pack(side=tk.LEFT)

        self.summary_var = tk.StringVar(value="Enter a DNA sequence and click Generate.")
        tk.Label(main, textvariable=self.summary_var, anchor="w", fg="#333333").pack(fill=tk.X, pady=(10, 0))

    def _generate(self) -> None:
        raw_sequence = self.sequence_box.get("1.0", tk.END)
        try:
            kmer_size = int(self.kmer_var.get().strip())
            signal = consensus_signal(raw_sequence, kmer_size=kmer_size)
        except ValueError as exc:
            messagebox.showerror("Invalid input", str(exc))
            return

        self._plot_signal(signal, kmer_size)

    def _plot_signal(self, signal: np.ndarray, kmer_size: int) -> None:
        mean_level = float(np.mean(signal))
        self.summary_var.set(
            f"Generated {len(signal)} consensus levels (k={kmer_size}). Mean normalized current: {mean_level:.3f}"
        )

        fig, ax = plt.subplots(figsize=(10, 4.5))
        ax.step(np.arange(len(signal)), signal, where="mid", linewidth=1.8)
        ax.set_title("Expected Consensus Signal")
        ax.set_xlabel("k-mer index")
        ax.set_ylabel("Normalized current (I/I0)")
        ax.set_ylim(0.0, 1.0)
        ax.grid(alpha=0.3)
        fig.tight_layout()
        plt.show()


def run_gui() -> None:
    root = tk.Tk()
    app = ConsensusMakerGUI(root)
    _ = app
    root.mainloop()


if __name__ == "__main__":
    run_gui()