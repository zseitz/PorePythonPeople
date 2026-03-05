"""
Subcomponent 2: Data_Navigator
Description: Implements a function called data_navi that filters files based on
inclusion and exclusion criteria provided by the user.
"""

import os
from typing import List


def data_navi(database_directory: str, array_1: List[str], array_2: List[str]) -> List[str]:
    """
    Filters files in the database directory based on inclusion and exclusion criteria.
    
    Args:
        database_directory (str): Path to the database directory containing files/folders.
        array_1 (List[str]): Inclusion filter - files must contain ALL strings in this list.
        array_2 (List[str]): Exclusion filter - files containing ANY string in this list are removed.
    
    Returns:
        List[str]: List of filenames that match the inclusion criteria and don't match exclusion criteria.
    """
    
    if not os.path.isdir(database_directory):
        raise ValueError(f"Database directory does not exist: {database_directory}")
    
    filenames_out = []
    
    try:
        items = os.listdir(database_directory)
    except OSError as e:
        raise OSError(f"Failed to list directory {database_directory}: {e}")
    
    # Filter based on inclusion criteria (Array_1)
    for item in items:
        # Check if all strings in array_1 are present in the item name
        if all(search_term in item for search_term in array_1):
            filenames_out.append(item)
    
    # Filter based on exclusion criteria (Array_2)
    if array_2:
        filenames_out = [item for item in filenames_out if not any(exclude_term in item for exclude_term in array_2)]
    
    return filenames_out


if __name__ == "__main__":
    # Example usage
    db_dir = "/Users/zachseitz/GitRepos/PorePythonPeople/ExampleData"
    
    # Example search criteria
    inclusion_terms = ["2NNN2", "p180"]
    exclusion_terms = ["b", "c"]
    
    try:
        results = data_navi(db_dir, inclusion_terms, exclusion_terms)
        print(f"Found {len(results)} matching files:")
        for file in results:
            print(f"  - {file}")
    except Exception as e:
        print(f"Error: {e}")
