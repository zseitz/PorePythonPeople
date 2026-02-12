## Components

# Component #1: Data Navigator
* finds data files from database based on metadata (enzyme, buffer, atp conc, etc)
* gui that takes user input to build subset of database
* allows for general searches for variables/dates/etc as well as manual 
* clear explanation for naming convention, and how to locate specific variables

# Component #2: event classifier - already exists in matlab pretty well
 * gui to visualize raw traces
 * classifies good events vs bad events

# Component #3: level finder- neural network to automatically identify levels
* gui (maybe same component as component #2?) that identifies levels in good events
* needs high manipulatability for different experiments

## Use Cases

# Use case #1: 
* pulls ranges of data from database by searching or manual selecting of metadata/variables

# Use case #2: 
* sequences known or unknown DNA/RNA (ID potential tech improvements, or expanded alphabet experiments)

# Use case #3: 
* compares motor enzyme function across variables (buffer, atp conc, pH, temperature, etc)

# Use case #4: 
* for non-enzymatic experiments (sensing experiments, bond ruptures, etc)
