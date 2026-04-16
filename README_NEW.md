# PorePythonPeople

Developing a Standardized Python-based Nanopore Data Analysis Pipeline

## Why Use PorePythonPeople?

PorePythonPeople is an open-source, Python-based tool for analyzing nanopore sequencing and tweezing data. Unlike proprietary commercial solutions, this package empowers researchers with **greater control, flexibility, and transparency** over their data analysis workflows.

### Key Advantages

- **Code Sharing & Standardization**: Centralized repository eliminates isolated code islands, ensuring standardized analysis across your lab and collaborators
- **Greater Customizability**: Customizable Python implementation enables tailoring of analysis methods to specific experimental parameters and needs
- **Publication-Ready Pipeline**: Provides a complete, reproducible endpoint for publishing research results with full methodological transparency
- **Environmental Management**: Locks specific package versions to prevent unwanted upgrades and ensure reproducible results across different systems and time periods
- **Open Source**: Transparent development with little to no proprietary restrictions

## What Can You Do With PorePythonPeople?

PorePythonPeople enables researchers to:

- **Search Large Databases**: Navigate and filter through nanopore sequencing data by experimental conditions (p10+ yH, buffer concentration, pore direction, enzyme type, temperature, voltage, etc.)
- **Plot & Compare Data**: Overlay nanopore trace data from selected experiments to identify trends and compare results across conditions
- **Detect & Classify Events**: Interactive event detection and classification tool to streamline identification of transitions, state changes, and anomalies in trace data
- **Visualize Raw Traces**: Comprehensive plotting and analysis tools with interactive matplotlib figures for detailed data examination

Example data can be found in `tests/ExampleDataGit`

Before using this software, ensure that files adhere to the naming convention defined below. 

## Installation

### Prerequisites

- Python 3.7 or higher
- pip (Python package manager)

### Quick Install

1. **Clone the repository** (or download the source code):
```bash
git clone https://github.com/your-username/PorePythonPeople.git
cd PorePythonPeople
```

2. **Install the package** using pip:
```bash
pip install -e .
```

This command installs PorePythonPeople and all required dependencies in development mode, allowing you to make modifications if needed.

### Required Dependencies

The package automatically installs the following dependencies:

- **numpy**: Numerical computing and array operations
- **matplotlib**: Data visualization and plotting
- **h5py**: HDF5 file format support for MATLAB v7.3 files
- **scipy**: Scientific computing (MAT file compatibility)
- **pytest**: Testing framework (development)
- **pytest-cov**: Code coverage reporting (development)

## Getting Started

#### **Data Navigator GUI**
The primary user interface for searching and selecting data files. This is the main entry point for most users.

**Key Features:**
- **Database Directory Selection**: Browse and select your nanopore data folder (saved for future sessions)
- **Logs Directory Selection**: Choose where search results and logs are stored
- **Cumulative Search**: Perform multiple searches that add to your selection (don't clear previous results), allowing you to build up complex selections across multiple queries
- **File Selection Toggle**: Click any file in the list to select/deselect it:
  - **Selected files** appear at the top with a green background and checkmark ✓
  - **Unselected files** appear below without highlighting
- **Quick Selection Tools**:
  - **Search Button**: Filter files by inclusion and exclusion terms
  - **Select All Button**: Quickly select all available files
  - **Clear Selection Button**: Deselect all files
  - **Confirm Search Button**: Finalize your selection and create a dated search log
- **Live Log Display**: Real-time logging of all actions with timestamps for troubleshooting and reference

**How to Use the Data Navigator GUI:**
1. Run the application (see "How to Run" section below)
2. Browse and select your database directory (containing your nanopore data folders)
3. Browse and select your logs directory (where search results will be saved)
4. Enter inclusion terms (comma-separated) - files must contain ALL of these terms
5. Enter exclusion terms (comma-separated) - files containing ANY of these are removed
6. Click "Search" to filter the file list
7. Manually click files to toggle selection (or use "Select All"/"Clear Selection")
8. Repeat steps 4-7 to perform cumulative searches if needed
9. Click "Confirm Search" to create a timestamped search log with your selected files

#### **Event Classifier GUI**
The analysis and visualization interface for examining selected data files.

**Key Features:**
- **Browse Search Logs**: Navigate to and select from previous search result directories
- **Query Selection**: Dropdown menu to select which search query results to analyze
- **File Viewer**: List of files within your selected search query
- **Data Plotting**: 
  - Automatically loads and plots reduced data traces from MATLAB/HDF5 files
  - X-axis: Point index (data points)
  - Y-axis: Current (picoamperes)
- **Interactive Matplotlib Toolbar**: Professional plotting controls including:
  - **Zoom**: Click and drag to zoom into regions of interest
  - **Pan**: Move around the plot to explore different sections
  - **Home**: Reset the plot to original view
  - **Back/Forward**: Navigate through your zoom/pan history
  - **Save**: Export the plot as an image file
- **Event Detection & Classification** (coming soon): Tools for identifying and classifying events in the trace data
- **Error Logging**: Detailed error messages and operation logs for troubleshooting

**How to Use the Event Classifier GUI:**
1. Run the application (see "How to Run" section below)
2. Browse to your logs directory (where search results are stored)
3. Select a search query from the dropdown menu
4. Select a file from the list to view
5. Use the interactive toolbar to zoom, pan, and explore the trace data
6. Use the plotting tools to analyze event characteristics and compare multiple traces

## How to Run

### Option 1: Run from Terminal (Recommended)

```bash
# Navigate to the project directory
cd /path/to/PorePythonPeople

# Activate your Python environment (if using venv/conda)
# conda activate myenv  # or source venv/bin/activate

# Run the Data Navigator GUI (main interface for selecting data)
python -m src.nanoporethon.subcomponent_4_data_navi_gui

# OR run the Event Classifier GUI (for analyzing selected data)
python -m src.nanoporethon.subcomponent_5_event_classifier_gui
```

### Option 2: Run Python Script Directly

```bash
# Data Navigator GUI
python src/nanoporethon/subcomponent_4_data_navi_gui.py

# Event Classifier GUI
python src/nanoporethon/subcomponent_5_event_classifier_gui.py
```

### Standard Workflow

1. **First Time Setup**:
   - Run the **Data Navigator GUI**
   - Select your database directory (folder containing all your nanopore data)
   - Select your logs directory (where search results will be saved)

2. **Search & Select Data**:
   - Use inclusion/exclusion filters to find relevant files
   - Manually select specific files by clicking them
   - Confirm your selection (creates a timestamped log)

3. **Analyze Data**:
   - Run the **Event Classifier GUI**
   - Select your logs directory
   - Choose a previously created search query
   - Select files and analyze the trace data using interactive plotting tools

## File Format Requirements

### Database File Naming Convention

Files in your database directory should follow this naming convention:

```
YYMMDDX_PPPPN_CONDITIONS_pVVVY
```

Where:
- **YYMMDD**: Date in year-month-day format
- **X**: Single letter station identifier
- **PPPP**: Pore name (e.g., 2NNN, 3AAA)
- **N**: Pore number
- **CONDITIONS**: Experimental conditions separated by "&" (e.g., `t1&pH7.5&500mM&streptavidin`)
- **pVVV**: Applied voltage with "p" prefix (e.g., `p180` for 180mV, `p060` for 60mV)
- **Y**: File letter/identifier

**Example**: `250101a_2NNN1_t1&pH7.5&streptavidin&100mM_p180a`

### Data File Formats

The Event Classifier GUI supports:
- **MATLAB `.mat` files** (v7.3 HDF5 format, using h5py)
- **NumPy arrays** (through scipy.io.loadmat compatibility)

Required files in your data folders:
- `reduced.mat`: Preprocessed current trace data
- `event.mat`: Event detection results
- `meta.mat`: Experiment metadata (sampling frequency, etc.)

## Example Use Cases

### Scenario 1: Comparing pH Effects on Motor Protein Activity
1. Open Data Navigator GUI
2. Search for files containing: `streptavidin` and `motor_enzyme_name`
3. Exclude results containing: `broken_pore`
4. Manually select files from pH7.0, pH7.5, and pH8.0 (cumulative search approach)
5. Confirm selection → creates timestamped log
6. Open Event Classifier GUI
7. Select your search query
8. Compare traces across different pH conditions using interactive plotting

### Scenario 2: Validating a New Enzyme Variant
1. Open Data Navigator GUI
2. Search for: `variant_name` AND `pore_type` 
3. Exclude: `failed` AND `preliminary`
4. Use "Select All" to include all passing experiments
5. Confirm selection
6. Analyze all variants together in Event Classifier


## Screenshots

<img width="1470" height="917" alt="Screenshot 2026-03-12 at 4 03 30 PM" src="https://github.com/user-attachments/assets/1e9b6b72-5cee-48db-aa7a-eaa6eab9378a" />

<img width="1470" height="918" alt="Screenshot 2026-03-12 at 4 05 02 PM" src="https://github.com/user-attachments/assets/4d21f391-f171-4932-bd69-586ad21a3433" />

## Troubleshooting

### Common Issues

**Q: "ModuleNotFoundError: No module named 'nanoporethon'"**
- **Solution**: Make sure you've installed the package with `pip install -e .` from the project root

**Q: GUI doesn't respond or appears frozen**
- **Solution**: This is usually a matplotlib backend issue. Try updating matplotlib: `pip install --upgrade matplotlib`

**Q: "Database directory does not exist"**
- **Solution**: Select a valid directory path in the Data Navigator GUI. Check that the path exists and you have read permissions

**Q: Files not appearing in the list**
- **Solution**: Verify files match your inclusion/exclusion criteria. Use "Clear Selection" and perform a new search with broader terms

**Q: Cannot load MAT files**
- **Solution**: Ensure files are in HDF5 format (MATLAB v7.3+). Older MATLAB format requires scipy conversion

## Contributing

Please reach out to the Gundlach lab at the University of Washington to discuss possible avenues for collaboration.

## License

See [LICENSE](LICENSE) file for details.

## Support & Contact

For questions, issues, or suggestions, please open an issue on the GitHub repository.

## Acknowledgments

This tool was built by the Gundlach Lab with input from collaborators, with specific contributions from Zach Seitz, Daniel Mendoza, Riya Patel, Yukun Li, and Tobias Rangel-Guillen. This tool aims to standardize nanopore sequencing analysis within the group.
