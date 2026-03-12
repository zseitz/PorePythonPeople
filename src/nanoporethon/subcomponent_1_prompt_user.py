"""
Subcomponent 1: Prompt_User
Description: Using a GUI, prompt the user for the path to the directory containing data.
Save the path to a global string variable named database_directory.
"""

import tkinter as tk
from tkinter import filedialog

# Global variable to store the selected directory
database_directory = None


def prompt_user():
    """
    Prompts the user to select a directory containing data using a tkinter file dialog.
    Saves the selected path to the global variable database_directory.
    
    Returns:
        str: The selected directory path, or None if no directory was selected.
    """
    global database_directory
    
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    
    directory = filedialog.askdirectory(title="Select the directory containing data")
    
    root.destroy()
    
    if directory:
        database_directory = directory
        print(f"Selected directory: {database_directory}")
        return database_directory
    else:
        database_directory = None
        print("No directory selected.")
        return None


if __name__ == "__main__":
    result = prompt_user()
    if result:
        print(f"Global database_directory is now set to: {database_directory}")
    else:
        print("User cancelled the dialog.")
