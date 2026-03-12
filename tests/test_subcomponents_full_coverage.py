import os
import sys
import runpy
import builtins
import tempfile
from unittest import mock

import pytest

# Ensure src is importable when running from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import nanoporethon.subcomponent_1_prompt_user as sub1
import nanoporethon.subcomponent_2_data_navigator as sub2
import nanoporethon.subcomponent_3_data_navi_sub_directory as sub3
import nanoporethon.subcomponent_4_data_navi_gui as sub4
import nanoporethon.subcomponent_5_event_classifier_gui as sub5


class DummyVar:
    def __init__(self, value=""):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


class DummyMenu:
    def __init__(self):
        self.commands = []

    def delete(self, *_args):
        self.commands = []

    def add_command(self, label, command):
        self.commands.append((label, command))


class DummyWidget:
    def __init__(self):
        self.menu = DummyMenu()
        self.destroyed = False

    def pack(self, *args, **kwargs):
        return None

    def bind(self, *args, **kwargs):
        return None

    def config(self, *args, **kwargs):
        return None

    def configure(self, *args, **kwargs):
        return None

    def destroy(self):
        self.destroyed = True

    def set(self, *args, **kwargs):
        return None

    def yview(self, *args, **kwargs):
        return None

    def update(self):
        return None

    def __getitem__(self, key):
        if key == "menu":
            return self.menu
        raise KeyError(key)


class DummyListbox(DummyWidget):
    def __init__(self):
        super().__init__()
        self.items = []
        self.selected_index = None

    def delete(self, start, end=None):
        self.items = []

    def insert(self, _pos, value):
        self.items.append(value)

    def size(self):
        return len(self.items)

    def itemconfig(self, *_args, **_kwargs):
        return None

    def curselection(self):
        if self.selected_index is None:
            return ()
        return (self.selected_index,)

    def get(self, idx):
        return self.items[idx]


class DummyScrolledText(DummyWidget):
    def __init__(self):
        super().__init__()
        self.text = ""

    def insert(self, _pos, value):
        self.text += value

    def see(self, *_args):
        return None


class DummyRoot(DummyWidget):
    def __init__(self):
        super().__init__()
        self.quit_called = False

    def title(self, *_args):
        return None

    def geometry(self, *_args):
        return None

    def quit(self):
        self.quit_called = True

    def mainloop(self):
        return None

    def withdraw(self):
        return None


@pytest.fixture
def patch_tk_widgets(monkeypatch):
    def patch_mod(mod):
        monkeypatch.setattr(mod.tk, 'Frame', lambda *a, **k: DummyWidget())
        monkeypatch.setattr(mod.tk, 'LabelFrame', lambda *a, **k: DummyWidget())
        monkeypatch.setattr(mod.tk, 'Label', lambda *a, **k: DummyWidget())
        monkeypatch.setattr(mod.tk, 'Entry', lambda *a, **k: DummyWidget())
        monkeypatch.setattr(mod.tk, 'Button', lambda *a, **k: DummyWidget())
        monkeypatch.setattr(mod.tk, 'Scrollbar', lambda *a, **k: DummyWidget())
        monkeypatch.setattr(mod.tk, 'Listbox', lambda *a, **k: DummyListbox())
        monkeypatch.setattr(mod.tk, 'StringVar', lambda *a, **k: DummyVar())
        monkeypatch.setattr(mod.tk, 'OptionMenu', lambda *a, **k: DummyWidget())

    patch_mod(sub4)
    patch_mod(sub5)
    monkeypatch.setattr(sub4.scrolledtext, 'ScrolledText', lambda *a, **k: DummyScrolledText())
    monkeypatch.setattr(sub5.scrolledtext, 'ScrolledText', lambda *a, **k: DummyScrolledText())


# --------------------- Subcomponent 1 ---------------------

def test_sub1_main_success(monkeypatch):
    monkeypatch.setattr(sub1.tk, 'Tk', lambda: DummyRoot())
    monkeypatch.setattr(sub1.filedialog, 'askdirectory', lambda title=None: '/tmp')
    runpy.run_module('nanoporethon.subcomponent_1_prompt_user', run_name='__main__')


def test_sub1_main_cancel(monkeypatch):
    monkeypatch.setattr(sub1.tk, 'Tk', lambda: DummyRoot())
    monkeypatch.setattr(sub1.filedialog, 'askdirectory', lambda title=None: '')
    runpy.run_module('nanoporethon.subcomponent_1_prompt_user', run_name='__main__')


# --------------------- Subcomponent 2 ---------------------

def test_sub2_oserror_branch(monkeypatch):
    monkeypatch.setattr(sub2.os.path, 'isdir', lambda _p: True)

    def boom(_p):
        raise OSError('nope')

    monkeypatch.setattr(sub2.os, 'listdir', boom)
    with pytest.raises(OSError):
        sub2.data_navi('/tmp', ['a'], [])


def test_sub2_main_success(monkeypatch):
    monkeypatch.setattr(sub2.os.path, 'isdir', lambda _p: True)
    monkeypatch.setattr(sub2.os, 'listdir', lambda _p: ['x_2NNN2_p180', 'other'])
    runpy.run_module('nanoporethon.subcomponent_2_data_navigator', run_name='__main__')


def test_sub2_main_error(monkeypatch):
    monkeypatch.setattr(sub2.os.path, 'isdir', lambda _p: False)
    runpy.run_module('nanoporethon.subcomponent_2_data_navigator', run_name='__main__')


# --------------------- Subcomponent 3 ---------------------

def test_sub3_type_error_for_non_list(tmp_path):
    with pytest.raises(TypeError):
        sub3.data_navi_sub_directory(str(tmp_path), 'not-a-list', str(tmp_path), 'q', [], [])


def test_sub3_oserror_from_makedirs(monkeypatch, tmp_path):
    def boom(*_args, **_kwargs):
        raise OSError('cannot make dir')

    monkeypatch.setattr(sub3.os, 'makedirs', boom)
    with pytest.raises(OSError):
        sub3.data_navi_sub_directory(str(tmp_path), [], str(tmp_path), 'q', [], [])


def test_sub3_absolute_path_and_no_selected_files(tmp_path):
    abs_item = str(tmp_path / 'abc.txt')
    (tmp_path / 'abc.txt').write_text('x')
    sub3.data_navi_sub_directory(str(tmp_path), [abs_item], str(tmp_path), 'qabs', [], [])

    # Also cover no selected files branch
    sub3.data_navi_sub_directory(str(tmp_path), [], str(tmp_path), 'qempty', [], [])


def test_sub3_ioerror_on_query_file(monkeypatch, tmp_path):
    real_open = builtins.open

    def bad_open(path, mode='r', *args, **kwargs):
        if str(path).endswith('search_query.txt') and 'w' in mode:
            raise IOError('write fail')
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, 'open', bad_open)
    with pytest.raises(IOError):
        sub3.data_navi_sub_directory(str(tmp_path), ['a'], str(tmp_path), 'qio', [], [])


def test_sub3_main_success_and_error(monkeypatch):
    # success path
    monkeypatch.setattr(sub3.os.path, 'isdir', lambda _p: True)
    runpy.run_module('nanoporethon.subcomponent_3_data_navi_sub_directory', run_name='__main__')

    # error path
    monkeypatch.setattr(sub3.os.path, 'isdir', lambda _p: False)
    runpy.run_module('nanoporethon.subcomponent_3_data_navi_sub_directory', run_name='__main__')


# --------------------- Subcomponent 4 helpers ---------------------

def make_sub4_gui():
    gui = sub4.DataNaviGUI.__new__(sub4.DataNaviGUI)
    gui.root = DummyRoot()
    gui.db_dir_var = DummyVar()
    gui.logs_dir_var = DummyVar()
    gui.inclusion_var = DummyVar()
    gui.exclusion_var = DummyVar()
    gui.file_listbox = DummyListbox()
    gui.log_output = DummyScrolledText()
    gui.selected_files = []
    gui.all_available_files = []
    gui.database_directory = None
    gui.logs_directory = None
    return gui


# --------------------- Subcomponent 4 ---------------------

def test_sub4_load_config_error(monkeypatch, tmp_path):
    monkeypatch.setattr(sub4, 'CONFIG_FILE', str(tmp_path / 'bad.json'))
    (tmp_path / 'bad.json').write_text('{bad-json')
    assert sub4.load_config() == {}


def test_sub4_save_config_exception(monkeypatch):
    monkeypatch.setattr(sub4, 'load_config', lambda: {})

    def bad_open(*_args, **_kwargs):
        raise OSError('fail')

    monkeypatch.setattr(builtins, 'open', bad_open)
    # should not raise
    sub4.save_config('/db', '/logs')


def test_sub4_init_lines(monkeypatch):
    root = DummyRoot()
    monkeypatch.setattr(sub4.DataNaviGUI, 'build_gui', lambda self: None)
    monkeypatch.setattr(sub4.DataNaviGUI, 'load_saved_directory', lambda self: None)
    gui = sub4.DataNaviGUI(root)
    assert gui.database_directory is None


def test_sub4_build_gui_and_log(patch_tk_widgets):
    gui = sub4.DataNaviGUI.__new__(sub4.DataNaviGUI)
    gui.root = DummyRoot()
    sub4.DataNaviGUI.build_gui(gui)
    sub4.DataNaviGUI.log(gui, 'hello')
    assert 'hello' in gui.log_output.text


def test_sub4_load_saved_directory_paths(monkeypatch, tmp_path):
    gui = make_sub4_gui()
    gui.log = mock.MagicMock()
    gui.set_database_directory = mock.MagicMock()
    gui.set_logs_directory = mock.MagicMock()
    gui.browse_database_directory = mock.MagicMock()

    # valid saved dirs
    cfg = {'database_directory': str(tmp_path), 'logs_directory': str(tmp_path)}
    monkeypatch.setattr(sub4, 'load_config', lambda: cfg)
    sub4.DataNaviGUI.load_saved_directory(gui)
    assert gui.set_database_directory.called
    assert gui.set_logs_directory.called

    # invalid saved dirs
    cfg2 = {'database_directory': '/nope', 'logs_directory': '/nope2'}
    monkeypatch.setattr(sub4, 'load_config', lambda: cfg2)
    sub4.DataNaviGUI.load_saved_directory(gui)
    assert gui.browse_database_directory.called


def test_sub4_browse_directory_methods(monkeypatch, tmp_path):
    gui = make_sub4_gui()
    gui.log = mock.MagicMock()
    gui.update_file_list = mock.MagicMock()
    monkeypatch.setattr(sub4, 'save_config', mock.MagicMock())

    # db valid + invalid
    monkeypatch.setattr(sub4.filedialog, 'askdirectory', lambda title=None: str(tmp_path))
    sub4.DataNaviGUI.browse_database_directory(gui)
    monkeypatch.setattr(sub4.filedialog, 'askdirectory', lambda title=None: '')
    sub4.DataNaviGUI.browse_database_directory(gui)

    # logs valid + invalid
    monkeypatch.setattr(sub4.filedialog, 'askdirectory', lambda title=None: str(tmp_path))
    sub4.DataNaviGUI.browse_logs_directory(gui)
    monkeypatch.setattr(sub4.filedialog, 'askdirectory', lambda title=None: '')
    sub4.DataNaviGUI.browse_logs_directory(gui)


def test_sub4_setters_and_update_file_list(monkeypatch, tmp_path):
    gui = make_sub4_gui()
    gui.log = mock.MagicMock()

    monkeypatch.setattr(sub4, 'save_config', mock.MagicMock())
    sub4.DataNaviGUI.set_database_directory(gui, str(tmp_path))
    sub4.DataNaviGUI.set_logs_directory(gui, str(tmp_path))

    # normal update
    (tmp_path / 'a.txt').write_text('a')
    (tmp_path / 'b.txt').write_text('b')
    gui.database_directory = str(tmp_path)
    gui.selected_files = ['a.txt']
    sub4.DataNaviGUI.update_file_list(gui)
    assert any(item.startswith('✓ ') for item in gui.file_listbox.items)

    # invalid path branch
    gui.database_directory = '/not/real'
    sub4.DataNaviGUI.update_file_list(gui)

    # exception branch
    gui.database_directory = str(tmp_path)
    monkeypatch.setattr(sub4.os, 'listdir', lambda _p: (_ for _ in ()).throw(RuntimeError('boom')))
    sub4.DataNaviGUI.update_file_list(gui)


def test_sub4_search_select_clear_confirm(monkeypatch, tmp_path):
    gui = make_sub4_gui()
    logs = []
    gui.log = lambda m: logs.append(m)
    gui.update_file_list = mock.MagicMock()

    # perform_search: no db
    sub4.DataNaviGUI.perform_search(gui)

    # perform_search: no inclusion
    gui.database_directory = str(tmp_path)
    gui.inclusion_var.set('')
    gui.exclusion_var.set('')
    sub4.DataNaviGUI.perform_search(gui)

    # perform_search: success + exception
    gui.inclusion_var.set('a')
    monkeypatch.setattr(sub4, 'data_navi', lambda *_args, **_kwargs: ['f1', 'f2'])
    sub4.DataNaviGUI.perform_search(gui)
    monkeypatch.setattr(sub4, 'data_navi', lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError('x')))
    sub4.DataNaviGUI.perform_search(gui)

    # on_file_select branches
    gui.file_listbox.items = ['f1', '✓ f2']
    gui.file_listbox.selected_index = None
    sub4.DataNaviGUI.on_file_select(gui, None)

    gui.selected_files = []
    gui.file_listbox.selected_index = 0
    sub4.DataNaviGUI.on_file_select(gui, None)

    # cover remove branch
    gui.selected_files = ['f1']
    gui.file_listbox.selected_index = 0
    sub4.DataNaviGUI.on_file_select(gui, None)

    gui.file_listbox.selected_index = 1
    sub4.DataNaviGUI.on_file_select(gui, None)

    # select all / clear
    gui.all_available_files = ['x', 'y']
    sub4.DataNaviGUI.select_all(gui)
    sub4.DataNaviGUI.clear_selection(gui)

    # confirm_search branches
    warn = mock.MagicMock()
    info = mock.MagicMock()
    err = mock.MagicMock()
    monkeypatch.setattr(sub4.messagebox, 'showwarning', warn)
    monkeypatch.setattr(sub4.messagebox, 'showinfo', info)
    monkeypatch.setattr(sub4.messagebox, 'showerror', err)

    gui.database_directory = '/bad'
    gui.browse_database_directory = lambda: None
    sub4.DataNaviGUI.confirm_search(gui)

    gui.database_directory = str(tmp_path)
    gui.selected_files = []
    sub4.DataNaviGUI.confirm_search(gui)

    gui.selected_files = ['x']
    gui.logs_directory = '/badlogs'
    gui.browse_logs_directory = lambda: None
    sub4.DataNaviGUI.confirm_search(gui)

    gui.logs_directory = str(tmp_path)
    monkeypatch.setattr(sub4.simpledialog, 'askstring', lambda *a, **k: None)
    sub4.DataNaviGUI.confirm_search(gui)

    monkeypatch.setattr(sub4.simpledialog, 'askstring', lambda *a, **k: 'q')
    monkeypatch.setattr(sub4, 'data_navi_sub_directory', lambda *a, **k: None)
    sub4.DataNaviGUI.confirm_search(gui)

    monkeypatch.setattr(sub4, 'data_navi_sub_directory', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('no')))
    sub4.DataNaviGUI.confirm_search(gui)


def test_sub4_run_gui(monkeypatch):
    monkeypatch.setattr(sub4.tk, 'Tk', lambda: DummyRoot())
    monkeypatch.setattr(sub4, 'DataNaviGUI', lambda root: object())
    sub4.run_gui()


def test_sub4_main_block(monkeypatch, patch_tk_widgets):
    monkeypatch.setattr(sub4.tk, 'Tk', lambda: DummyRoot())
    monkeypatch.setattr(sub4.filedialog, 'askdirectory', lambda title=None: '')
    runpy.run_module('nanoporethon.subcomponent_4_data_navi_gui', run_name='__main__')


# --------------------- Subcomponent 5 helpers ---------------------

def make_sub5_gui():
    gui = sub5.EventClassifierGUI.__new__(sub5.EventClassifierGUI)
    gui.root = DummyRoot()
    gui.dir_var = DummyVar()
    gui.query_var = DummyVar()
    gui.query_combo = DummyWidget()
    gui.file_listbox = DummyListbox()
    gui.plot_container = DummyWidget()
    gui.log_output = DummyScrolledText()
    gui.logs_directory = None
    gui.database_directory = None
    gui.current_query = None
    gui.selected_files = []
    gui.plot_canvas = None
    gui.plot_toolbar = None
    return gui


# --------------------- Subcomponent 5 ---------------------

def test_sub5_load_and_save_config_branches(monkeypatch, tmp_path):
    monkeypatch.setattr(sub5, 'CONFIG_FILE', str(tmp_path / 'cfg.json'))
    assert sub5.load_config() is None
    sub5.save_config('/abc')
    assert sub5.load_config() == '/abc'

    # exception branch
    def bad_open(*_args, **_kwargs):
        raise OSError('x')

    monkeypatch.setattr(builtins, 'open', bad_open)
    assert sub5.load_config() is None
    sub5.save_config('/xyz')  # should not raise


def test_sub5_load_search_log_branches(tmp_path, monkeypatch):
    log_file = tmp_path / 'search_query.txt'
    log_file.write_text(
        'Source Directory: /src\n'
        'Selected Files/Directories:\n'
        '- f1\n'
        '- f2\n'
        'Failed to load\n'
    )
    source, files = sub5.load_search_log(str(log_file))
    assert source == '/src'
    assert files == ['f1', 'f2']

    # exception path
    monkeypatch.setattr(builtins, 'open', lambda *_a, **_k: (_ for _ in ()).throw(OSError('bad')))
    source, files = sub5.load_search_log('/missing')
    assert source is None and files == []


def test_sub5_init_build_and_log(monkeypatch, patch_tk_widgets):
    root = DummyRoot()
    monkeypatch.setattr(sub5.EventClassifierGUI, 'load_saved_directory', lambda self: None)
    gui = sub5.EventClassifierGUI(root)
    sub5.EventClassifierGUI.log(gui, 'msg')
    assert 'msg' in gui.log_output.text


def test_sub5_directory_and_queries(monkeypatch, tmp_path):
    gui = make_sub5_gui()
    gui.log = mock.MagicMock()
    gui.refresh_queries = mock.MagicMock()

    # load_saved_directory valid and invalid
    monkeypatch.setattr(sub5, 'load_config', lambda: str(tmp_path))
    sub5.EventClassifierGUI.load_saved_directory(gui)

    monkeypatch.setattr(sub5, 'load_config', lambda: '/nope')
    sub5.EventClassifierGUI.load_saved_directory(gui)

    # browse_directory valid/invalid
    monkeypatch.setattr(sub5.filedialog, 'askdirectory', lambda title=None: str(tmp_path))
    sub5.EventClassifierGUI.browse_directory(gui)
    monkeypatch.setattr(sub5.filedialog, 'askdirectory', lambda title=None: '')
    sub5.EventClassifierGUI.browse_directory(gui)


def test_sub5_refresh_select_and_exit(monkeypatch, tmp_path):
    gui = make_sub5_gui()
    logs = []
    gui.log = lambda m: logs.append(m)

    # refresh invalid dir
    sub5.EventClassifierGUI.refresh_queries(gui)

    # refresh valid dir and query list
    q1 = tmp_path / 'q1'
    q2 = tmp_path / 'q2'
    q1.mkdir()
    q2.mkdir()
    gui.logs_directory = str(tmp_path)
    called = {'selected': None}
    gui.select_query = lambda q: called.update({'selected': q})
    sub5.EventClassifierGUI.refresh_queries(gui)
    assert called['selected'] is not None

    # refresh exception branch
    monkeypatch.setattr(sub5.os, 'listdir', lambda _p: (_ for _ in ()).throw(RuntimeError('bad')))
    sub5.EventClassifierGUI.refresh_queries(gui)

    # select_query missing log
    gui.select_query = sub5.EventClassifierGUI.select_query.__get__(gui, sub5.EventClassifierGUI)
    gui.logs_directory = str(tmp_path)
    sub5.EventClassifierGUI.select_query(gui, 'qmissing')

    # select_query no source in log
    qq = tmp_path / 'qgood'
    qq.mkdir()
    (qq / 'search_query.txt').write_text('Selected Files/Directories:\n- a\n')
    sub5.EventClassifierGUI.select_query(gui, 'qgood')

    # select_query success
    (qq / 'search_query.txt').write_text('Source Directory: /source\nSelected Files/Directories:\n- a\n- b\n')
    sub5.EventClassifierGUI.select_query(gui, 'qgood')

    # exit
    sub5.EventClassifierGUI.exit_gui(gui)
    assert gui.root.quit_called is True


def test_sub5_on_file_select_branches(monkeypatch, tmp_path):
    gui = make_sub5_gui()
    logs = []
    gui.log = lambda m: logs.append(m)
    gui.database_directory = str(tmp_path)
    gui.file_listbox.items = ['sample']

    # no selection
    gui.file_listbox.selected_index = None
    sub5.EventClassifierGUI.on_file_select(gui, None)

    # missing mat file
    gui.file_listbox.selected_index = 0
    sub5.EventClassifierGUI.on_file_select(gui, None)

    # Create MAT path structure
    sample_dir = tmp_path / 'sample'
    sample_dir.mkdir()
    mat_file = sample_dir / 'reduced.mat'
    mat_file.write_text('not-hdf5')

    # reduced missing
    class FakeFile1(dict):
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False

    monkeypatch.setattr(sub5.h5py, 'File', lambda *_a, **_k: FakeFile1({}))
    sub5.EventClassifierGUI.on_file_select(gui, None)

    # data or pt missing
    monkeypatch.setattr(sub5.h5py, 'File', lambda *_a, **_k: FakeFile1({'reduced': {}}))
    sub5.EventClassifierGUI.on_file_select(gui, None)

    # successful plotting
    class FakeDataset:
        def __init__(self, arr):
            self.arr = arr
        def __getitem__(self, _idx):
            class Arr:
                def __init__(self, data):
                    self._data = data
                def flatten(self):
                    return self._data
            return Arr(self.arr)

    class FakeReduced(dict):
        pass

    fake_reduced = FakeReduced({'data': FakeDataset([1, 2]), 'pt': FakeDataset([0, 1])})
    monkeypatch.setattr(sub5.h5py, 'File', lambda *_a, **_k: FakeFile1({'reduced': fake_reduced}))

    ax = mock.MagicMock()
    fig = mock.MagicMock()
    monkeypatch.setattr(sub5.plt, 'subplots', lambda figsize=None: (fig, ax))

    canvas_widget = DummyWidget()

    class FakeCanvas:
        def __init__(self, fig, master=None):
            self._widget = canvas_widget
        def draw(self):
            return None
        def get_tk_widget(self):
            return self._widget

    class FakeToolbar(DummyWidget):
        def __init__(self, canvas, container):
            super().__init__()

    monkeypatch.setattr(sub5, 'FigureCanvasTkAgg', FakeCanvas)
    monkeypatch.setattr(sub5, 'NavigationToolbar2Tk', FakeToolbar)

    gui.plot_toolbar = FakeToolbar(None, None)
    gui.plot_canvas = FakeCanvas(None, None)
    sub5.EventClassifierGUI.on_file_select(gui, None)

    # exception branch
    monkeypatch.setattr(sub5.h5py, 'File', lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError('boom')))
    sub5.EventClassifierGUI.on_file_select(gui, None)


def test_sub5_run_gui_and_main(monkeypatch, patch_tk_widgets):
    monkeypatch.setattr(sub5.tk, 'Tk', lambda: DummyRoot())
    monkeypatch.setattr(sub5, 'EventClassifierGUI', lambda root: object())
    sub5.run_gui()

    monkeypatch.setattr(sub5.filedialog, 'askdirectory', lambda title=None: '')
    runpy.run_module('nanoporethon.subcomponent_5_event_classifier_gui', run_name='__main__')
