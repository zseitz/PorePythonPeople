# PorePythonPeople
Developing python based Nanopore Sequencing/Tweezing analysis pipeline

This is an easy-to-use, Python-based tool that allows Gundlach lab members to:
- search a large database of historical data by experimental conditions
- plot and overlay nanopore trace data from selected experiments
- detect and display ‘events’ in trace data with an interactive display


The 'data navigator' component uses a GUI to take input from users about relevant data for plotting.
The 'event classifier' component takes preprocessed sequencing data (Current in picoamperes, by points) which can be converted to current by time assuming that we know what the sampling frequency was set to at the time of recording data. In general, sampling frequency, or "fsamp" as it is commonly referred to in this script, should be 10kHz. This means that for every 10k points, 1 second goes by.

<img width="1470" height="917" alt="Screenshot 2026-03-12 at 4 03 30 PM" src="https://github.com/user-attachments/assets/1e9b6b72-5cee-48db-aa7a-eaa6eab9378a" />

<img width="1470" height="918" alt="Screenshot 2026-03-12 at 4 05 02 PM" src="https://github.com/user-attachments/assets/4d21f391-f171-4932-bd69-586ad21a3433" />
