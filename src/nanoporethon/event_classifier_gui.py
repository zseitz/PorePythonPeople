"""
EventClassifierGUI: Event Classification and Editing GUI
Description: Creates a GUI for classifying and editing events.
Focuses on event visualization, navigation, and quality editing.
Delegates to subcomponents 4, 5, 6, 7 for config, directory selection, log parsing, and data loading.
"""

import os
import tkinter as tk
from tkinter import scrolledtext
from datetime import datetime
from typing import List, Dict, Any, Optional
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import h5py
import numpy as np

from nanoporethon.subcomponent_4_config_manager import (
    get_database_directory, set_database_directory,
)
from nanoporethon.subcomponent_5_directory_utilities import browse_for_directory
from nanoporethon.subcomponent_6_search_log_utilities import (
    load_search_log, find_search_queries,
)
from nanoporethon.subcomponent_7_mat_file_loader import (
    load_reduced_mat, load_event_data, load_fsamp_from_event_mat, load_fsamp_from_meta_mat,
)

# Import internal MAT file loader functions for backward compatibility with tests
from nanoporethon.subcomponent_7_mat_file_loader import (
    _safe_get_scalar as _safe_get_scalar_impl,
    _normalize_key as _normalize_key_impl,
    _first_matching_key as _first_matching_key_impl,
    _extract_numeric_from_dataset as _extract_numeric_from_dataset_impl,
    _load_event_vector as _load_event_vector_impl,
    _find_dataset_case_insensitive as _find_dataset_case_insensitive_impl,
    _mat_extract_numeric_vector as _mat_extract_numeric_vector_impl,
    _mat_find_field as _mat_find_field_impl,
    _mat_iter_children as _mat_iter_children_impl,
    _mat_to_numeric_array as _mat_to_numeric_array_impl,
)


class EventClassifierGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("EventClassifierGUI - Data Analysis")
        self.root.geometry("1200x800")
        
        self.logs_directory = None
        self.database_directory = None
        self.current_query = None
        self.selected_files: List[str] = []
        self.plot_canvas = None
        self.plot_toolbar = None

        self.current_file_name: Optional[str] = None
        self.current_reduced_mat_path: Optional[str] = None
        self.current_event_mat_path: Optional[str] = None
        self.current_data: Optional[np.ndarray] = None
        self.current_pt: Optional[np.ndarray] = None
        self.current_time_s: Optional[np.ndarray] = None
        self.current_fsamp_hz: Optional[float] = None
        self.current_downsample_factor: float = 1.0
        self.current_effective_fs_hz: Optional[float] = None
        self.current_event_data: Dict[str, np.ndarray] = {}
        self.current_ax = None

        self.classify_mode = False
        self.current_event_index = 0
        
        self.build_gui()
        self._bind_keyboard_shortcuts()
        
        # Load saved directory on startup
        self.load_saved_directory()
    
    def build_gui(self):
        """Build the GUI layout."""
        # Top frame for directory and query selection
        top_frame = tk.Frame(self.root)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)
        
        # Directory selection for search logs
        dir_frame = tk.Frame(top_frame)
        dir_frame.pack(side=tk.TOP, fill=tk.X)
        
        tk.Label(dir_frame, text="Search Logs Directory:").pack(side=tk.LEFT)
        self.dir_var = tk.StringVar()
        tk.Entry(dir_frame, textvariable=self.dir_var, width=50).pack(side=tk.LEFT, padx=5)
        tk.Button(dir_frame, text="Browse", command=self.browse_directory).pack(side=tk.LEFT)
        
        # Query selection
        query_frame = tk.Frame(top_frame)
        query_frame.pack(side=tk.TOP, fill=tk.X, pady=(10, 0))
        
        tk.Label(query_frame, text="Search Query:").pack(side=tk.LEFT)
        self.query_var = tk.StringVar()
        self.query_combo = tk.OptionMenu(query_frame, self.query_var, [])
        self.query_combo.pack(side=tk.LEFT, padx=5)
        self.query_combo.config(width=40)
        tk.Button(query_frame, text="Refresh Queries", command=self.refresh_queries).pack(side=tk.LEFT)
        
        # Middle frame for file list and plot
        middle_frame = tk.Frame(self.root)
        middle_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # File list
        list_frame = tk.LabelFrame(middle_frame, text="Files in Query", padx=10, pady=10)
        list_frame.pack(side=tk.LEFT, fill=tk.Y)
        
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.file_listbox = tk.Listbox(list_frame, selectmode=tk.SINGLE, yscrollcommand=scrollbar.set, height=20)
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.file_listbox.bind('<<ListboxSelect>>', self.on_file_select)
        scrollbar.config(command=self.file_listbox.yview)
        
        # Plot area
        plot_frame = tk.LabelFrame(middle_frame, text="Data Plot", padx=10, pady=10)
        plot_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        controls_frame = tk.Frame(plot_frame)
        controls_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 8))

        tk.Label(controls_frame, text="Sampling Frequency (Hz, optional override):").pack(side=tk.LEFT)
        self.fsamp_override_var = tk.StringVar()
        tk.Entry(controls_frame, textvariable=self.fsamp_override_var, width=16).pack(side=tk.LEFT, padx=5)
        tk.Button(controls_frame, text="Apply Frequency", command=self.recompute_time_axis).pack(side=tk.LEFT, padx=5)

        tk.Button(controls_frame, text="Classify Events", command=self.start_classify_events).pack(side=tk.LEFT, padx=15)
        tk.Button(controls_frame, text="Previous Event", command=self.previous_event).pack(side=tk.LEFT, padx=5)
        tk.Button(controls_frame, text="Next Event", command=self.next_event).pack(side=tk.LEFT, padx=5)

        tk.Label(controls_frame, text="Event #: ").pack(side=tk.LEFT, padx=(20, 0))
        self.current_eventnum_var = tk.StringVar()
        self.current_eventnum_var.set("-")
        tk.Label(controls_frame, textvariable=self.current_eventnum_var).pack(side=tk.LEFT, padx=(0, 10))

        tk.Label(controls_frame, text="Quality:").pack(side=tk.LEFT)
        self.quality_var = tk.StringVar()
        tk.Entry(controls_frame, textvariable=self.quality_var, width=10).pack(side=tk.LEFT, padx=5)
        tk.Button(controls_frame, text="Save Quality", command=self.save_current_quality).pack(side=tk.LEFT, padx=5)

        tk.Label(
            controls_frame,
            text="Shortcuts: ←/p prev  →/n next  c classify  s/Enter save",
            fg="#555555"
        ).pack(side=tk.LEFT, padx=(12, 0))
        
        self.plot_container = tk.Frame(plot_frame)
        self.plot_container.pack(fill=tk.BOTH, expand=True)
        
        # Bottom frame for log
        log_frame = tk.LabelFrame(self.root, text="Log", padx=10, pady=10)
        log_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=False, padx=10, pady=5)
        
        self.log_output = scrolledtext.ScrolledText(log_frame, height=6, width=100, state=tk.DISABLED)
        self.log_output.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Button frame at the very bottom
        button_frame = tk.Frame(self.root)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        
        tk.Button(button_frame, text="Exit", command=self.exit_gui, bg='#ff6b6b', fg='white').pack(side=tk.RIGHT, padx=5)
        
        self.log("EventClassifierGUI ready.")

    def _bind_keyboard_shortcuts(self):
        """Bind keyboard shortcuts for faster event navigation/classification."""
        # Arrow keys and n/p are convenient for stepping events.
        self.root.bind('<Left>', self.on_keyboard_shortcut)
        self.root.bind('<Right>', self.on_keyboard_shortcut)
        self.root.bind('<Key>', self.on_keyboard_shortcut)

    def on_keyboard_shortcut(self, event):
        """Handle keyboard shortcuts.

        Shortcuts:
        - Left arrow / p: previous event
        - Right arrow / n: next event
        - c: classify events (jump to first event)
        - s / Return: save current quality
        """
        key = (getattr(event, 'keysym', '') or '').lower()
        char = (getattr(event, 'char', '') or '').lower()

        # Prefer keysym, but fall back to character for plain key presses.
        token = key if key else char

        # Avoid hijacking text-entry typing for letter shortcuts.
        widget_class = ""
        widget = getattr(event, 'widget', None)
        if widget is not None:
            try:
                widget_class = widget.winfo_class()
            except Exception:
                widget_class = ""

        if widget_class == 'Entry' and token in {'n', 'p', 'c', 's'}:
            return None

        if token in {'left', 'p'}:
            self.previous_event()
            return "break"
        if token in {'right', 'n'}:
            self.next_event()
            return "break"
        if token == 'c':
            self.start_classify_events()
            return "break"
        if token in {'s', 'return'}:
            self.save_current_quality()
            return "break"
        return None
    
    def log(self, msg):
        """Add a timestamped message to the log."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_output.config(state=tk.NORMAL)
        self.log_output.insert(tk.END, f"[{timestamp}] {msg}\n")
        self.log_output.see(tk.END)
        self.log_output.config(state=tk.DISABLED)
    
    def load_saved_directory(self):
        """Load the saved directory on startup."""
        saved_dir = get_database_directory()
        
        if saved_dir:
            self.set_directory(saved_dir)
            self.log(f"Loaded saved directory: {saved_dir}")
        else:
            self.log("Please select a database directory.")
    
    def browse_directory(self):
        """Open a directory browser dialog to select search logs directory."""
        path = browse_for_directory("Select Search Logs Directory")
        if path:
            self.set_directory(path)
        else:
            self.log("Invalid directory selected.")
    
    def set_directory(self, path):
        """Set the search logs directory."""
        self.dir_var.set(path)
        self.logs_directory = path
        set_database_directory(path)
        self.log(f"Directory set: {path}")
        self.refresh_queries()
    
    def refresh_queries(self):
        """Refresh the list of available search queries."""
        if not self.logs_directory or not os.path.isdir(self.logs_directory):
            self.log("Search logs directory not found.")
            return
        
        try:
            query_dirs = find_search_queries(self.logs_directory)
            
            # Update the option menu
            menu = self.query_combo["menu"]
            menu.delete(0, "end")
            for query in query_dirs:
                menu.add_command(label=query, command=lambda q=query: self.select_query(q))
            
            if query_dirs:
                self.query_var.set(query_dirs[0])
                self.select_query(query_dirs[0])
            
            self.log(f"Found {len(query_dirs)} search queries.")
        except Exception as e:
            self.log(f"Error refreshing queries: {e}")
    
    def select_query(self, query_name):
        """Select a search query and load its files."""
        self.query_var.set(query_name)
        self.current_query = query_name
        
        query_path = os.path.join(self.logs_directory, query_name)
        log_file = os.path.join(query_path, "search_query.txt")
        
        if not os.path.exists(log_file):
            self.log(f"Log file not found: {log_file}")
            return
        
        self.database_directory, self.selected_files = load_search_log(log_file)
        
        if not self.database_directory:
            self.log(f"Could not find source directory in log file")
            return
        
        # Update file listbox
        self.file_listbox.delete(0, tk.END)
        for file in self.selected_files:
            self.file_listbox.insert(tk.END, file)
        
        self.log(f"Loaded query '{query_name}' with {len(self.selected_files)} files from {self.database_directory}.")
    
    def on_file_select(self, event):
        """Handle file selection and plot reduced data with event overlays."""
        selection = self.file_listbox.curselection()
        if not selection:
            return
        
        file_name = self.file_listbox.get(selection[0])
        file_path = os.path.join(self.database_directory, file_name)
        mat_file_path = os.path.join(file_path, 'reduced.mat')
        event_file_path = os.path.join(file_path, 'event.mat')
        meta_file_path = os.path.join(file_path, 'meta.mat')
        
        if not os.path.exists(mat_file_path):
            self.log(f"Reduced MAT file not found: {mat_file_path}")
            return
        
        try:
            # Load data from reduced.mat using SC5a
            data, pt, downsample_factor = load_reduced_mat(mat_file_path)
            if data is None or pt is None:
                self.log(f"Failed to load data from {file_name}")
                return
            
            # Load event data using SC5a
            event_data = load_event_data(event_file_path)
            event_fsamp_hz = load_fsamp_from_event_mat(event_file_path)
            meta_fsamp_hz = load_fsamp_from_meta_mat(meta_file_path)
            fsamp_hz = meta_fsamp_hz if (meta_fsamp_hz and meta_fsamp_hz > 0) else event_fsamp_hz

            self.current_file_name = file_name
            self.current_reduced_mat_path = mat_file_path
            self.current_event_mat_path = event_file_path if os.path.exists(event_file_path) else None
            self.current_data = data
            self.current_pt = pt
            self.current_fsamp_hz = fsamp_hz
            self.current_downsample_factor = downsample_factor
            self.current_event_data = event_data
            self.classify_mode = False
            self.current_event_index = 0
            self.current_eventnum_var.set("-")
            self.quality_var.set("")

            # Auto-populate fsamp input box when available (prefers event.mat).
            if fsamp_hz and fsamp_hz > 0:
                self.fsamp_override_var.set(f"{float(fsamp_hz):g}")
            else:
                self.fsamp_override_var.set("")

            self._compute_time_axis()
            self._plot_current_data()

            event_count = self._get_event_count()
            boundary_source = self._get_event_boundary_source()

            if self.current_event_mat_path:
                if meta_fsamp_hz and meta_fsamp_hz > 0:
                    self.log(
                        f"Plotted data and event overlays from {file_name}. "
                        f"fsamp loaded from meta.mat. Detected {event_count} events via {boundary_source}."
                    )
                elif event_fsamp_hz and event_fsamp_hz > 0:
                    self.log(
                        f"Plotted data and event overlays from {file_name}. "
                        f"fsamp loaded from event.mat. Detected {event_count} events via {boundary_source}."
                    )
                else:
                    self.log(
                        f"Plotted data and event overlays from {file_name}. "
                        f"Detected {event_count} events via {boundary_source}."
                    )
            else:
                self.log(f"Plotted data from {file_name} (event.mat not found)")
        except Exception as e:
            self.log(f"Error loading/plotting {file_name}: {e}")

    # Helper methods for data processing and plotting
    
    # These methods are wrappers that delegate to SC5a (MAT File Loader)
    # Kept for backward compatibility with existing tests and code
    
    def _safe_get_scalar(self, dataset_or_value) -> Optional[float]:
        """Wrapper for SC5a function."""
        return _safe_get_scalar_impl(dataset_or_value)
    
    def _normalize_key(self, key: str) -> str:
        """Wrapper for SC5a function."""
        return _normalize_key_impl(key)
    
    def _first_matching_key(self, container, candidates: List[str]) -> Optional[str]:
        """Wrapper for SC5a function."""
        return _first_matching_key_impl(container, candidates)
    
    def _extract_numeric_from_dataset(self, dataset, h5file) -> np.ndarray:
        """Wrapper for SC5a function."""
        return _extract_numeric_from_dataset_impl(dataset, h5file)
    
    def _load_event_data(self, event_file_path: str) -> Dict[str, np.ndarray]:
        """Wrapper for SC5a function."""
        return load_event_data(event_file_path)
    
    def _extract_fsamp_from_event_mat(self, event_file_path: str) -> Optional[float]:
        """Wrapper for SC5a function."""
        return load_fsamp_from_event_mat(event_file_path)
    
    def _extract_fsamp_from_meta_mat(self, meta_file_path: str) -> Optional[float]:
        """Wrapper for SC5a function."""
        return load_fsamp_from_meta_mat(meta_file_path)
    
    def _detect_downsample_factor(self, reduced_group) -> float:
        """Detect downsample factor in reduced.mat. Defaults to 1 if unavailable."""
        candidate_keys = ['downsampleFactor', 'downsample', 'dwnspl', 'ds', 'dsFactor']
        for key in candidate_keys:
            if key in reduced_group:
                value = self._safe_get_scalar(reduced_group.get(key))
                if value and value > 0:
                    return float(value)
        return 1.0
    
    def _compute_time_axis(self):
        """Convert point axis to time (seconds) using fsamp and downsample factor."""
        if self.current_pt is None:
            self.current_time_s = None
            self.current_effective_fs_hz = None
            return

        override_fs = None
        fs_text = self.fsamp_override_var.get().strip() if hasattr(self, 'fsamp_override_var') else ''
        if fs_text:
            try:
                parsed = float(fs_text)
                if parsed > 0:
                    override_fs = parsed
            except Exception:
                self.log("Invalid sampling frequency override. Using fsamp from event.mat/meta.mat when available.")

        base_fs = override_fs if override_fs is not None else self.current_fsamp_hz

        if not base_fs or base_fs <= 0:
            self.current_effective_fs_hz = None
            self.current_time_s = np.array(self.current_pt, dtype=float)
            self.log("Sampling frequency unavailable. Using points on x-axis.")
            return

        ds = self.current_downsample_factor if self.current_downsample_factor > 0 else 1.0
        effective_fs = base_fs / ds
        if effective_fs <= 0:
            self.current_effective_fs_hz = None
            self.current_time_s = np.array(self.current_pt, dtype=float)
            self.log("Invalid effective sampling frequency. Using points on x-axis.")
            return

        self.current_effective_fs_hz = effective_fs
        self.current_time_s = np.array(self.current_pt, dtype=float) / effective_fs
    
    def _array_or_empty(self, parent, key) -> np.ndarray:
        """Helper to extract array from parent or return empty array."""
        if key in parent:
            try:
                return np.array(parent[key][:]).flatten()
            except Exception:
                return np.array([])
        return np.array([])
    
    def _find_dataset_case_insensitive(self, group, target_key: str):
        """Wrapper for SC5a function."""
        return _find_dataset_case_insensitive_impl(group, target_key)
    
    def _load_event_vector(self, h5file, root_group, key: str) -> np.ndarray:
        """Wrapper for SC5a function."""
        return _load_event_vector_impl(h5file, root_group, key)
    
    def _mat_iter_children(self, obj):
        """Wrapper for SC5a function."""
        return _mat_iter_children_impl(obj)
    
    def _mat_find_field(self, obj, field_name: str, depth: int = 0):
        """Wrapper for SC5a function."""
        return _mat_find_field_impl(obj, field_name, depth)
    
    def _mat_to_numeric_array(self, value) -> np.ndarray:
        """Wrapper for SC5a function."""
        return _mat_to_numeric_array_impl(value)
    
    def _mat_extract_numeric_vector(self, root_obj, field_name: str) -> np.ndarray:
        """Wrapper for SC5a function."""
        return _mat_extract_numeric_vector_impl(root_obj, field_name)

    def _event_point_to_time(self, point: float) -> float:
        fs = self.current_effective_fs_hz
        if fs and fs > 0:
            return float(point) / fs
        return float(point)

    def _get_event_boundaries(self):
        """Return event start/end arrays, preferring Pt and falling back to Ndx."""
        starts_pt = self.current_event_data.get('eventStartPt', np.array([]))
        ends_pt = self.current_event_data.get('eventEndPt', np.array([]))
        if starts_pt.size > 0 and ends_pt.size > 0:
            return starts_pt, ends_pt

        starts_ndx = self.current_event_data.get('eventStartNdx', np.array([]))
        ends_ndx = self.current_event_data.get('eventEndNdx', np.array([]))
        if starts_ndx.size > 0 and ends_ndx.size > 0:
            return starts_ndx, ends_ndx

        return np.array([]), np.array([])

    def _get_event_boundary_source(self) -> str:
        """Return the boundary source currently used for event classification."""
        starts_pt = self.current_event_data.get('eventStartPt', np.array([]))
        ends_pt = self.current_event_data.get('eventEndPt', np.array([]))
        if starts_pt.size > 0 and ends_pt.size > 0:
            return "eventStartPt/eventEndPt"

        starts_ndx = self.current_event_data.get('eventStartNdx', np.array([]))
        ends_ndx = self.current_event_data.get('eventEndNdx', np.array([]))
        if starts_ndx.size > 0 and ends_ndx.size > 0:
            return "eventStartNdx/eventEndNdx"

        return "none"

    def _quality_to_color(self, quality_value: float) -> str:
        if np.isnan(quality_value):
            return '#9E9E9E'
        if quality_value <= 0:
            return '#EF5350'
        if quality_value == 1:
            return '#FFB300'
        return '#66BB6A'

    def _overlay_events(self, ax):
        event_start_pt, event_end_pt = self._get_event_boundaries()
        event_num = self.current_event_data.get('eventnum', np.array([]))
        quality = self.current_event_data.get('quality', np.array([]))
        local_ios_arr = self.current_event_data.get('localIOS', np.array([]))

        if local_ios_arr.size > 0:
            local_ios_val = float(local_ios_arr[0])
            ax.axhline(local_ios_val, color='red', linestyle='-', linewidth=1.2, alpha=0.9, label='localIOS')

        n_events = min(event_start_pt.size, event_end_pt.size)
        if n_events == 0:
            return

        y_min, y_max = ax.get_ylim()
        y_for_label = y_max - 0.05 * (y_max - y_min)

        for i in range(n_events):
            start_time = self._event_point_to_time(event_start_pt[i])
            end_time = self._event_point_to_time(event_end_pt[i])

            q = np.nan
            if i < quality.size:
                try:
                    q = float(quality[i])
                except Exception:
                    q = np.nan

            color = self._quality_to_color(q)
            ax.axvline(start_time, color='purple', linestyle='--', linewidth=0.8, alpha=0.6)
            ax.axvline(end_time, color='purple', linestyle='--', linewidth=0.8, alpha=0.6)
            ax.axvspan(start_time, end_time, color=color, alpha=0.12)

            if i < event_num.size:
                label = str(int(event_num[i])) if float(event_num[i]).is_integer() else str(event_num[i])
                ax.text(start_time, y_for_label, label, fontsize=7, color='purple', rotation=90,
                        va='top', ha='left', alpha=0.8)

    def _plot_current_data(self):
        if self.current_data is None or self.current_time_s is None:
            return

        if self.plot_toolbar:
            self.plot_toolbar.destroy()
            self.plot_toolbar = None
        if self.plot_canvas:
            self.plot_canvas.get_tk_widget().destroy()

        fig, ax = plt.subplots(figsize=(6, 4))
        ax.plot(self.current_time_s, self.current_data, linewidth=0.9)
        ax.set_xlabel('Time (s)' if self.current_effective_fs_hz else 'Point Index')
        ax.set_ylabel('Current (pA)')
        title_file = self.current_file_name if self.current_file_name else 'selected file'
        ax.set_title(f'Data from {title_file}')

        self._overlay_events(ax)

        self.current_ax = ax
        self.plot_canvas = FigureCanvasTkAgg(fig, master=self.plot_container)
        self.plot_canvas.draw()
        self.plot_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.plot_toolbar = NavigationToolbar2Tk(self.plot_canvas, self.plot_container)
        self.plot_toolbar.update()

    def recompute_time_axis(self):
        """Recompute point-to-time conversion and refresh the plot."""
        if self.current_pt is None or self.current_data is None:
            self.log("No file loaded to re-compute time axis.")
            return
        self._compute_time_axis()
        self._plot_current_data()
        self.log("Updated x-axis conversion using current sampling frequency settings.")

    def _get_event_count(self) -> int:
        starts, ends = self._get_event_boundaries()
        return int(min(starts.size, ends.size))

    def start_classify_events(self):
        """Enter classify mode and zoom to the first event without replotting."""
        n_events = self._get_event_count()
        if self.current_ax is None:
            self.log("Load a file before classifying events.")
            return
        if n_events == 0:
            self.log("No events available to classify.")
            return

        self.classify_mode = True
        self.current_event_index = 0
        self._zoom_to_event(self.current_event_index)

    def next_event(self):
        """Advance to the next event in classify mode."""
        n_events = self._get_event_count()
        if self.current_ax is None or n_events == 0:
            self.log("No loaded events to navigate.")
            return

        if not self.classify_mode:
            self.classify_mode = True

        self.current_event_index = (self.current_event_index + 1) % n_events
        self._zoom_to_event(self.current_event_index)

    def previous_event(self):
        """Go to the previous event in classify mode."""
        n_events = self._get_event_count()
        if self.current_ax is None or n_events == 0:
            self.log("No loaded events to navigate.")
            return

        if not self.classify_mode:
            self.classify_mode = True

        self.current_event_index = (self.current_event_index - 1) % n_events
        self._zoom_to_event(self.current_event_index)

    def _zoom_to_event(self, idx: int):
        starts, ends = self._get_event_boundaries()
        quality = self.current_event_data.get('quality', np.array([]))
        eventnum = self.current_event_data.get('eventnum', np.array([]))
        local_ios_arr = self.current_event_data.get('localIOS', np.array([]))

        n_events = self._get_event_count()
        if idx < 0 or idx >= n_events:
            self.log("Event index out of range.")
            return

        start_t = self._event_point_to_time(starts[idx])
        end_t = self._event_point_to_time(ends[idx])
        if end_t < start_t:
            start_t, end_t = end_t, start_t

        span = max(end_t - start_t, 1e-9)
        x_pad = 0.25 * span
        x_min = start_t - x_pad
        x_max = end_t + x_pad

        y_candidates = [0.0]
        if local_ios_arr.size > 0:
            y_candidates.append(float(local_ios_arr[0]))

        if self.current_data is not None and self.current_time_s is not None:
            mask = (self.current_time_s >= x_min) & (self.current_time_s <= x_max)
            if np.any(mask):
                event_segment = self.current_data[mask]
                y_candidates.extend([float(np.min(event_segment)), float(np.max(event_segment))])

        y_min = min(y_candidates)
        y_max = max(y_candidates)
        y_pad = 0.2 * max(abs(y_max - y_min), 1.0)

        self.current_ax.set_xlim(x_min, x_max)
        self.current_ax.set_ylim(y_min - y_pad, y_max + y_pad)
        if self.plot_canvas:
            self.plot_canvas.draw()

        if idx < eventnum.size:
            n = eventnum[idx]
            label_num = str(int(n)) if float(n).is_integer() else str(n)
            self.current_eventnum_var.set(label_num)
        else:
            self.current_eventnum_var.set(str(idx + 1))

        if idx < quality.size:
            self.quality_var.set(str(quality[idx]))
        else:
            self.quality_var.set("")

        self.log(f"Classifying event {self.current_eventnum_var.get()} ({idx + 1}/{n_events}).")

    def save_current_quality(self):
        """Save edited event quality back to event.mat for current event only."""
        n_events = self._get_event_count()
        if n_events == 0:
            self.log("No event selected to save quality.")
            return

        idx = self.current_event_index
        if idx < 0 or idx >= n_events:
            self.log("Current event index is invalid.")
            return

        text = self.quality_var.get().strip()
        try:
            new_quality = float(text)
        except Exception:
            self.log("Quality must be a numeric value.")
            return

        if not self.current_event_mat_path or not os.path.exists(self.current_event_mat_path):
            self.log("event.mat not found; cannot save quality.")
            return

        try:
            with h5py.File(self.current_event_mat_path, 'r+') as f:
                event_group = f['event'] if 'event' in f else f
                if 'quality' not in event_group:
                    self.log("event.quality not found in event.mat.")
                    return

                quality_ds = event_group['quality']
                flat = quality_ds[...].reshape(-1)
                if idx >= flat.size:
                    self.log("Selected event index exceeds event.quality length.")
                    return

                flat[idx] = new_quality
                quality_ds[...] = flat.reshape(quality_ds.shape)

            quality = self.current_event_data.get('quality', np.array([]))
            if quality.size > idx:
                quality[idx] = new_quality

            self.log(f"Saved event.quality for event {self.current_eventnum_var.get()} as {new_quality}.")
        except Exception as e:
            self.log(f"Failed to save event quality: {e}")
    
    def exit_gui(self):
        """Close the EventClassifierGUI."""
        self.log("Exiting EventClassifierGUI...")
        self.root.quit()


def run_gui():
    """Launch the EventClassifierGUI."""
    root = tk.Tk()
    app = EventClassifierGUI(root)
    root.mainloop()


if __name__ == '__main__':
    run_gui()
