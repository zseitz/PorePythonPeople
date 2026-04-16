# NanoporethonArchitecture - Subcomponent Guide

## Overview
The nanoporethon subcomponents have been organized to reduce code redundancy and improve separation of concerns. Each subcomponent has a single, well-defined responsibility following a layered architecture pattern:

- **Layer 1: Core Operations** (SC1-SC3) - Data processing and filtering
- **Layer 2: Shared Utilities** (SC4-SC7) - Reusable infrastructure and data loading
- **Layer 3: GUI Applications** - High-level interfaces that delegate to lower layers

---

## Architectural Layers

### Layer 1: Core Operations
Core functionality components that perform specific data processing tasks.

---

## Subcomponent 1: Prompt User

**File:** `subcomponent_1_prompt_user.py`  
**Size:** ~60 lines

*Description:* Using a GUI, prompt the user for the path to the directory containing data. Save the path to a global string variable named `database_directory`.

*Input:*
- File path

*Output:*
- `database_directory` variable (global variable accessible by other functions)

*Key Function:*
- `prompt_user()` - Opens dialog to select database directory

---

## Subcomponent 2: Data Navigator

**File:** `subcomponent_2_data_navigator.py`  
**Size:** ~50 lines

*Description:* Create a function called `data_navi` that takes in as input 2 lists or arrays containing strings, and the string `database_directory`. The function should also prompt the user for the name to be associated with a specific search query. The strings in the input lists `Array_1` and `Array_2` have the following format:

- String with 4 components delimited by "_"
  - Component 1: Date + Station letter
    - Date is formatted "YYMMDD"
    - Station letter is a lowercase character
  - Component 2: Pore Name + Pore Number
    - Pore Name is a string
    - Pore Number is an integer value in string form
  - Component 3: Series of condition strings delimited by "&" of varying length
    - Ex: `t1&streptavidin&100mM100mM`
  - Component 4: Applied voltage + file letter
    - For applied voltage, the format is "p" + a 3 character string. The voltage will not exceed 3 characters. If the voltage is less than 100mV, say for 60mV, then the applied voltage will read "p060". If say 6mV, then "p006".
    - File letter is a few characters

Example string: `250101g_2NNN1_t1&streptavidin&100mM100mM_p180a`
- "250101" is the date in the format YYMMDD
- the "g" following the date refers to station letter with no spaces
- "2NNN" is the pore name
- the "1" following the "2NNN" is the pore number with no spaces
- the "t1&streptavidin&100mM100mM" contains strings separated by "&" that explain the conditions of this experiment
- "p180" refers to applied voltage or "pipette offset 180 mV"
- The final letter "a" is the file letter.

*Inputs:*
- `Array_1`: List or array of strings that `data_navi` should find within the filenames in the `database_directory`. If all the strings in `Array_1` are present in the filename, it should add the filename to an array named `filenames_out`.
- `Array_2`: List or array of strings that `data_navi` will find within the filenames in the `filenames_out` array and remove those filenames from the array.
- `query_name` (optional): User-provided name for the search query (prompted in GUI or passed as parameter).

*Outputs:*
- Returns the `filenames_out` array

*Key Function:*
- `data_navi(database_directory, array_1, array_2) -> List[str]` - Filters files based on inclusion/exclusion criteria

---

## Subcomponent 3: Data Navi Sub Directory

**File:** `subcomponent_3_data_navi_sub_directory.py`  
**Size:** ~130 lines

*Description:* Creates a new timestamped directory in the user-specified logs directory. The name of the new folder begins with the search query name supplied by the user in subcomponent 2, followed by the current date and time in the format `YYYYMMDD_hh:mm:ss`. A text log is written documenting the inclusion/exclusion arrays and the list of selected files (without copying the actual files to save storage space).

*Inputs:*
- `source_directory` (str): Path to the database root.
- `filenames_out` (list): Names/paths of selected files or folders.
- `destination_parent_directory` (str): The logs directory where the query folder will be created.
- `query_name` (str): User-provided identifier for this search.
- `array_1` (list): Inclusion filter list.
- `array_2` (list): Exclusion filter list.

*Outputs:*
- None (creates a new folder with a log file listing the selected files and metadata)

*Key Function:*
- `data_navi_sub_directory(...)` - Creates timestamped directories and logs search queries

---

### Layer 2: Shared Utilities
Reusable utility subcomponents that provide cross-cutting functionality.

---

## Subcomponent 4: Config Manager

**File:** `subcomponent_4_config_manager.py`  
**Size:** ~80 lines

*Description:* Handles persistent configuration storage for directory paths. Provides a centralized single-source-of-truth for user preferences that persist across sessions.

*Responsibilities:*
- Load/save configuration from JSON file (`.nanoporethon_config.json`)
- Manage database and logs directory paths
- Provide atomic config operations

*Key Functions:*
- `load_config()` - Loads config from JSON file
- `save_config(dict)` - Saves config to JSON file
- `get_config_value(key)` - Gets a config value
- `set_config_value(key, val)` - Sets a config value
- `get_database_directory()` / `set_database_directory()` - Directory-specific helpers
- `get_logs_directory()` / `set_logs_directory()` - Directory-specific helpers

*Used by:*
- DataNaviGUI
- EventClassifierGUI

---

## Subcomponent 5: Directory Utilities

**File:** `subcomponent_5_directory_utilities.py`  
**Size:** ~70 lines

*Description:* Provides common directory selection and validation functions. Thin wrapper around tkinter filedialog with caching via SC4.

*Responsibilities:*
- Prompt user for directory selection via native file dialog
- Cache directory selections using SC4
- Validate directory existence

*Key Functions:*
- `browse_for_directory(title)` - Opens directory browser dialog
- `select_database_directory()` - Select and cache database directory
- `select_logs_directory()` - Select and cache logs directory

*Delegation:*
- Uses SC4 (Config Manager) for caching selections

*Used by:*
- DataNaviGUI
- EventClassifierGUI

---

## Subcomponent 6: Search Log Utilities

**File:** `subcomponent_6_search_log_utilities.py`  
**Size:** ~40 lines

*Description:* Parses and loads search log files created by SC3. Extracts metadata and file listings from search query logs.

*Responsibilities:*
- Parse search log file format
- Extract source directory and selected files
- Find available search queries in a directory

*Key Functions:*
- `load_search_log(log_file_path)` - Loads search log and returns metadata and file list
- `find_search_queries(directory)` - Finds all search query directories in a location

*Used by:*
- EventClassifierGUI

---

## Subcomponent 7: MAT File Loader

**File:** `subcomponent_7_mat_file_loader.py`  
**Size:** ~420 lines

*Description:* Loads and parses MATLAB files (reduced.mat, event.mat, meta.mat) with robust extraction and multiple fallback strategies. Handles both HDF5 (h5py) and non-HDF5 (scipy.io) MAT file formats.

*Responsibilities:*
- Load MATLAB files in different formats
- Extract nested data with case-insensitive key matching
- Resolve object references
- Provide fallback loading strategies
- Handle numeric extraction from various data types

*Key Functions:*
- `load_reduced_mat(path)` - Loads reduced.mat file and returns data arrays
- `load_event_data(path)` - Loads event data from event.mat
- `load_fsamp_from_event_mat(path)` - Extracts sampling frequency from event.mat
- `load_fsamp_from_meta_mat(path)` - Extracts sampling frequency from meta.mat

*Internal Helpers:*
- `_safe_get_scalar()` - Safely extract scalar values
- `_normalize_key()` - Case-insensitive key matching
- `_extract_numeric_from_dataset()` - Extract numbers from datasets
- `_load_event_vector()` - Load event data vectors
- `_mat_extract_numeric_vector()` - Extract numeric vectors

*Features:*
- Case-insensitive key matching for robustness
- Object reference resolution
- Nested group searching
- Multiple fallback loading paths
- Proper handling of different data types

*Used by:*
- EventClassifierGUI

---

### Layer 3: GUI Applications
High-level GUI applications that delegate to lower layers.

---

## Subcomponent 4: DataNaviGUI

**File:** `data_navi_gui.py`  
**Size:** ~340 lines

*Description:* Creates a GUI using tkinter. This GUI-based application (DataNaviGUI) utilizes subcomponents 2 and 3 for navigating and managing the database. The GUI manages two persistent directories:

1. **Database Directory**: The directory containing data files to search through. If a directory was previously selected (saved from a prior session), it automatically loads that directory, provided it still exists. The user can change this directory at any time using the "Browse" button next to "Database Directory".

2. **Logs Directory**: The directory where search query logs will be saved. On first run (or if not previously set), the user is prompted to select a logs directory. This selection is saved and reused in future sessions. The user can change this directory at any time using the "Browse" button next to "Logs Directory".

Once valid directories are selected, the GUI displays a menu where the user can:
- Enter inclusion and exclusion search terms (Array_1 and Array_2) and click "Search" to filter files. **Multiple searches can be performed cumulatively**: each new search adds matching files to the current selection without clearing previously selected files. This allows for building up a selection across multiple queries, accommodating inconsistent naming schemes.
- Click on files in the list to toggle their selection state: **clicking an unselected file selects it** (adds a ✓ checkmark, highlights with green background, and moves it to the top), and **clicking a selected file deselects it** (removes the checkmark and highlighting, and moves it to the bottom). Selected files are always displayed at the top of the list in alphabetical order, separated from unselected files below, with clear visual highlighting.
- Click "Select All" to select all files or "Clear" to deselect all files.
- Click "Confirm Search" to finalize the selection. This prompts the user for:
  - A name to associate with the search query (used to label the output directory).
  - The function then creates a folder at `<logs_directory>/<query_name>_YYYYMMDD_hh:mm:ss/` containing a log file with the list of selected files and search metadata (files are not copied to save storage).
  - **Upon successful completion, the GUI exits automatically.**

The GUI maintains a log of all operations (search, selection, confirmation, errors, etc.) with timestamps.

*Workflow:*
Select database → Enter search criteria → View/select files → Confirm search

*Responsibilities:*
- GUI layout and user interactions
- Search workflow orchestration
- Logging/messaging

*Delegates to:*
- SC4 (Config Manager)
- SC5 (Directory Utilities)
- SC2 (Data Navigator) for filtering
- SC3 (Data Navi Sub Directory) for logging

*Key Behaviors:*
- The search operation does **not** prompt in the terminal; it only uses the GUI.
- Both database and logs directories are persisted to a config file (`.nanoporethon_config.json`) so they are remembered across sessions.
- If either directory no longer exists (e.g., on a different system or after deletion), the user is prompted to select one.
- The user can change either directory at any point during the session using the respective Browse buttons.
- **Cumulative searches**: Subsequent searches add to the existing selection, allowing users to include files that may not match the initial query due to naming inconsistencies.
- **Toggle selection**: Click any file in the list to toggle between selected (with ✓ checkmark, at top) and unselected (no checkmark, at bottom). Single-click interaction makes the selection process intuitive.
- **Sorted list**: Selected files appear at the top of the file list in alphabetical order with green highlighting, making it easier to see and manage the current selection.
- **Storage efficient**: Only a log file is created in the logs directory with the list of selected files and metadata; actual data files are not copied to avoid wasting storage space.
- **No subdirectories**: Query folders are created directly in the logs directory without intermediate subdirectories.

*Inputs:*
None

*Outputs:*
None (GUI creates directories and log files via SC3)

---

## Subcomponent 5: EventClassifierGUI

**File:** `event_classifier_gui.py`  
**Size:** ~750 lines (reduced from ~1100+)

*Description:* Creates a GUI using tkinter. This GUI-based application utilizes the search results generated by DataNaviGUI to assist with classifying events in the data. The GUI allows the user to browse to and select a search logs directory (the directory where DataNaviGUI saved search query logs). Once a search logs directory is selected, the GUI displays available search queries found in that directory as timestamped folders. When a query is selected, it loads the list of selected files from the search log. The user can then select a file to view its data. Each selected file is a folder containing MAT files; clicking on a file loads and plots `reduced.data` vs `reduced.pt` (point index) using matplotlib.

*Workflow:*
Select logs directory → Select query → Select file → View/edit events

*Responsibilities:*
- GUI layout and user interactions
- Event visualization and navigation
- Event quality editing
- Keyboard shortcuts

*Delegates to:*
- SC4 (Config Manager)
- SC5 (Directory Utilities)
- SC6 (Search Log Utilities) for log parsing
- SC7 (MAT File Loader) for data loading

*Key Features:*
- Flexible directory selection: Users browse to any directory containing search logs created by DataNaviGUI.
- Query selection: Dropdown to choose from search query directories found in the selected logs directory.
- File selection: Listbox showing files from the selected query.
- Data plotting: Loads MAT file data and plots the specified fields in an embedded matplotlib figure.
- Interactive toolbar: Provides zoom, pan, home (reset), back/forward navigation, and save functionality similar to MATLAB figures.
- Exit button: Easily close the application from the GUI.
- Error handling: Logs issues with loading files or data.

*Inputs:*
None (reads from config and logs directory)

*Outputs:*
None (displays plots in GUI)

---

## Dependencies and Data Flow

### DataNaviGUI Dependency Tree
```
DataNaviGUI
├── SC4 (Config Manager)
├── SC5 (Directory Utilities)
│   └── SC4 (Config Manager)
├── SC2 (Data Navigator)
└── SC3 (Data Navi Sub Directory)
```

### EventClassifierGUI Dependency Tree
```
EventClassifierGUI
├── SC4 (Config Manager)
├── SC5 (Directory Utilities)
│   └── SC4 (Config Manager)
├── SC6 (Search Log Utilities)
└── SC7 (MAT File Loader)
```

---

## Code Reuse Benefits

### Before Refactoring
- Config management duplicated in DataNaviGUI and EventClassifierGUI (~40 lines each)
- Directory selection logic duplicated in DataNaviGUI and EventClassifierGUI (~35 lines each)
- All MAT file loading logic (~700 lines) in EventClassifierGUI only
- Search log parsing logic in EventClassifierGUI only
- **Total code duplication: ~900+ lines**

### After Refactoring
- SC4 provides single config implementation (~80 lines) used by both GUIs
- SC5 provides single directory selection implementation (~70 lines) used by both GUIs
- SC7 provides reusable MAT file loading (~420 lines) available to future components
- SC6 provides reusable log parsing (~40 lines) available to future components
- **Eliminated ~400+ lines of redundant code**
- **Improved maintainability**: Changes to config or directory logic only need to be made once

---

## Testing Strategy

The test file (`test_nanoporethon.py`) tests each subcomponent independently using mock objects and unit tests.

### Key Test Coverage
- **SC1**: User prompting functionality
- **SC2**: File filtering with various inclusion/exclusion patterns
- **SC3**: Log file creation and format validation
- **SC4**: Configuration save/load/clear operations
- **SC5**: Directory selection caching
- **SC6**: Search log parsing
- **SC7**: MAT file loading from various formats
- **DataNaviGUI**: Directory browsing, search workflow, file selection
- **EventClassifierGUI**: Query loading, file loading, event data parsing, quality saving

### Test Execution
```bash
pytest tests/test_nanoporethon.py -v
```

---

## Future Extensibility

The new architecture makes it easy to:

1. **Add new data loading formats** - Extend SC7 with new parsers or file types
2. **Create new GUIs** - Reuse SC4 and SC5 for any GUI that needs config and directory selection
3. **Add new file formats to search logs** - Extend SC6 for new metadata formats
4. **Improve config management** - Update SC4 without affecting GUIs
5. **Create batch processing tools** - Use the utility subcomponents (SC4-SC7) for automation
6. **Add new event parsers** - Extend SC6 to handle different log formats
7. **Support additional file formats** - SC7 can be extended to load additional data types

---

## Migration Notes

### For Users
- No changes to user-facing behavior
- All existing workflows work identically
- Configuration files remain compatible (.nanoporethon_config.json)

### For Developers

When adding new features:

1. **Check if similar functionality exists in layers 1-2** - Reuse before reimplementing
2. **Prefer extending existing utilities over duplicating code** - Add to SC4-SC7 rather than duplicating
3. **Keep GUI components focused on UI logic** - Offload data processing to layer 2 utilities
4. **Extract reusable functionality to lower layers** - If two GUIs need the same logic, create a utility

#### Import Path Updates
All subcomponents are in `src.nanoporethon.*`:
```python
from src.nanoporethon import subcomponent_1_prompt_user
from src.nanoporethon import subcomponent_2_data_navigator
from src.nanoporethon import subcomponent_3_data_navi_sub_directory
from src.nanoporethon import subcomponent_4_config_manager
from src.nanoporethon import subcomponent_5_directory_utilities
from src.nanoporethon import subcomponent_6_search_log_utilities
from src.nanoporethon import subcomponent_7_mat_file_loader
from src.nanoporethon import data_navi_gui
from src.nanoporethon import event_classifier_gui
```

---

## Dependencies

The following Python packages are required to run the subcomponents:

- `scipy`: For potential MAT file loading compatibility
- `matplotlib`: For plotting data in EventClassifierGUI
- `h5py`: For loading MATLAB v7.3 HDF5 format MAT files in SC7
- `numpy`: For data array operations across all components
- `tkinter`: For GUI components (usually included with Python)

Install them using pip:
```bash
pip install scipy matplotlib h5py numpy
```

Or install all dependencies from the project:
```bash
pip install -e .
```
