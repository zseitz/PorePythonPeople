# PorePythonPeople
Developing python based Nanopore Sequencing/Tweezing analysis pipeline

The first function that we will try to port into Python from MATLAB will be the eventclassifier function.

This code takes preprocessed sequencing data (Current in picoamperes, by points) which can be converted to current 
by time assuming that we know what the sampling frequency was set to at the time of recording data. In general, sampling
frequency, or "fsamp" as it is commonly referred to in this script, should be 10kHz. This means that for every 10k points,
1 second goes by.
