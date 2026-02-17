"""
Data Navigator GUI using PySimpleGUI.

Features:
- Scan a directory for files matching the project's naming scheme
- Parse filename metadata (date, station, pore name/number, conditions, voltage, letter)
- Filter by search tokens (comma/space-separated)
- Select/deselect files (multi-select list)
- Export selected file list to JSON or CSV

Requires: PySimpleGUI (pip install PySimpleGUI)
"""

import re
import os
import json
import csv
import PySimpleGUI as sg
from typing import List, Dict, Optional

FILENAME_REGEX = re.compile(
    r'^(?P<date>\d{6})(?P<station>[A-Za-z])_(?P<pore_name>[A-Za-z0-9]+)(?P<pore_number>\d+)_'
    r'(?P<conds>t[^_]+)_p(?P<vol>\d{3})(?P<letter>[A-Za-z])$'
)


def parse_filename(filename: str) -> Optional[Dict]:
    name = os.path.splitext(filename)[0]
    m = FILENAME_REGEX.match(name)
    if not m:
        return None
    groups = m.groupdict()
    conditions = groups['conds']
    # conditions start with 't', split on '&' and strip leading 't' from first
    cond_parts = conditions.split('&')
    if cond_parts and cond_parts[0].startswith('t'):
        cond_parts[0] = cond_parts[0][1:]
    return {
        'raw': filename,
        'date': groups['date'],
        'station': groups['station'],
        'pore_name': groups['pore_name'],
        'pore_number': groups['pore_number'],
        'conditions': cond_parts,
        'voltage_mV': int(groups['vol']),
        'file_letter': groups['letter'],
    }


def scan_directory(directory: str, extensions: Optional[List[str]] = None) -> List[Dict]:
    if extensions is None:
        extensions = ['.abf', '.txt', '.dat', '.csv', '.bin']  # common data file ext guesses
    files = []
    try:
        for fname in sorted(os.listdir(directory)):
            if os.path.isdir(os.path.join(directory, fname)):
                continue
            if extensions and not any(fname.lower().endswith(ext) for ext in extensions):
                continue
            meta = parse_filename(fname) or {'raw': fname}
            files.append(meta)
    except Exception:
        files = []
    return files


def match_query(meta: Dict, tokens: List[str]) -> bool:
    if not tokens:
        return True
    hay = []
    # searchable fields
    hay.append(meta.get('raw', ''))
    for k in ('date', 'station', 'pore_name', 'pore_number', 'file_letter'):
        v = meta.get(k)
        if v:
            hay.append(str(v))
    for cond in meta.get('conditions', []):
        hay.append(cond)
    hay_text = ' '.join(hay).lower()
    return all(t.lower() in hay_text for t in tokens)


def filter_files(files: List[Dict], query: str) -> List[Dict]:
    tokens = [t.strip() for t in re.split(r'[,\s]+', query) if t.strip()]
    return [f for f in files if match_query(f, tokens)]


def export_selected(selected: List[Dict], path: str):
    ext = os.path.splitext(path)[1].lower()
    if ext == '.json':
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(selected, fh, indent=2)
    else:
        # default CSV
        keys = ['raw', 'date', 'station', 'pore_name', 'pore_number', 'conditions', 'voltage_mV', 'file_letter']
        with open(path, 'w', newline='', encoding='utf-8') as fh:
            writer = csv.writer(fh)
            writer.writerow(keys)
            for s in selected:
                writer.writerow([s.get(k) if k != 'conditions' else '&'.join(s.get('conditions', [])) for k in keys])


def launch_gui(initial_dir: str = '.'):
    sg.theme('SystemDefault')
    layout = [
        [sg.Text('Database directory:'), sg.Input(initial_dir, key='-DIR-'), sg.FolderBrowse()],
        [sg.Text('Search tokens (comma or space separated):'), sg.Input(key='-QUERY-'), sg.Button('Filter')],
        [sg.Button('Rescan'), sg.Button('Select All'), sg.Button('Deselect All'),
         sg.Button('Export Selected'), sg.Button('Close')],
        [sg.Text('Matching files:' )],
        [sg.Listbox(values=[], size=(80, 15), key='-LIST-', select_mode=sg.LISTBOX_SELECT_MODE_MULTIPLE, enable_events=True)],
        [sg.Text('Selected file metadata preview:')],
        [sg.Multiline('', size=(80, 8), key='-PREVIEW-', disabled=True)],
    ]

    window = sg.Window('Data Navigator', layout, finalize=True)
    files = scan_directory(initial_dir)
    window['-LIST-'].update([f['raw'] for f in files])

    while True:
        event, values = window.read()
        if event in (sg.WIN_CLOSED, 'Close'):
            break
        if event == 'Rescan':
            directory = values['-DIR-'] or initial_dir
            files = scan_directory(directory)
            window['-LIST-'].update([f['raw'] for f in files])
            window['-PREVIEW-'].update('')
        elif event == 'Filter' or event == '-QUERY-':
            directory = values['-DIR-'] or initial_dir
            files = scan_directory(directory)
            q = values['-QUERY-'] or ''
            filtered = filter_files(files, q)
            window['-LIST-'].update([f['raw'] for f in filtered])
            window['-PREVIEW-'].update('')
        elif event == 'Select All':
            window['-LIST-'].update(set_to_index=list(range(len(window['-LIST-'].get_list_values()))))
        elif event == 'Deselect All':
            window['-LIST-'].update(set_to_index=[])
            window['-PREVIEW-'].update('')
        elif event == '-LIST-':
            sel = values['-LIST-']
            if not sel:
                window['-PREVIEW-'].update('')
                continue
            # show preview of first selected
            sel_name = sel[0]
            meta = next((f for f in files if f.get('raw') == sel_name), {'raw': sel_name})
            pretty = json.dumps(meta, indent=2)
            window['-PREVIEW-'].update(pretty)
        elif event == 'Export Selected':
            sel = values['-LIST-']
            if not sel:
                sg.popup('No files selected')
                continue
            selected_meta = [next((f for f in files if f.get('raw') == s), {'raw': s}) for s in sel]
            save_path = sg.popup_get_file('Save selected', save_as=True, no_window=True, file_types=(('JSON','*.json'),('CSV','*.csv')))
            if save_path:
                try:
                    export_selected(selected_meta, save_path)
                    sg.popup('Exported to', save_path)
                except Exception as e:
                    sg.popup('Export failed:', str(e))

    window.close()


if __name__ == '__main__':
    # default to project folder; change as needed
    launch_gui(os.path.abspath('.'))
    