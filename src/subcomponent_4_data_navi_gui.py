"""
Subcomponent 4: DataNaviGUI
Description: Creates a tkinter GUI for navigating and managing the database using
subcomponents 1, 2, and 3. Supports cumulative searches, persistent directory selection,
and sorted file lists.
"""

import os
import json
import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox, simpledialog
from datetime import datetime
from typing import List
from subcomponent_2_data_navigator import data_navi
from subcomponent_3_data_navi_sub_directory import data_navi_sub_directory

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


class DataNaviGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("DataNaviGUI - Database Navigator")
        self.root.geometry("1000x700")
        
        self.database_directory = None
        self.logs_save_directory = None
        self.selected_files: List[str] = []
        self.all_available_files: List[str] = []
        
        self.build_gui()
        self.load_saved_directory()
    
    def build_gui(self):
        """Build the GUI layout."""
        # Top frame for directory selection
        top_frame = tk.Frame(self.root)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)
        
        tk.Label(top_frame, text="Database Directory:").pack(side=tk.LEFT)
        self.dir_var = tk.StringVar()
        tk.Entry(top_frame, textvariable=self.dir_var, width=60).pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame, text="Browse", command=self.browse_directory).pack(side=tk.LEFT)
        
        # Search and filter frame
        search_frame = tk.LabelFrame(self.root, text="Search Filters", padx=10, pady=10)
        search_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)
        
        tk.Label(search_frame, text="Inclusion Terms (comma-separated):").pack(side=tk.TOP, anchor=tk.W)
        self.inclusion_var = tk.StringVar()
        tk.Entry(search_frame, textvariable=self.inclusion_var, width=80).pack(side=tk.TOP, fill=tk.X, pady=5)
        
        tk.Label(search_frame, text="Exclusion Terms (comma-separated):").pack(side=tk.TOP, anchor=tk.W)
        self.exclusion_var = tk.StringVar()
        tk.Entry(search_frame, textvariable=self.exclusion_var, width=80).pack(side=tk.TOP, fill=tk.X, pady=5)
        
        button_frame = tk.Frame(search_frame)
        button_frame.pack(side=tk.TOP, fill=tk.X, pady=10)
        tk.Button(button_frame, text="Search", command=self.perform_search).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Clear Selection", command=self.clear_selection).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Select All", command=self.select_all).pack(side=tk.LEFT, padx=5)
        
        # File list
        list_frame = tk.LabelFrame(self.root, text="Available Files (Click to select/deselect)", padx=10, pady=10)
        list_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.file_listbox = tk.Listbox(list_frame, selectmode=tk.SINGLE, yscrollcommand=scrollbar.set, height=15)
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.file_listbox.bind('<<ListboxSelect>>', self.on_file_select)
        scrollbar.config(command=self.file_listbox.yview)
        
        # Confirm Search button frame (above log)
        confirm_frame = tk.Frame(self.root)
        confirm_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)
        
        tk.Button(confirm_frame, text="Confirm Search", command=self.confirm_search).pack(side=tk.RIGHT, padx=5)
        
        # Log frame
        log_frame = tk.LabelFrame(self.root, text="Log", padx=10, pady=10)
        log_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=False, padx=10, pady=5)
        
        self.log_output = scrolledtext.ScrolledText(log_frame, height=5, width=100, state=tk.DISABLED)
        self.log_output.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.log("DataNaviGUI ready.")
    
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
        """Open a directory browser dialog."""
        path = filedialog.askdirectory(title="Select Database Directory")
        if path and os.path.isdir(path):
            self.set_directory(path)
        else:
            self.log("Invalid directory selected.")
    
    def set_directory(self, path):
        """Set the database directory."""
        self.dir_var.set(path)
        self.database_directory = path
        save_config(path)
        self.log(f"Directory set: {path}")
        self.update_file_list()
    
    def update_file_list(self):
        """Update the listbox with available files, selected files at top and highlighted."""
        if not self.database_directory or not os.path.isdir(self.database_directory):
            self.log("Invalid database directory.")
            return
        
        try:
            self.all_available_files = sorted(os.listdir(self.database_directory))
            self.file_listbox.delete(0, tk.END)
            
            # Sort: selected files first, then unselected
            selected_sorted = sorted([f for f in self.all_available_files if f in self.selected_files])
            unselected_sorted = sorted([f for f in self.all_available_files if f not in self.selected_files])
            
            # Display selected files first with checkmark and highlight, then unselected
            for file in selected_sorted:
                idx = self.file_listbox.size()
                self.file_listbox.insert(tk.END, f"✓ {file}")
                self.file_listbox.itemconfig(idx, background='#4CAF50', foreground='white')
            
            for file in unselected_sorted:
                self.file_listbox.insert(tk.END, file)
            
            self.log(f"Loaded {len(self.all_available_files)} files from directory. {len(self.selected_files)} selected.")
        except Exception as e:
            self.log(f"Error loading files: {e}")
    
    def perform_search(self):
        """Perform a cumulative search based on inclusion/exclusion terms."""
        if not self.database_directory:
            self.log("Please select a database directory first.")
            return
        
        inclusion = [term.strip() for term in self.inclusion_var.get().split(',') if term.strip()]
        exclusion = [term.strip() for term in self.exclusion_var.get().split(',') if term.strip()]
        
        if not inclusion:
            self.log("Please enter at least one inclusion term.")
            return
        
        try:
            results = data_navi(self.database_directory, inclusion, exclusion)
            # Cumulative: add to existing selection
            self.selected_files.extend([f for f in results if f not in self.selected_files])
            self.log(f"Found {len(results)} files. Total selected: {len(self.selected_files)}")
            self.update_file_list()
        except Exception as e:
            self.log(f"Search error: {e}")
    
    def on_file_select(self, event):
        """Handle file selection/deselection by toggling."""
        selection = self.file_listbox.curselection()
        if not selection:
            return
        
        idx = selection[0]
        file_text = self.file_listbox.get(idx)
        file_name = file_text.lstrip('✓ ')
        
        # Toggle selection
        if file_name in self.selected_files:
            self.selected_files.remove(file_name)
        else:
            self.selected_files.append(file_name)
        
        self.update_file_list()
    
    def select_all(self):
        """Select all files."""
        self.selected_files = self.all_available_files.copy()
        self.update_file_list()
        self.log(f"Selected all {len(self.selected_files)} files.")
    
    def clear_selection(self):
        """Clear all selections."""
        self.selected_files.clear()
        self.update_file_list()
        self.log("Selection cleared.")
    
    def confirm_search(self):
        """Finalize the search and create a log file."""
        if not self.selected_files:
            messagebox.showwarning("No Selection", "Please select at least one file.")
            return
        
        query_name = simpledialog.askstring("Query Name", "Enter a name for this search query:")
        if not query_name:
            return
        
        # Prompt for directory to save the log file
        log_directory = filedialog.askdirectory(title="Select directory to save the search log")
        if not log_directory:
            self.log("Log directory selection cancelled.")
            return
        
        try:
            inclusion = [term.strip() for term in self.inclusion_var.get().split(',') if term.strip()]
            exclusion = [term.strip() for term in self.exclusion_var.get().split(',') if term.strip()]
            
            data_navi_sub_directory(
                self.database_directory,
                self.selected_files,
                log_directory,
                query_name,
                inclusion,
                exclusion
            )
            
            self.log(f"Search confirmed. Created log for '{query_name}' in {log_directory}.")
            messagebox.showinfo("Success", f"Search saved successfully as '{query_name}'.\nThe GUI will now exit.")
            self.root.quit()
        except Exception as e:
            self.log(f"Error confirming search: {e}")
            messagebox.showerror("Error", f"Failed to confirm search: {e}")


def run_gui():
    """Launch the DataNaviGUI."""
    root = tk.Tk()
    app = DataNaviGUI(root)
    root.mainloop()


if __name__ == '__main__':
    run_gui()
