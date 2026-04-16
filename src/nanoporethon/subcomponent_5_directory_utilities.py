"""
Subcomponent 2a: Directory Utilities
Description: Common directory selection and path management functions used by GUIs.
Provides reusable dialogs and path validation to avoid code duplication between SC4 and SC5.
"""

import os
import tkinter as tk
from tkinter import filedialog
from typing import Optional
from nanoporethon.subcomponent_4_config_manager import (
    get_database_directory,
    set_database_directory,
    get_logs_directory,
    set_logs_directory,
)


def browse_for_directory(title: str) -> Optional[str]:
    """
    Open a directory browser dialog and return the selected path.
    
    Args:
        title (str): Title for the directory browser dialog.
    
    Returns:
        Optional[str]: The selected directory path, or None if cancelled.
    """
    path = filedialog.askdirectory(title=title)
    return path if path and os.path.isdir(path) else None


def select_database_directory(allow_prompt: bool = True) -> Optional[str]:
    """
    Prompt user to select a database directory and save it.
    
    Args:
        allow_prompt (bool): If True, prompts user if none saved. If False, just checks saved value.
    
    Returns:
        Optional[str]: The selected database directory path, or None if cancelled.
    """
    saved_path = get_database_directory()
    
    if saved_path:
        return saved_path
    
    if not allow_prompt:
        return None
    
    path = browse_for_directory("Select Database Directory")
    if path:
        set_database_directory(path)
        return path
    
    return None


def select_logs_directory(allow_prompt: bool = True) -> Optional[str]:
    """
    Prompt user to select a logs directory and save it.
    
    Args:
        allow_prompt (bool): If True, prompts user if none saved. If False, just checks saved value.
    
    Returns:
        Optional[str]: The selected logs directory path, or None if cancelled.
    """
    saved_path = get_logs_directory()
    
    if saved_path:
        return saved_path
    
    if not allow_prompt:
        return None
    
    path = browse_for_directory("Select Logs Directory")
    if path:
        set_logs_directory(path)
        return path
    
    return None


def validate_directory(path: Optional[str], name: str = "directory") -> bool:
    """
    Validate that a path exists and is a directory.
    
    Args:
        path (Optional[str]): The path to validate.
        name (str): Name of the directory for error messages.
    
    Returns:
        bool: True if valid, False otherwise.
    """
    if not path:
        return False
    return os.path.isdir(path)
