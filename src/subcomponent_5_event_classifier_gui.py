"""
Subcomponent 5: EventClassifierGUI
Description: Creates a GUI using tkinter to assist with classifying events in the data.
Utilizes search results from subcomponent 4 to display and plot data from selected files.
"""

import os
import json
import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox, simpledialog
from datetime import datetime
from typing import List
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import h5py

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
        
        self.build_gui()
        
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
        """Handle file selection and plot the data."""
        selection = self.file_listbox.curselection()
        if not selection:
            return
        
        file_name = self.file_listbox.get(selection[0])
        file_path = os.path.join(self.database_directory, file_name)
        mat_file_path = os.path.join(file_path, 'reduced.mat')
        
        if not os.path.exists(mat_file_path):
            self.log(f"Reduced MAT file not found: {mat_file_path}")
            return
        
        try:
            # Load mat file using h5py for v7.3 HDF5 format
            with h5py.File(mat_file_path, 'r') as f:
                if 'reduced' in f:
                    reduced_group = f['reduced']
                    if 'data' in reduced_group and 'pt' in reduced_group:
                        data = reduced_group['data'][:].flatten()
                        pt = reduced_group['pt'][:].flatten()
                        
                        # Clear previous plot and toolbar
                        if self.plot_toolbar:
                            self.plot_toolbar.destroy()
                            self.plot_toolbar = None
                        if self.plot_canvas:
                            self.plot_canvas.get_tk_widget().destroy()
                        
                        # Create new plot
                        fig, ax = plt.subplots(figsize=(6, 4))
                        ax.plot(pt, data)
                        ax.set_xlabel('Point Index')
                        ax.set_ylabel('Data')
                        ax.set_title(f'Data from {file_name}')
                        
                        # Embed in tkinter with toolbar
                        self.plot_canvas = FigureCanvasTkAgg(fig, master=self.plot_container)
                        self.plot_canvas.draw()
                        self.plot_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
                        
                        # Add interactive toolbar (zoom, pan, save, etc.)
                        self.plot_toolbar = NavigationToolbar2Tk(self.plot_canvas, self.plot_container)
                        self.plot_toolbar.update()
                        
                        self.log(f"Plotted data from {file_name}")
                    else:
                        self.log(f"data or pt not found in reduced data for {file_name}")
                else:
                    self.log(f"'reduced' key not found in {file_name}")
        except Exception as e:
            self.log(f"Error loading/plotting {file_name}: {e}")
    
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
