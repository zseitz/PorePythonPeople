# Components
## Data_Navigator

**Subcomponent 1:**

## Prompt_User
*Description:* using a GUI, ask the user for the path to the directory containing data. Save the path to a global string variable named, database_directory. 
*Input:*
File path
*Output:* 
database_directory variable (should be a global variable accessible by other functions)


**Subcomponent 2:**

## Data_Navigator
*Description:* Create a function called DataNavi that takes in as input 2 lists or arrays containing strings, and the string, _database\_directory_. The strings in the input lists Array\_1 and Array\_2 have the following format:

Output of this function should be a list of files in User_Selected_Files within the database which are of interest to the user as selected through their searches and manual selections, and the list will be used with proceeding components for data analysis.



  - String with 4 components delimited by “\_”

    - Component 1: Date + Stationletter

      - Date is formatted “YYMMDD”

      - Stationletter is a lowercase character

    - Component  2: Pore Name + Pore Number

      - Pore Name is a string?

      - Pore Number is an integer value in string form

    - Component  3: series of condition strings delimited by “&” of varying length

      - Ex: t1\&streptavidin&100mM100mM

    - Component 4: applied voltage + file letter

      - For applied voltage, the format is “p” + a 3 character string. The voltage will not exceed 3 characters. If the voltage less than 100mV, say for 60mV, then the applied voltage will read "p060". If say 6mV, then “p006”.

      - File letter is a few characters

  - Example string: "250101g\_2NNN1\_t1\&streptavidin&100mM100mM\_p180a" 

    - "250101" is the date in the format YYMMDD

    - the "g" following the date refers to station letter with no spaces

    - "2NNN" is the pore name 

    - the "1" following the "2NNN" is the pore number with no spaces

    - the "t1\&streptavidin&100mM100mM" contains strings separated by "&" that explain the conditions of this experiment

    - "p180" refers to applied voltage or "pipette offset 180 mV"

    - The final letter "a" is the file letter. 

*Inputs:*

    - Array\_1 - list or array of strings that DataNavi should find within the file\_names in the data\_base\_directory and if all the strings in array\_1 are present in the file\_name, it should add the file\_name to an array named, _filenames\_out_, that will be the output of the function.

    - array\_2 - list or array of strings that DataNavi will find within the file names in the _filenames\_out_ array created with Array\_1 and will remove those filenames from the _filenames\_out_ array

*Outputs:*

    - Returns the _filenames\_out_ array


**Subcomponent 3**

## DataNaviSubDirectory
*Description:* Takes files in _filenames\_out_ array created by DataNavi function, and copies the data files from the source directory to a new directory with title of current date and time in format ‘DD/MM/YYYY_hh:mm:ss’ and includes a text file containing the exact input search query being Array\_1 and array\_2

*Inputs:* source directory folder as a string, filenames\out array with names of directories containing relevant data

Outputs: none, saves a copy of files to new directory and creates a new text file
**Subcomponent 4**

## DataNaviGUI
* Description:* Creates a gui using PyGui that takes user input (Prompt_User) to select a directory containing data. Once, a valid directory is selected, (should prompt the user to re-enter a directory path if invalid directory inputted), should open a menu where the user can click a button to select files in that directory. The gui should have a space to input Array\_1 and array\_2, and the DataNavi function should be called after clicking a search button and Array\_1 field is filled. If array\_2 is not filled, assume an empty array. Once the user has submitted their entry, prompt the user for the new filepath to save the new directory created from DataNaviSubDirectory.  


User should be able to search for specific strings that may be present in filenames by typing desired strings for the Initial_Search such as dates, pore names, or other conditions of the experiment, or etc as well as manually click to select or deselect files from the list of files contained in the database. 

*inputs*: none
*outputs*: none
## Event_Classifier
*Description:* Classifies good events vs bad events.

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
## Event Classifier GUI
