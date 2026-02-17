# Components

## Data_Navigator
*Description:* Creates a GUI using PyGui that takes user input to build subset of database that contains many files of a consistent naming scheme. Database contains files with a consistent naming scheme that contains information on the data within those files. An example filename is "250101g_2NNN1_t1&streptavidin&100mM100mM_p180a" where "250101" is the date in the format YYMMDD, the "g" following the date refers to station letter, "2NNN" is the pore name, the "1" following the "2NNN" is the pore number, and the "t1&streptavidin&100mM100mM" contains strings separated by "&" that explain the conditions of this experiment, "p180" refers to applied voltage or "pipette offset 180 mV", and the final letter "a" is the file letter. The date, station letter, applied voltage are always the same number of characters (if less than 100mV, say for 60mV, then the applied voltage will read "p060"). The pore name, pore number, conditions of the experiment, and file letter can change number of characters. User should be able to search for specific strings that may be present in filenames by typing desired strings such as dates, pore names, or other conditions of the experiment, or etc as well as manually click to select or deselect files from the list of files contained in the database. Output of this function should be a list of files within the database which are of interest to the user as selected through their searches and manual selections, and the list will be used with proceeding components for data analysis.

*Inputs:*
- Database path (directory containing the files)

*Outputs:*
- List of selected file paths

## Event_Classifier
*Description:* A GUI to visualize raw traces and classifies good events vs bad events.

*Inputs:*
- Raw trace data

*Outputs:*
- Classified events (good/bad)

## Level_Finder
*Description:* A GUI that identifies levels in good events. Needs high manipulatability for different experiments.

*Inputs:*
- Good events data

*Outputs:*
- Identified levels in events