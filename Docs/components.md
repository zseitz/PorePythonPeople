# Components

## Data_Navigator
*Description:* Create a function called DataNavi that takes in as input 2 lists or arrays containing strings, and the string, _database\_directory_. The strings in the input lists Array\_1 and Array\_2 have the following format:

  - String with 4 components delimited by “\_”

    - Component 1: Date + Stationletter

      - Date is formatted “YYMMDD”

      - Stationletter is a lowercase character

    - Component  2: Pore Name + Pore Number

      - Pore Name is a string?

      - Pore Number is an integer value in string form

    - Component  3: series of condition strings delimited by “&” of varying length

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