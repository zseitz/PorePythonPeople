"""
Subcomponent 3: DataNaviSubDirectory
Description: Creates a timestamped directory under a `tests` folder with a log file
documenting the search query and selected files (without copying the actual files).
"""

import os
import shutil
from datetime import datetime
from typing import List


def data_navi_sub_directory(source_directory: str, filenames_out: List[str], 
                            destination_parent_directory: str, query_name: str,
                            array_1: List[str], array_2: List[str]) -> None:
    """
    Creates a new timestamped directory under a `tests` subdirectory of
    `destination_parent_directory`. The new folder is named after the provided
    `query_name` with the current date/time appended. A text log is written
    documenting the inclusion/exclusion terms and the list of selected files
    (without copying them, to save storage).

    Args:
        source_directory (str): The source directory containing the data.
        filenames_out (List[str]): List of file or directory names (relative or
            absolute) that were selected.
        destination_parent_directory (str): Base path where a `tests` directory
            will be created if it does not already exist. The final path will be
            `os.path.join(destination_parent_directory, "tests", query_name + "_<timestamp>")`.
        query_name (str): Name supplied by the user in subcomponent 2 to identify
            this search; used as part of the destination folder name.
        array_1 (List[str]): The inclusion filter array used in the search.
        array_2 (List[str]): The exclusion filter array used in the search.

    Returns:
        None: Creates destination directory and a search query log file listing
        the selected files and metadata.

    Raises:
        ValueError: If source_directory or destination_parent_directory do not exist.
        TypeError: If filenames_out is not a list.
    """
    
    # Validate inputs
    if not os.path.isdir(source_directory):
        raise ValueError(f"Source directory does not exist: {source_directory}")
    
    if not os.path.isdir(destination_parent_directory):
        raise ValueError(f"Destination parent directory does not exist: {destination_parent_directory}")
    
    if not isinstance(filenames_out, list):
        raise TypeError("filenames_out must be a list of file paths.")
    
    # Create directory name with current date and time and include query_name
    current_time = datetime.now()
    timestamp = current_time.strftime("%Y%m%d_%H:%M:%S")
    directory_name = f"{query_name}_{timestamp}"
    
    # Create the full path for the new directory directly in destination_parent_directory
    new_directory_path = os.path.join(destination_parent_directory, directory_name)
    
    try:
        os.makedirs(new_directory_path, exist_ok=True)
        print(f"Created new directory: {new_directory_path}")
    except OSError as e:
        raise OSError(f"Failed to create directory {new_directory_path}: {e}")
    
    # Prepare list of selected files (without copying)
    selected_files = []
    for item_path in filenames_out:
        # Handle both absolute paths and relative paths
        if os.path.isabs(item_path):
            full_item_path = item_path
        else:
            full_item_path = os.path.join(source_directory, item_path)
        
        # Get the item name (file or folder)
        item_name = os.path.basename(full_item_path)
        selected_files.append(item_name)
    
    # Create a text file documenting the search query and selected files
    query_file_path = os.path.join(new_directory_path, "search_query.txt")
    
    try:
        with open(query_file_path, 'w') as query_file:
            query_file.write("DataNavi Search Query Log\n")
            query_file.write("=" * 50 + "\n")
            query_file.write(f"Timestamp: {current_time.strftime('%d/%m/%Y %H:%M:%S')}\n")
            query_file.write(f"Source Directory: {source_directory}\n")
            query_file.write(f"Destination Directory: {new_directory_path}\n")
            query_file.write("\n")
            query_file.write("Search Criteria:\n")
            query_file.write("-" * 50 + "\n")
            query_file.write("Inclusion Filter (Array_1):\n")
            if array_1:
                for item in array_1:
                    query_file.write(f"  - {item}\n")
            else:
                query_file.write("  (Empty - all items included initially)\n")
            
            query_file.write("\nExclusion Filter (Array_2):\n")
            if array_2:
                for item in array_2:
                    query_file.write(f"  - {item}\n")
            else:
                query_file.write("  (Empty - no items excluded)\n")
            
            query_file.write("\nSelected Files/Directories:\n")
            query_file.write("-" * 50 + "\n")
            
            if selected_files:
                for item in selected_files:
                    query_file.write(f"  - {item}\n")
            else:
                query_file.write("  (No items selected)\n")
        
        print(f"Created search query log: {query_file_path}")
    except IOError as e:
        raise IOError(f"Failed to create query file: {e}")


if __name__ == "__main__":
    # Example usage
    source_dir = "/Users/zachseitz/GitRepos/PorePythonPeople/ExampleData"
    destination_dir = "/Users/zachseitz/GitRepos/PorePythonPeople"
    query_name = "example_query"
    
    # Example filenames_out from DataNavi function
    filenames_out = [
        "240424g_2NNN2_t1&400mM400mM&perfuse&atp1000um&upstreamR4&thermistor&tset37&heating&hel308tga_p180a"
    ]
    
    # Search arrays for documentation
    array_1 = ["2NNN2", "p180"]
    array_2 = ["b", "c"]
    
    try:
        data_navi_sub_directory(source_dir, filenames_out, destination_dir, query_name, array_1, array_2)
        print("\nOperation completed successfully. Check the created directory for the log file.")
    except Exception as e:
        print(f"Error: {e}")
