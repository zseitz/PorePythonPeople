"""
DataNaviGUI: Database Navigation and Search GUI
Description: Creates a tkinter GUI for navigating and managing the database.
Workflow: Select database directory → enter search criteria → view/select matching files → confirm search.
Delegates to subcomponents 2, 3, 4, 5 for filtering, logging, config, and directory selection.
"""

import os
import tkinter as tk
from tkinter import scrolledtext, messagebox, simpledialog
from datetime import datetime
from typing import List
from nanoporethon.subcomponent_4_config_manager import (
    get_database_directory, set_database_directory,
    get_logs_directory, set_logs_directory,
)
from nanoporethon.subcomponent_2_data_navigator import data_navi
from nanoporethon.subcomponent_5_directory_utilities import (
    browse_for_directory, select_database_directory, select_logs_directory,
)
from nanoporethon.subcomponent_3_data_navi_sub_directory import data_navi_sub_directory


class DataNaviGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("DataNaviGUI - Database Navigator")
        self.root.geometry("1000x700")
        
        self.database_directory = None
        self.logs_directory = None
        self.selected_files: List[str] = []
        self.all_available_files: List[str] = []
        
        self.build_gui()
        self.load_saved_directory()
    
    def build_gui(self):
        """Build the GUI layout."""
        # Top frame for database directory selection
        db_frame = tk.Frame(self.root)
        db_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(10, 5))
        
        tk.Label(db_frame, text="Database Directory:").pack(side=tk.LEFT)
        self.db_dir_var = tk.StringVar()
        tk.Entry(db_frame, textvariable=self.db_dir_var, width=50).pack(side=tk.LEFT, padx=5)
        tk.Button(db_frame, text="Browse", command=self.browse_database_directory).pack(side=tk.LEFT)
        
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
        
        # Logs directory selection (right above log window)
        logs_frame = tk.Frame(self.root)
        logs_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(5, 5))
        
        tk.Label(logs_frame, text="Logs Directory:").pack(side=tk.LEFT)
        self.logs_dir_var = tk.StringVar()
        tk.Entry(logs_frame, textvariable=self.logs_dir_var, width=50).pack(side=tk.LEFT, padx=5)
        tk.Button(logs_frame, text="Browse", command=self.browse_logs_directory).pack(side=tk.LEFT)
        
        # Confirm Search button frame
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
        """Load the saved directories on startup."""
        db_dir = get_database_directory()
        logs_dir = get_logs_directory()
        
        # Load database directory
        if db_dir:
            self.set_database_directory(db_dir)
            self.log(f"Loaded saved database directory: {db_dir}")
        else:
            self.log("Please select a database directory.")
            # Prompt for database directory at startup when not already configured.
            self.browse_database_directory()
        
        # Load logs directory if available. Do not prompt at startup.
        if logs_dir:
            self.set_logs_directory(logs_dir)
            self.log(f"Loaded saved logs directory: {logs_dir}")
    
    def browse_database_directory(self):
        """Open a directory browser dialog for database directory."""
        selected_path = browse_for_directory("Select Database Directory")
        if selected_path:
            # Update database directory StringVar and instance variable
            self.db_dir_var.set(selected_path)
            self.database_directory = selected_path
            # Save to config
            set_database_directory(selected_path)
            self.log(f"Database directory set: {selected_path}")
            self.update_file_list()
        else:
            self.log("Database directory selection cancelled or invalid.")
    
    def browse_logs_directory(self):
        """Open a directory browser dialog for logs directory."""
        selected_path = browse_for_directory("Select Logs Directory")
        if selected_path:
            # Update logs directory StringVar and instance variable
            self.logs_dir_var.set(selected_path)
            self.logs_directory = selected_path
            # Save to config
            set_logs_directory(selected_path)
            self.log(f"Logs directory set: {selected_path}")
        else:
            self.log("Logs directory selection cancelled or invalid.")
    
    def set_database_directory(self, path):
        """Set the database directory (used for loading saved config)."""
        self.db_dir_var.set(path)
        self.database_directory = path
        set_database_directory(path)
        self.log(f"Database directory set: {path}")
        self.update_file_list()
    
    def set_logs_directory(self, path):
        """Set the logs directory (used for loading saved config)."""
        self.logs_dir_var.set(path)
        self.logs_directory = path
        set_logs_directory(path)
        self.log(f"Logs directory set: {path}")
    
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
        if not self.database_directory or not os.path.isdir(self.database_directory):
            messagebox.showwarning("No Database Directory", "Please select a valid database directory first.")
            self.browse_database_directory()
            if not self.database_directory or not os.path.isdir(self.database_directory):
                return

        if not self.selected_files:
            messagebox.showwarning("No Selection", "Please select at least one file.")
            return
        
        if not self.logs_directory or not os.path.isdir(self.logs_directory):
            messagebox.showinfo("Select Logs Directory", "Please select a logs directory for this confirmed search.")
            self.browse_logs_directory()
            if not self.logs_directory or not os.path.isdir(self.logs_directory):
                return
        
        query_name = simpledialog.askstring("Query Name", "Enter a name for this search query:")
        if not query_name:
            return
        
        try:
            inclusion = [term.strip() for term in self.inclusion_var.get().split(',') if term.strip()]
            exclusion = [term.strip() for term in self.exclusion_var.get().split(',') if term.strip()]
            
            data_navi_sub_directory(
                self.database_directory,
                self.selected_files,
                self.logs_directory,
                query_name,
                inclusion,
                exclusion
            )
            
            self.log(f"Search confirmed. Created log for '{query_name}' in {self.logs_directory}.")
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
