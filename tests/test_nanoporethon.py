import pytest
import os
import sys
import tempfile
import shutil
import json
from unittest import mock
from datetime import datetime
from typing import List

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Import the subcomponents
import nanoporethon.subcomponent_1_prompt_user as subcomponent_1_prompt_user_module
from nanoporethon.subcomponent_1_prompt_user import prompt_user, database_directory
from nanoporethon.subcomponent_2_data_navigator import data_navi
from nanoporethon.subcomponent_3_data_navi_sub_directory import data_navi_sub_directory
from nanoporethon.subcomponent_4_config_manager import load_config, save_config
from nanoporethon.subcomponent_5_directory_utilities import browse_for_directory, select_database_directory
from nanoporethon.subcomponent_6_search_log_utilities import load_search_log, find_search_queries
from nanoporethon.subcomponent_7_mat_file_loader import load_reduced_mat, load_event_data, load_fsamp_from_event_mat, load_fsamp_from_meta_mat
from nanoporethon.data_navi_gui import DataNaviGUI
from nanoporethon.event_classifier_gui import EventClassifierGUI


class TestSubcomponent1PromptUser:
    """Tests for subcomponent_1_prompt_user.py"""

    def test_smoke_import(self):
        """Smoke test: Ensure module imports and function exists."""
        assert callable(prompt_user)
        assert database_directory is None

    @mock.patch('nanoporethon.subcomponent_1_prompt_user.filedialog.askdirectory')
    @mock.patch('nanoporethon.subcomponent_1_prompt_user.tk.Tk')
    def test_one_shot_select_directory(self, mock_tk, mock_askdirectory):
        """One shot test: Simulate selecting a directory."""
        mock_askdirectory.return_value = '/fake/path'
        result = prompt_user()
        assert result == '/fake/path'
        assert subcomponent_1_prompt_user_module.database_directory == '/fake/path'

    @mock.patch('nanoporethon.subcomponent_1_prompt_user.filedialog.askdirectory')
    @mock.patch('nanoporethon.subcomponent_1_prompt_user.tk.Tk')
    def test_one_shot_no_selection(self, mock_tk, mock_askdirectory):
        """One shot test: Simulate no directory selected."""
        mock_askdirectory.return_value = ''
        result = prompt_user()
        assert result is None
        assert subcomponent_1_prompt_user_module.database_directory is None

    @mock.patch('nanoporethon.subcomponent_1_prompt_user.filedialog.askdirectory')
    @mock.patch('nanoporethon.subcomponent_1_prompt_user.tk.Tk')
    def test_pattern_different_paths(self, mock_tk, mock_askdirectory):
        """Pattern test: Test with different directory paths."""
        paths = ['/path1', '/path2', '']
        for path in paths:
            mock_askdirectory.return_value = path
            result = prompt_user()
            expected = path if path else None
            assert result == expected
            assert subcomponent_1_prompt_user_module.database_directory == expected

    @mock.patch('nanoporethon.subcomponent_1_prompt_user.filedialog.askdirectory')
    @mock.patch('nanoporethon.subcomponent_1_prompt_user.tk.Tk')
    def test_edge_empty_string(self, mock_tk, mock_askdirectory):
        """Edge test: Empty string returned."""
        mock_askdirectory.return_value = ''
        result = prompt_user()
        assert result is None


class TestSubcomponent2DataNavigator:
    """Tests for subcomponent_2_data_navigator.py"""

    def test_smoke_import(self):
        """Smoke test: Ensure function exists."""
        assert callable(data_navi)

    def test_one_shot_basic_filter(self):
        """One shot test: Basic filtering."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test files
            open(os.path.join(temp_dir, 'file1.txt'), 'w').close()
            open(os.path.join(temp_dir, 'file2.log'), 'w').close()
            open(os.path.join(temp_dir, 'data.txt'), 'w').close()

            result = data_navi(temp_dir, ['file'], [])
            assert 'file1.txt' in result
            assert 'file2.log' in result
            assert 'data.txt' not in result

    def test_pattern_inclusion_exclusion(self):
        """Pattern test: Various inclusion and exclusion combinations."""
        with tempfile.TemporaryDirectory() as temp_dir:
            files = ['test1.txt', 'test2.log', 'data1.txt', 'data2.log', 'other.py']
            for f in files:
                open(os.path.join(temp_dir, f), 'w').close()

            # Test inclusion only
            result = data_navi(temp_dir, ['test'], [])
            assert set(result) == {'test1.txt', 'test2.log'}

            # Test inclusion and exclusion
            result = data_navi(temp_dir, ['test'], ['.log'])
            assert result == ['test1.txt']

            # Test multiple inclusions
            result = data_navi(temp_dir, ['test', '1'], [])
            assert result == ['test1.txt']

    def test_edge_invalid_directory(self):
        """Edge test: Invalid directory."""
        with pytest.raises(ValueError):
            data_navi('/nonexistent', [], [])

    def test_edge_empty_arrays(self):
        """Edge test: Empty arrays."""
        with tempfile.TemporaryDirectory() as temp_dir:
            open(os.path.join(temp_dir, 'file.txt'), 'w').close()
            result = data_navi(temp_dir, [], [])
            assert result == ['file.txt']


class TestSubcomponent3DataNaviSubDirectory:
    """Tests for subcomponent_3_data_navi_sub_directory.py"""

    def test_smoke_import(self):
        """Smoke test: Ensure function exists."""
        assert callable(data_navi_sub_directory)

    def test_one_shot_create_directory_and_log(self):
        """One shot test: Create directory and log file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = os.path.join(temp_dir, 'source')
            dest_parent = os.path.join(temp_dir, 'dest')
            os.makedirs(source_dir)
            os.makedirs(dest_parent)

            filenames = ['file1.txt', 'file2.log']
            query_name = 'test_query'
            array_1 = ['inc']
            array_2 = ['exc']

            data_navi_sub_directory(source_dir, filenames, dest_parent, query_name, array_1, array_2)

            # Check if a subdirectory was created (timestamped) directly under dest_parent
            subdirs = [d for d in os.listdir(dest_parent) if os.path.isdir(os.path.join(dest_parent, d))]
            assert len(subdirs) == 1
            subdir = os.path.join(dest_parent, subdirs[0])
            assert os.path.exists(subdir)

            # Check log file
            log_file = os.path.join(subdir, 'search_query.txt')
            assert os.path.exists(log_file)

            with open(log_file, 'r') as f:
                content = f.read()
                assert 'Inclusion Filter (Array_1):' in content
                assert 'Exclusion Filter (Array_2):' in content
                assert 'Selected Files/Directories:' in content

    def test_pattern_different_queries(self):
        """Pattern test: Different query names and arrays."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = os.path.join(temp_dir, 'source')
            dest_parent = os.path.join(temp_dir, 'dest')
            os.makedirs(source_dir)
            os.makedirs(dest_parent)

            queries = [
                ('query1', ['inc1'], ['exc1']),
                ('query2', ['inc2'], []),
                ('query3', [], ['exc3'])
            ]

            for query_name, array_1, array_2 in queries:
                filenames = ['file.txt']
                data_navi_sub_directory(source_dir, filenames, dest_parent, query_name, array_1, array_2)

            subdirs = [d for d in os.listdir(dest_parent) if os.path.isdir(os.path.join(dest_parent, d))]
            assert len(subdirs) == 3

    def test_edge_invalid_source_directory(self):
        """Edge test: Invalid source directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with pytest.raises(ValueError):
                data_navi_sub_directory('/nonexistent', [], temp_dir, 'query', [], [])

    def test_edge_invalid_destination_directory(self):
        """Edge test: Invalid destination directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = os.path.join(temp_dir, 'source')
            os.makedirs(source_dir)
            with pytest.raises(ValueError):
                data_navi_sub_directory(source_dir, [], '/nonexistent', 'query', [], [])


class TestSubcomponent4DataNaviGUI:
    """Tests for subcomponent_4_data_navi_gui.py"""

    def test_smoke_import(self):
        """Smoke test: Ensure class exists."""
        assert DataNaviGUI is not None
        assert callable(load_config)
        assert callable(save_config)

    @pytest.mark.skip(reason="GUI initialization requires tkinter root, hard to mock without changing code")
    @mock.patch('tkinter.Tk')
    def test_one_shot_gui_init(self, mock_tk):
        """One shot test: Initialize GUI."""
        mock_root = mock.MagicMock()
        mock_tk.return_value = mock_root
        gui = DataNaviGUI(mock_root)
        assert gui.root == mock_root

    def test_pattern_config_load_save(self):
        """Pattern test: Load and save config."""
        # Test save using the new SC0 API
        config = {'database_directory': '/db', 'logs_directory': '/logs'}
        save_config(config)
        loaded_config = load_config()
        assert loaded_config.get('database_directory') == '/db'
        assert loaded_config.get('logs_directory') == '/logs'

        # Clean up
        config_file = os.path.join(os.path.dirname(__file__), '..', 'src', 'nanoporethon', '.nanoporethon_config.json')
        if os.path.exists(config_file):
            os.remove(config_file)

    def test_edge_config_file_missing(self):
        """Edge test: Config file missing."""
        config = load_config()
        assert config == {}


class TestSubcomponent5EventClassifierGUI:
    """Tests for subcomponent_5_event_classifier_gui.py"""

    def test_smoke_import(self):
        """Smoke test: Ensure class exists."""
        assert EventClassifierGUI is not None
        assert callable(load_config)
        assert callable(save_config)
        assert callable(load_search_log)

    @pytest.mark.skip(reason="GUI initialization requires tkinter root, hard to mock without changing code")
    @mock.patch('tkinter.Tk')
    def test_one_shot_gui_init(self, mock_tk):
        """One shot test: Initialize GUI."""
        mock_root = mock.MagicMock()
        mock_tk.return_value = mock_root
        gui = EventClassifierGUI(mock_root)
        assert gui.root == mock_root

    def test_pattern_config_load_save(self):
        """Pattern test: Load and save config."""
        # Test save using the new SC0 API
        config = {'database_directory': '/db'}
        save_config(config)
        loaded_config = load_config()
        assert loaded_config.get('database_directory') == '/db'

        # Clean up
        config_file = os.path.join(os.path.dirname(__file__), '..', 'src', 'nanoporethon', '.nanoporethon_config.json')
        if os.path.exists(config_file):
            os.remove(config_file)

    def test_edge_config_file_missing(self):
        """Edge test: Config file missing."""
        # Remove config file if it exists
        config_file = os.path.join(os.path.dirname(__file__), '..', 'src', 'nanoporethon', '.nanoporethon_config.json')
        if os.path.exists(config_file):
            os.remove(config_file)
        
        # Test that load_config returns {} when file is missing
        config = load_config()
        assert config == {}

    def test_one_shot_load_search_log(self):
        """One shot test: Load search log."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("DataNavi Search Query Log\n")
            f.write("==================================================\n")
            f.write("Timestamp: 10/03/2026 15:43:33\n")
            f.write("Source Directory: /source\n")
            f.write("Destination Directory: /dest\n")
            f.write("\n")
            f.write("Search Criteria:\n")
            f.write("--------------------------------------------------\n")
            f.write("Inclusion Filter (Array_1):\n")
            f.write("  - inc\n")
            f.write("\nExclusion Filter (Array_2):\n")
            f.write("  - exc\n")
            f.write("\nSelected Files/Directories:\n")
            f.write("--------------------------------------------------\n")
            f.write("  - file1.txt\n")
            f.write("  - file2.log\n")
            log_path = f.name

        source, files = load_search_log(log_path)
        assert source == '/source'
        assert files == ['file1.txt', 'file2.log']

        os.unlink(log_path)