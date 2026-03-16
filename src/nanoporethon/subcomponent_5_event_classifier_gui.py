"""
Subcomponent 5: EventClassifierGUI
Description: Creates a GUI using tkinter to assist with classifying events in the data.
Utilizes search results from subcomponent 4 to display and plot data from selected files.
"""

import os
import json
import tkinter as tk
from tkinter import filedialog, scrolledtext
from datetime import datetime
from typing import List, Dict, Any, Optional
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import h5py
import numpy as np

try:
    from scipy import io as scipy_io
except Exception:
    scipy_io = None

# Config file for persisting the selected directory
CONFIG_FILE = os.path.join(os.path.dirname(__file__), ".datanavi_config.json")


def load_config():
    """Load the saved database directory from config file."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                return config.get("database_directory")
        except Exception:
            return None
    return None


def save_config(database_directory):
    """Save the database directory to config file."""
    try:
        config = {"database_directory": database_directory}
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f)
    except Exception:
        pass


def load_search_log(log_file_path):
    """Load the source directory and selected files from a search log file."""
    source_directory = None
    selected_files = []
    try:
        with open(log_file_path, 'r') as f:
            lines = f.readlines()
            in_selected = False
            for line in lines:
                line = line.strip()
                # Extract source directory
                if line.startswith("Source Directory:"):
                    source_directory = line.split("Source Directory:", 1)[1].strip()
                # Extract selected files
                if line.startswith("Selected Files/Directories:"):
                    in_selected = True
                    continue
                if in_selected and line.startswith("- "):
                    selected_files.append(line[2:])
                elif in_selected and line.startswith("Failed"):
                    break
    except Exception as e:
        print(f"Error loading log: {e}")
    return source_directory, selected_files


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
        saved_dir = load_config()
        
        if saved_dir and os.path.isdir(saved_dir):
            self.set_directory(saved_dir)
            self.log(f"Loaded saved directory: {saved_dir}")
        else:
            if saved_dir:
                self.log(f"Saved directory no longer exists: {saved_dir}")
            self.log("Please select a database directory.")
    
    def browse_directory(self):
        """Open a directory browser dialog to select search logs directory."""
        path = filedialog.askdirectory(title="Select Search Logs Directory")
        if path and os.path.isdir(path):
            self.set_directory(path)
        else:
            self.log("Invalid directory selected.")
    
    def set_directory(self, path):
        """Set the search logs directory."""
        self.dir_var.set(path)
        self.logs_directory = path
        save_config(path)
        self.log(f"Directory set: {path}")
        self.refresh_queries()
    
    def refresh_queries(self):
        """Refresh the list of available search queries."""
        if not self.logs_directory or not os.path.isdir(self.logs_directory):
            self.log("Search logs directory not found.")
            return
        
        try:
            items = os.listdir(self.logs_directory)
            query_dirs = [item for item in items if os.path.isdir(os.path.join(self.logs_directory, item))]
            query_dirs.sort(reverse=True)  # Most recent first
            
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
            with h5py.File(mat_file_path, 'r') as f:
                if 'reduced' not in f:
                    self.log(f"'reduced' key not found in {file_name}")
                    return

                reduced_group = f['reduced']
                if 'data' not in reduced_group or 'pt' not in reduced_group:
                    self.log(f"data or pt not found in reduced data for {file_name}")
                    return

                data = np.array(reduced_group['data'][:]).flatten()
                pt = np.array(reduced_group['pt'][:]).flatten()
                downsample_factor = self._detect_downsample_factor(reduced_group)

            event_data = self._load_event_data(event_file_path)
            event_fsamp_hz = self._extract_fsamp_from_event_mat(event_file_path)
            meta_fsamp_hz = self._extract_fsamp_from_meta_mat(meta_file_path)
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

    def _safe_get_scalar(self, dataset_or_value) -> Optional[float]:
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

    def _normalize_key(self, key: str) -> str:
        """Normalize field names for robust matching across naming variants."""
        return ''.join(ch for ch in str(key).lower() if ch.isalnum())

    def _first_matching_key(self, container, candidates: List[str]) -> Optional[str]:
        """Return first key in container matching any candidate after normalization."""
        if not hasattr(container, 'keys'):
            return None
        normalized_candidates = {self._normalize_key(c) for c in candidates}
        for key in container.keys():
            if self._normalize_key(key) in normalized_candidates:
                return key
        return None

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
        if key in parent:
            try:
                return np.array(parent[key][:]).flatten()
            except Exception:
                return np.array([])
        return np.array([])

    def _extract_numeric_from_dataset(self, dataset, h5file) -> np.ndarray:
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

    def _find_dataset_case_insensitive(self, group, target_key: str):
        """Find a dataset by key (case-insensitive), searching recursively."""
        target = self._normalize_key(target_key)

        if not hasattr(group, 'keys'):
            return None

        # Direct children first.
        for key in group.keys():
            if self._normalize_key(key) == target:
                return group[key]

        # Then recurse into nested groups.
        for key in group.keys():
            child = group[key]
            if isinstance(child, (h5py.Group, dict)):
                found = self._find_dataset_case_insensitive(child, target_key)
                if found is not None:
                    return found
        return None

    def _load_event_vector(self, h5file, root_group, key: str) -> np.ndarray:
        """Load a vector from event.mat by key with robust fallback behavior."""
        ds = self._find_dataset_case_insensitive(root_group, key)
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

        return self._extract_numeric_from_dataset(ds, h5file)

    def _load_event_data(self, event_file_path: str) -> Dict[str, np.ndarray]:
        """Load event metadata from event.mat if available."""
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
                    'eventnum': self._load_event_vector(f, event_group, 'eventnum'),
                    'eventStartPt': self._load_event_vector(f, event_group, 'eventStartPt'),
                    'eventEndPt': self._load_event_vector(f, event_group, 'eventEndPt'),
                    'eventStartNdx': self._load_event_vector(f, event_group, 'eventStartNdx'),
                    'eventEndNdx': self._load_event_vector(f, event_group, 'eventEndNdx'),
                    'quality': self._load_event_vector(f, event_group, 'quality'),
                    'localIOS': self._load_event_vector(f, event_group, 'localIOS'),
                }
                return out
        except Exception:
            pass

        # Fallback: MATLAB v5/v7 (non-HDF5) via scipy.io.loadmat.
        if scipy_io is None:
            self.log("Could not load event.mat: unsupported format and scipy is unavailable.")
            return empty

        try:
            mat = scipy_io.loadmat(event_file_path, squeeze_me=True, struct_as_record=False)
            event_obj = mat.get('event', mat)
            out = {
                'eventnum': self._mat_extract_numeric_vector(event_obj, 'eventnum'),
                'eventStartPt': self._mat_extract_numeric_vector(event_obj, 'eventStartPt'),
                'eventEndPt': self._mat_extract_numeric_vector(event_obj, 'eventEndPt'),
                'eventStartNdx': self._mat_extract_numeric_vector(event_obj, 'eventStartNdx'),
                'eventEndNdx': self._mat_extract_numeric_vector(event_obj, 'eventEndNdx'),
                'quality': self._mat_extract_numeric_vector(event_obj, 'quality'),
                'localIOS': self._mat_extract_numeric_vector(event_obj, 'localIOS'),
            }
            return out
        except Exception as e:
            self.log(f"Could not load event.mat: {e}")
            return empty

    def _mat_iter_children(self, obj):
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

    def _mat_find_field(self, obj, field_name: str, depth: int = 0):
        """Recursively find a field in MATLAB-loaded structures (case-insensitive)."""
        if obj is None or depth > 4:
            return None

        target = field_name.lower()
        for k, v in self._mat_iter_children(obj):
            if isinstance(k, str) and k.lower() == target:
                return v

        for _k, v in self._mat_iter_children(obj):
            found = self._mat_find_field(v, field_name, depth + 1)
            if found is not None:
                return found
        return None

    def _mat_to_numeric_array(self, value) -> np.ndarray:
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
                sub = self._mat_to_numeric_array(item)
                if sub.size > 0:
                    vals.extend(sub.tolist())
            return np.array(vals, dtype=float) if vals else np.array([])

        try:
            return arr.astype(float).flatten()
        except Exception:
            return np.array([])

    def _mat_extract_numeric_vector(self, root_obj, field_name: str) -> np.ndarray:
        """Extract a numeric vector for a field from scipy-loaded MATLAB content."""
        value = self._mat_find_field(root_obj, field_name)
        return self._mat_to_numeric_array(value)

    def _extract_fsamp_from_event_mat(self, event_file_path: str) -> Optional[float]:
        """Extract fsamp from event.mat, preferring values in the event group."""
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
                    matched_key = self._first_matching_key(group, candidate_keys)
                    if matched_key is not None:
                        obj = group[matched_key]
                        if isinstance(obj, h5py.Dataset):
                            vals = self._extract_numeric_from_dataset(obj, f)
                            value = float(vals[0]) if vals.size > 0 else None
                        else:
                            try:
                                value = float(np.array(obj).flatten()[0])
                            except Exception:
                                value = self._safe_get_scalar(obj)
                        if value and value > 0:
                            return float(value)

                # Fallback: one-level nested groups (robust to schema variations).
                for group in groups_to_check:
                    if not hasattr(group, 'keys'):
                        continue
                    for child_key in group.keys():
                        child = group[child_key]
                        if isinstance(child, (h5py.Group, dict)):
                            if not hasattr(child, 'keys'):
                                continue
                            matched_key = self._first_matching_key(child, candidate_keys)
                            if matched_key is not None:
                                obj = child[matched_key]
                                if isinstance(obj, h5py.Dataset):
                                    vals = self._extract_numeric_from_dataset(obj, f)
                                    value = float(vals[0]) if vals.size > 0 else None
                                else:
                                    try:
                                        value = float(np.array(obj).flatten()[0])
                                    except Exception:
                                        value = self._safe_get_scalar(obj)
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
                    vals = self._mat_extract_numeric_vector(event_obj, key)
                    if vals.size > 0 and float(vals[0]) > 0:
                        return float(vals[0])
            except Exception:
                pass
        else:
            self.log("Could not extract fsamp from event.mat: scipy is unavailable for non-HDF5 files.")

        return None

    def _extract_fsamp_from_meta_mat(self, meta_file_path: str) -> Optional[float]:
        """Extract fsamp from meta.mat, preferring values in the meta group."""
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
                    matched_key = self._first_matching_key(group, candidate_keys)
                    if matched_key is not None:
                        obj = group[matched_key]
                        if isinstance(obj, h5py.Dataset):
                            vals = self._extract_numeric_from_dataset(obj, f)
                            value = float(vals[0]) if vals.size > 0 else None
                        else:
                            try:
                                value = float(np.array(obj).flatten()[0])
                            except Exception:
                                value = self._safe_get_scalar(obj)
                        if value and value > 0:
                            return float(value)

                # Fallback: one-level nested groups (robust to schema variations).
                for group in groups_to_check:
                    if not hasattr(group, 'keys'):
                        continue
                    for child_key in group.keys():
                        child = group[child_key]
                        if isinstance(child, (h5py.Group, dict)):
                            if not hasattr(child, 'keys'):
                                continue
                            matched_key = self._first_matching_key(child, candidate_keys)
                            if matched_key is not None:
                                obj = child[matched_key]
                                if isinstance(obj, h5py.Dataset):
                                    vals = self._extract_numeric_from_dataset(obj, f)
                                    value = float(vals[0]) if vals.size > 0 else None
                                else:
                                    try:
                                        value = float(np.array(obj).flatten()[0])
                                    except Exception:
                                        value = self._safe_get_scalar(obj)
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
                    vals = self._mat_extract_numeric_vector(meta_obj, key)
                    if vals.size > 0 and float(vals[0]) > 0:
                        return float(vals[0])
            except Exception:
                pass
        else:
            self.log("Could not extract fsamp from meta.mat: scipy is unavailable for non-HDF5 files.")

        return None

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
