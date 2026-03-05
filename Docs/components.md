# Components
## Data Navigator

**Subcomponent 1:**

## Prompt_User
*Description:* Using a GUI, prompt the user for the path to the directory containing data. Save the path to a global string variable named `database_directory`.

*Input:*
File path

*Output:*
`database_directory` variable (global variable accessible by other functions)


**Subcomponent 2:**

## Data_Navigator
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


**Subcomponent 3:**

## DataNaviSubDirectory
*Description:* Creates a new timestamped directory under a `tests` folder. The name of the new folder begins with the search query name supplied by the user in subcomponent 2, followed by the current date and time in the format `YYYYMMDD_hh:mm:ss`. A text log is written documenting the inclusion/exclusion arrays and the list of selected files (without copying the actual files to save storage space).

*Inputs:*
- `source_directory` (str): Path to the database root.
- `filenames_out` (list): Names/paths of selected files or folders.
- `destination_parent_directory` (str): The database directory where a `tests` subdirectory will be created if necessary.
- `query_name` (str): User-provided identifier for this search.
- `array_1` (list): Inclusion filter list.
- `array_2` (list): Exclusion filter list.

*Outputs:*
None (creates a new folder with a log file listing the selected files and metadata)


**Subcomponent 4:**

## DataNaviGUI
*Description:* Creates a GUI using tkinter. This GUI-based application (DataNaviGUI) utilizes subcomponents 1, 2, and 3 for navigating and managing the database. The GUI prompts the user to select a database directory on startup; if a directory was previously selected (saved from a prior session), it automatically loads that directory, provided it still exists on the current system. If the saved directory no longer exists, or if no directory has been selected yet, the user is prompted to select a new one. The user can change the database directory at any time using the "Browse" button.

Once a valid directory is selected, the GUI displays a menu where the user can:
- Enter inclusion and exclusion search terms (Array_1 and Array_2) and click "Search" to filter files. **Multiple searches can be performed cumulatively**: each new search adds matching files to the current selection without clearing previously selected files. This allows for building up a selection across multiple queries, accommodating inconsistent naming schemes.
- Click on files in the list to toggle their selection state: **clicking an unselected file selects it** (adds a ✓ checkmark, highlights with green background, and moves it to the top), and **clicking a selected file deselects it** (removes the checkmark and highlighting, and moves it to the bottom). Selected files are always displayed at the top of the list in alphabetical order, separated from unselected files below, with clear visual highlighting.
- Click "Select All" to select all files or "Clear" to deselect all files.
- Click "Confirm Search" to finalize the selection. This prompts the user for:
  - A name to associate with the search query (used to label the output directory).
  - A directory where the search log will be saved (user selects via file browser).
  - The function then creates a folder at `<selected_directory>/tests/<query_name>_YYYYMMDD_hh:mm:ss/` containing a log file with the list of selected files and search metadata (files are not copied to save storage).
  - **Upon successful completion, the GUI exits automatically.**

The GUI maintains a log of all operations (search, selection, confirmation, errors, etc.) with timestamps.

*Key Behaviors:*
- The search operation does **not** prompt in the terminal; it only uses the GUI.
- The database directory is persisted to a config file (`.datanavi_config.json`) so it is remembered across sessions.
- If the directory no longer exists (e.g., on a different system or after deletion), the user is re-prompted to select one.
- The user can change the directory at any point during the session.
- **Cumulative searches**: Subsequent searches add to the existing selection, allowing users to include files that may not match the initial query due to naming inconsistencies.
- **Toggle selection**: Click any file in the list to toggle between selected (with ✓ checkmark, at top) and unselected (no checkmark, at bottom). Single-click interaction makes the selection process intuitive.
- **Sorted list**: Selected files appear at the top of the file list in alphabetical order, making it easier to see and manage the current selection.
- **Storage efficient**: Only a log file is created in the `tests` subdirectory of the selected database directory with the list of selected files and metadata; actual data files are not copied to avoid wasting storage space.

*Inputs:*
None

*Outputs:*
None (GUI creates directories and log files via subcomponent 3)


**Subcomponent 5:**

## EventClassifierGUI
*Description:* Creates a GUI using tkinter. This GUI-based application utilizes the search results generated by subcomponent 4 to assist with classifying events in the data. The GUI allows the user to browse to and select a search logs directory (the directory where subcomponent 4 saved search query logs). Once a search logs directory is selected, the GUI displays available search queries found in that directory as timestamped folders. When a query is selected, it loads the list of selected files from the search log. The user can then select a file to view its data. Each selected file is a folder containing MAT files; clicking on a file loads and plots `reduced.vdata` vs `reduced.pt` (point index) using matplotlib.

*Key Features:*
- Flexible directory selection: Users browse to any directory containing search logs created by subcomponent 4.
- Query selection: Dropdown to choose from search query directories found in the selected logs directory.
- File selection: Listbox showing files from the selected query.
- Data plotting: Loads MAT file data and plots the specified fields in an embedded matplotlib figure.
- Interactive toolbar: Provides zoom, pan, home (reset), back/forward navigation, and save functionality similar to MATLAB figures.
- Exit button: Easily close the application from the GUI.
- Error handling: Logs issues with loading files or data.

*Inputs:*
None (reads from config and tests directory)

*Outputs:*
None (displays plots in GUI)

## Dependencies

The following Python packages are required to run the subcomponents:

- `scipy`: For potential MAT file loading compatibility.
- `matplotlib`: For plotting data in subcomponent 5.
- `h5py`: For loading MATLAB v7.3 HDF5 format MAT files in subcomponent 5.

Install them using pip:
```
pip install scipy matplotlib h5py
```
