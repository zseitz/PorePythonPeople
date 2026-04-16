"""
Subcomponent 3a: Search Log Utilities
Description: Common functions for parsing and loading search log files from SC3.
Extracted from SC5 to be reusable by other components.
"""

import os
from typing import Tuple, List, Optional


def load_search_log(log_file_path: str) -> Tuple[Optional[str], List[str]]:
    """
    Load the source directory and selected files from a search log file.
    
    Args:
        log_file_path (str): Path to the search_query.txt log file.
    
    Returns:
        Tuple[Optional[str], List[str]]: (source_directory, selected_files)
                                         Returns (None, []) if parsing fails.
    """
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
    except Exception:
        pass
    
    return source_directory, selected_files


def find_search_queries(directory: str) -> List[str]:
    """
    Find all search query directories in a given logs directory.
    
    Args:
        directory (str): Path to the logs directory.
    
    Returns:
        List[str]: List of query directory names, sorted most recent first.
    """
    if not os.path.isdir(directory):
        return []
    
    try:
        items = os.listdir(directory)
        query_dirs = [item for item in items if os.path.isdir(os.path.join(directory, item))]
        query_dirs.sort(reverse=True)  # Most recent first
        return query_dirs
    except Exception:
        return []
