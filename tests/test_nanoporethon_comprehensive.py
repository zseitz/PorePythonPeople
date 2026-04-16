"""
Comprehensive test suite for nanoporethon module.
Tests all subcomponents with >90% code coverage.
All tests are non-interactive - no user prompts or GUI dialogs.
"""

import pytest
import os
import sys
import tempfile
import shutil
import json
import numpy as np
import h5py
from unittest import mock
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Import all modules
import nanoporethon.subcomponent_1_prompt_user as sub1
import nanoporethon.subcomponent_2_data_navigator as sub2
import nanoporethon.subcomponent_3_data_navi_sub_directory as sub3
import nanoporethon.subcomponent_4_config_manager as sub4
import nanoporethon.subcomponent_5_directory_utilities as sub5
import nanoporethon.subcomponent_6_search_log_utilities as sub6
import nanoporethon.subcomponent_7_mat_file_loader as sub7


# ============================================================================
# SUBCOMPONENT 1: Prompt User Tests
# ============================================================================

class TestSubcomponent1PromptUser:
    """Tests for subcomponent_1_prompt_user.py"""
    
    def test_prompt_user_with_directory_selected(self):
        """Test prompt_user correctly saves selected directory."""
        with mock.patch('nanoporethon.subcomponent_1_prompt_user.tk.Tk'), \
             mock.patch('nanoporethon.subcomponent_1_prompt_user.filedialog.askdirectory') as mock_dialog:
            mock_dialog.return_value = '/test/database/path'
            result = sub1.prompt_user()
            assert result == '/test/database/path'
            assert sub1.database_directory == '/test/database/path'
    
    def test_prompt_user_empty_selection(self):
        """Test prompt_user handles empty string selection."""
        with mock.patch('nanoporethon.subcomponent_1_prompt_user.tk.Tk'), \
             mock.patch('nanoporethon.subcomponent_1_prompt_user.filedialog.askdirectory') as mock_dialog:
            mock_dialog.return_value = ''
            result = sub1.prompt_user()
            assert result is None
            assert sub1.database_directory is None
    
    def test_prompt_user_cancelled(self):
        """Test prompt_user handles cancelled dialog."""
        with mock.patch('nanoporethon.subcomponent_1_prompt_user.tk.Tk'), \
             mock.patch('nanoporethon.subcomponent_1_prompt_user.filedialog.askdirectory') as mock_dialog:
            mock_dialog.return_value = None
            result = sub1.prompt_user()
            assert result is None
            assert sub1.database_directory is None
    
    def test_prompt_user_overwrites_previous_selection(self):
        """Test that successive calls overwrite previous directory."""
        with mock.patch('nanoporethon.subcomponent_1_prompt_user.tk.Tk'), \
             mock.patch('nanoporethon.subcomponent_1_prompt_user.filedialog.askdirectory') as mock_dialog:
            mock_dialog.return_value = '/path/one'
            sub1.prompt_user()
            assert sub1.database_directory == '/path/one'
            
            mock_dialog.return_value = '/path/two'
            sub1.prompt_user()
            assert sub1.database_directory == '/path/two'


# ============================================================================
# SUBCOMPONENT 2: Data Navigator Tests
# ============================================================================

class TestSubcomponent2DataNavigator:
    """Tests for subcomponent_2_data_navigator.py"""
    
    @pytest.fixture
    def test_directory(self):
        """Create test directory with sample files."""
        temp_dir = tempfile.mkdtemp()
        
        # Create diverse test files
        files = [
            'experiment_2NNN1_p180_v1.mat',
            'experiment_2NNN1_p190_v1.mat',
            'experiment_2NNN2_p180_v1.mat',
            'control_2NNN1_p180.txt',
            'calibration.dat',
            'metadata.json'
        ]
        
        for filename in files:
            Path(temp_dir, filename).touch()
        
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    def test_data_navi_empty_arrays(self, test_directory):
        """Test with empty inclusion and exclusion arrays."""
        results = sub2.data_navi(test_directory, [], [])
        assert len(results) == 6
    
    def test_data_navi_single_inclusion_term(self, test_directory):
        """Test filtering with single inclusion term."""
        results = sub2.data_navi(test_directory, ['experiment'], [])
        assert 'experiment_2NNN1_p180_v1.mat' in results
        assert 'control_2NNN1_p180.txt' not in results
        assert len(results) == 3
    
    def test_data_navi_multiple_inclusion_terms(self, test_directory):
        """Test filtering requires ALL inclusion terms."""
        results = sub2.data_navi(test_directory, ['experiment', '2NNN1'], [])
        assert 'experiment_2NNN1_p180_v1.mat' in results
        assert 'experiment_2NNN2_p180_v1.mat' not in results
        assert len(results) == 2
    
    def test_data_navi_single_exclusion_term(self, test_directory):
        """Test filtering with single exclusion term."""
        results = sub2.data_navi(test_directory, [], ['calibration'])
        assert 'calibration.dat' not in results
        assert len(results) == 5
    
    def test_data_navi_multiple_exclusion_terms(self, test_directory):
        """Test filtering excludes if ANY exclusion term matches."""
        results = sub2.data_navi(test_directory, [], ['calibration', 'metadata'])
        assert 'calibration.dat' not in results
        assert 'metadata.json' not in results
        assert len(results) == 4
    
    def test_data_navi_inclusion_and_exclusion(self, test_directory):
        """Test combining inclusion and exclusion criteria."""
        results = sub2.data_navi(test_directory, ['experiment'], ['p190'])
        assert 'experiment_2NNN1_p180_v1.mat' in results
        assert 'experiment_2NNN1_p190_v1.mat' not in results
        assert len(results) == 2
    
    def test_data_navi_no_matches(self, test_directory):
        """Test search with no matching results."""
        results = sub2.data_navi(test_directory, ['nonexistent'], [])
        assert len(results) == 0
    
    def test_data_navi_case_sensitive(self, test_directory):
        """Test that filtering is case-sensitive."""
        results = sub2.data_navi(test_directory, ['EXPERIMENT'], [])
        assert len(results) == 0
    
    def test_data_navi_partial_strings(self, test_directory):
        """Test partial string matching."""
        results = sub2.data_navi(test_directory, ['experiment'], [])
        assert len(results) == 3
        assert all('experiment' in r for r in results)
    
    def test_data_navi_invalid_directory(self):
        """Test error handling for nonexistent directory."""
        with pytest.raises(ValueError):
            sub2.data_navi('/nonexistent/directory', [], [])
    
    def test_data_navi_unreadable_directory(self):
        """Test error handling for unreadable directory."""
        temp_dir = tempfile.mkdtemp()
        try:
            os.chmod(temp_dir, 0o000)
            with pytest.raises(OSError):
                sub2.data_navi(temp_dir, [], [])
        finally:
            os.chmod(temp_dir, 0o755)
            shutil.rmtree(temp_dir)


# ============================================================================
# SUBCOMPONENT 3: Data Navi Sub Directory Tests
# ============================================================================

class TestSubcomponent3DataNaviSubDirectory:
    """Tests for subcomponent_3_data_navi_sub_directory.py"""
    
    @pytest.fixture
    def directories(self):
        """Create source and destination directories."""
        src = tempfile.mkdtemp()
        dst = tempfile.mkdtemp()
        
        # Create sample files in source
        for i in range(3):
            Path(src, f'data_file_{i}.mat').touch()
        
        yield src, dst
        
        shutil.rmtree(src)
        shutil.rmtree(dst)
    
    def test_creates_timestamped_subdirectory(self, directories):
        """Test that function creates timestamped directory."""
        src, dst = directories
        sub3.data_navi_sub_directory(src, ['data_file_0.mat'], dst, 'test_query', [], [])
        
        subdirs = os.listdir(dst)
        assert len(subdirs) == 1
        assert subdirs[0].startswith('test_query_')
        assert '_' in subdirs[0]  # Has timestamp
    
    def test_creates_search_query_log_file(self, directories):
        """Test that search_query.txt file is created."""
        src, dst = directories
        sub3.data_navi_sub_directory(src, ['data_file_0.mat'], dst, 'test_query', [], [])
        
        log_file = os.path.join(dst, os.listdir(dst)[0], 'search_query.txt')
        assert os.path.exists(log_file)
    
    def test_log_contains_source_directory(self, directories):
        """Test log file contains source directory path."""
        src, dst = directories
        sub3.data_navi_sub_directory(src, ['data_file_0.mat'], dst, 'test', [], [])
        
        log_file = os.path.join(dst, os.listdir(dst)[0], 'search_query.txt')
        with open(log_file, 'r') as f:
            content = f.read()
        
        assert src in content
        assert 'Source Directory:' in content
    
    def test_log_contains_selected_files(self, directories):
        """Test log file lists selected files."""
        src, dst = directories
        selected = ['data_file_0.mat', 'data_file_1.mat']
        sub3.data_navi_sub_directory(src, selected, dst, 'test', [], [])
        
        log_file = os.path.join(dst, os.listdir(dst)[0], 'search_query.txt')
        with open(log_file, 'r') as f:
            content = f.read()
        
        assert 'data_file_0.mat' in content
        assert 'data_file_1.mat' in content
        assert 'Selected Files/Directories:' in content
    
    def test_log_contains_inclusion_criteria(self, directories):
        """Test log file documents inclusion criteria."""
        src, dst = directories
        sub3.data_navi_sub_directory(src, [], dst, 'test', ['term1', 'term2'], [])
        
        log_file = os.path.join(dst, os.listdir(dst)[0], 'search_query.txt')
        with open(log_file, 'r') as f:
            content = f.read()
        
        assert 'term1' in content
        assert 'term2' in content
        assert 'Inclusion Filter' in content
    
    def test_log_contains_exclusion_criteria(self, directories):
        """Test log file documents exclusion criteria."""
        src, dst = directories
        sub3.data_navi_sub_directory(src, [], dst, 'test', [], ['exc1', 'exc2'])
        
        log_file = os.path.join(dst, os.listdir(dst)[0], 'search_query.txt')
        with open(log_file, 'r') as f:
            content = f.read()
        
        assert 'exc1' in content
        assert 'exc2' in content
        assert 'Exclusion Filter' in content
    
    def test_log_structure(self, directories):
        """Test log file has expected structure."""
        src, dst = directories
        sub3.data_navi_sub_directory(src, ['data_file_0.mat'], dst, 'test', ['inc'], ['exc'])
        
        log_file = os.path.join(dst, os.listdir(dst)[0], 'search_query.txt')
        with open(log_file, 'r') as f:
            content = f.read()
        
        # Check for expected sections
        assert 'DataNavi Search Query Log' in content
        assert 'Source Directory:' in content
        assert 'Search Criteria:' in content
        assert 'Selected Files/Directories:' in content
    
    def test_empty_filenames_list(self, directories):
        """Test with empty file list still creates log."""
        src, dst = directories
        sub3.data_navi_sub_directory(src, [], dst, 'empty', [], [])
        
        log_file = os.path.join(dst, os.listdir(dst)[0], 'search_query.txt')
        assert os.path.exists(log_file)
        
        with open(log_file, 'r') as f:
            content = f.read()
        assert '(No items selected)' in content
    
    def test_empty_criteria_lists(self, directories):
        """Test with empty inclusion and exclusion lists."""
        src, dst = directories
        sub3.data_navi_sub_directory(src, ['data_file_0.mat'], dst, 'empty_criteria', [], [])
        
        log_file = os.path.join(dst, os.listdir(dst)[0], 'search_query.txt')
        with open(log_file, 'r') as f:
            content = f.read()
        
        assert '(Empty - all items included initially)' in content
        assert '(Empty - no items excluded)' in content
    
    def test_invalid_source_directory_error(self, directories):
        """Test error when source directory doesn't exist."""
        _, dst = directories
        with pytest.raises(ValueError):
            sub3.data_navi_sub_directory('/nonexistent', [], dst, 'test', [], [])
    
    def test_invalid_destination_directory_error(self, directories):
        """Test error when destination directory doesn't exist."""
        src, _ = directories
        with pytest.raises(ValueError):
            sub3.data_navi_sub_directory(src, [], '/nonexistent', 'test', [], [])
    
    def test_filenames_not_list_error(self, directories):
        """Test error when filenames_out is not a list."""
        src, dst = directories
        with pytest.raises(TypeError):
            sub3.data_navi_sub_directory(src, 'not_a_list', dst, 'test', [], [])
    
    def test_with_absolute_file_paths(self, directories):
        """Test with absolute file paths."""
        src, dst = directories
        abs_path = os.path.join(src, 'data_file_0.mat')
        sub3.data_navi_sub_directory(src, [abs_path], dst, 'test', [], [])
        
        log_file = os.path.join(dst, os.listdir(dst)[0], 'search_query.txt')
        assert os.path.exists(log_file)


# ============================================================================
# SUBCOMPONENT 4: Config Manager Tests
# ============================================================================

class TestSubcomponent4ConfigManager:
    """Tests for subcomponent_4_config_manager.py"""
    
    @pytest.fixture(autouse=True)
    def clean_config(self):
        sub4.clear_config()
        yield
        sub4.clear_config()
    
    def test_save_and_load_config(self):
        """Test saving and loading configuration."""
        config = {'key1': 'value1', 'key2': 42}
        sub4.save_config(config)
        loaded = sub4.load_config()
        assert loaded == config
    
    def test_load_empty_config(self):
        """Test loading config when file doesn't exist."""
        loaded = sub4.load_config()
        assert isinstance(loaded, dict)
        assert len(loaded) == 0
    
    def test_get_config_value_exists(self):
        """Test retrieving existing config value."""
        sub4.save_config({'test_key': 'test_value'})
        assert sub4.get_config_value('test_key') == 'test_value'
    
    def test_get_config_value_missing_with_default(self):
        """Test retrieving missing value with default."""
        result = sub4.get_config_value('nonexistent', 'default')
        assert result == 'default'
    
    def test_get_config_value_missing_no_default(self):
        """Test retrieving missing value without default."""
        result = sub4.get_config_value('nonexistent')
        assert result is None
    
    def test_set_config_value_new(self):
        """Test setting a new config value."""
        sub4.set_config_value('new_key', 'new_value')
        assert sub4.get_config_value('new_key') == 'new_value'
    
    def test_set_config_value_overwrite(self):
        """Test overwriting existing config value."""
        sub4.set_config_value('key', 'old')
        sub4.set_config_value('key', 'new')
        assert sub4.get_config_value('key') == 'new'
    
    def test_set_multiple_values_cumulative(self):
        """Test setting multiple values cumulatively."""
        sub4.set_config_value('a', 1)
        sub4.set_config_value('b', 2)
        sub4.set_config_value('c', 3)
        
        config = sub4.load_config()
        assert config['a'] == 1
        assert config['b'] == 2
        assert config['c'] == 3
    
    def test_database_directory_save_and_get(self):
        """Test database directory specific functions."""
        temp_dir = tempfile.mkdtemp()
        try:
            sub4.set_database_directory(temp_dir)
            assert sub4.get_database_directory() == temp_dir
        finally:
            shutil.rmtree(temp_dir)
    
    def test_logs_directory_save_and_get(self):
        """Test logs directory specific functions."""
        temp_dir = tempfile.mkdtemp()
        try:
            sub4.set_logs_directory(temp_dir)
            assert sub4.get_logs_directory() == temp_dir
        finally:
            shutil.rmtree(temp_dir)
    
    def test_get_nonexistent_directory_returns_none(self):
        """Test that nonexistent database directory returns None."""
        sub4.save_config({'database_directory': '/nonexistent/path'})
        assert sub4.get_database_directory() is None
    
    def test_get_logs_directory_nonexistent_returns_none(self):
        """Test that nonexistent logs directory returns None."""
        sub4.save_config({'logs_directory': '/nonexistent/path'})
        assert sub4.get_logs_directory() is None
    
    def test_clear_config_deletes_file(self):
        """Test that clear_config removes configuration."""
        sub4.save_config({'key': 'value'})
        sub4.clear_config()
        loaded = sub4.load_config()
        assert len(loaded) == 0


# ============================================================================
# SUBCOMPONENT 5: Directory Utilities Tests
# ============================================================================

class TestSubcomponent5DirectoryUtilities:
    """Tests for subcomponent_5_directory_utilities.py"""
    
    @pytest.fixture(autouse=True)
    def clean_config(self):
        sub4.clear_config()
        yield
        sub4.clear_config()
    
    def test_browse_for_directory_valid(self):
        """Test browse dialog with valid directory."""
        temp_dir = tempfile.mkdtemp()
        try:
            with mock.patch('nanoporethon.subcomponent_5_directory_utilities.filedialog.askdirectory', 
                          return_value=temp_dir):
                result = sub5.browse_for_directory("Test")
                assert result == temp_dir
        finally:
            shutil.rmtree(temp_dir)
    
    def test_browse_for_directory_empty_string(self):
        """Test browse dialog when cancelled (empty string)."""
        with mock.patch('nanoporethon.subcomponent_5_directory_utilities.filedialog.askdirectory', 
                      return_value=''):
            result = sub5.browse_for_directory("Test")
            assert result is None
    
    def test_browse_for_directory_invalid_path(self):
        """Test browse dialog with nonexistent path."""
        with mock.patch('nanoporethon.subcomponent_5_directory_utilities.filedialog.askdirectory', 
                      return_value='/nonexistent'):
            result = sub5.browse_for_directory("Test")
            assert result is None
    
    def test_select_database_directory_saved(self):
        """Test selecting database directory when already saved."""
        temp_dir = tempfile.mkdtemp()
        try:
            sub4.set_database_directory(temp_dir)
            result = sub5.select_database_directory(allow_prompt=False)
            assert result == temp_dir
        finally:
            shutil.rmtree(temp_dir)
    
    def test_select_database_directory_no_prompt_no_saved(self):
        """Test selecting database directory without prompt when none saved."""
        result = sub5.select_database_directory(allow_prompt=False)
        assert result is None
    
    def test_select_database_directory_with_prompt(self):
        """Test selecting database directory with prompt."""
        temp_dir = tempfile.mkdtemp()
        try:
            with mock.patch('nanoporethon.subcomponent_5_directory_utilities.filedialog.askdirectory',
                          return_value=temp_dir):
                result = sub5.select_database_directory(allow_prompt=True)
                assert result == temp_dir
                assert sub4.get_database_directory() == temp_dir
        finally:
            shutil.rmtree(temp_dir)
    
    def test_select_logs_directory_with_prompt(self):
        """Test selecting logs directory with prompt."""
        temp_dir = tempfile.mkdtemp()
        try:
            with mock.patch('nanoporethon.subcomponent_5_directory_utilities.filedialog.askdirectory',
                          return_value=temp_dir):
                result = sub5.select_logs_directory(allow_prompt=True)
                assert result == temp_dir
        finally:
            shutil.rmtree(temp_dir)
    
    def test_validate_directory_valid(self):
        """Test directory validation with valid directory."""
        temp_dir = tempfile.mkdtemp()
        try:
            assert sub5.validate_directory(temp_dir) is True
        finally:
            shutil.rmtree(temp_dir)
    
    def test_validate_directory_invalid(self):
        """Test directory validation with nonexistent directory."""
        assert sub5.validate_directory('/nonexistent') is False
    
    def test_validate_directory_none(self):
        """Test directory validation with None."""
        assert sub5.validate_directory(None) is False


# ============================================================================
# SUBCOMPONENT 6: Search Log Utilities Tests
# ============================================================================

class TestSubcomponent6SearchLogUtilities:
    """Tests for subcomponent_6_search_log_utilities.py"""
    
    def test_load_search_log_valid_file(self):
        """Test loading valid search log file."""
        temp_dir = tempfile.mkdtemp()
        try:
            log_path = os.path.join(temp_dir, 'log.txt')
            with open(log_path, 'w') as f:
                f.write("Source Directory: /test/source\n")
                f.write("Selected Files/Directories:\n")
                f.write("  - file1.txt\n")
                f.write("  - file2.txt\n")
            
            source, files = sub6.load_search_log(log_path)
            assert source == '/test/source'
            assert 'file1.txt' in files
            assert 'file2.txt' in files
        finally:
            shutil.rmtree(temp_dir)
    
    def test_load_search_log_nonexistent_file(self):
        """Test loading nonexistent log file."""
        source, files = sub6.load_search_log('/nonexistent.txt')
        assert source is None
        assert len(files) == 0
    
    def test_load_search_log_empty_file(self):
        """Test loading empty log file."""
        temp_dir = tempfile.mkdtemp()
        try:
            log_path = os.path.join(temp_dir, 'empty.txt')
            Path(log_path).touch()
            
            source, files = sub6.load_search_log(log_path)
            assert source is None
            assert len(files) == 0
        finally:
            shutil.rmtree(temp_dir)
    
    def test_find_search_queries_empty_directory(self):
        """Test finding queries in empty directory."""
        temp_dir = tempfile.mkdtemp()
        try:
            results = sub6.find_search_queries(temp_dir)
            assert len(results) == 0
        finally:
            shutil.rmtree(temp_dir)
    
    def test_find_search_queries_nonexistent_directory(self):
        """Test finding queries in nonexistent directory."""
        results = sub6.find_search_queries('/nonexistent')
        assert len(results) == 0
    
    def test_find_search_queries_with_directories(self):
        """Test finding query directories."""
        temp_dir = tempfile.mkdtemp()
        try:
            # Create query directories
            Path(temp_dir, 'query1_20260101_10:00:00').mkdir()
            Path(temp_dir, 'query2_20260102_10:00:00').mkdir()
            Path(temp_dir, 'query3_20260103_10:00:00').mkdir()
            # Create non-query file
            Path(temp_dir, 'readme.txt').touch()
            
            results = sub6.find_search_queries(temp_dir)
            
            assert len(results) == 3
            assert 'query1_20260101_10:00:00' in results
            assert 'readme.txt' not in results
        finally:
            shutil.rmtree(temp_dir)
    
    def test_find_search_queries_sorted_reverse(self):
        """Test that queries are sorted most recent first."""
        temp_dir = tempfile.mkdtemp()
        try:
            Path(temp_dir, 'query1_20260101').mkdir()
            Path(temp_dir, 'query2_20260102').mkdir()
            Path(temp_dir, 'query3_20260103').mkdir()
            
            results = sub6.find_search_queries(temp_dir)
            
            # Most recent first (reverse sorted)
            assert results[0] > results[1] > results[2]
        finally:
            shutil.rmtree(temp_dir)


# ============================================================================
# SUBCOMPONENT 7: MAT File Loader Tests
# ============================================================================

class TestSubcomponent7MatFileLoader:
    """Tests for subcomponent_7_mat_file_loader.py"""
    
    def test_load_reduced_mat_valid_hdf5(self):
        """Test loading valid HDF5 reduced.mat file."""
        temp_dir = tempfile.mkdtemp()
        try:
            mat_path = os.path.join(temp_dir, 'reduced.mat')
            with h5py.File(mat_path, 'w') as f:
                rg = f.create_group('reduced')
                rg.create_dataset('data', data=np.array([1.0, 2.0, 3.0, 4.0, 5.0]))
                rg.create_dataset('pt', data=np.array([0.1, 0.2, 0.3, 0.4, 0.5]))
                rg.create_dataset('downsampleFactor', data=np.array([2.0]))
            
            data, pt, downsample = sub7.load_reduced_mat(mat_path)
            
            assert len(data) == 5
            assert len(pt) == 5
            assert downsample == 2.0
            assert np.allclose(data[0], 1.0)
        finally:
            shutil.rmtree(temp_dir)
    
    def test_load_reduced_mat_nonexistent_file(self):
        """Test loading nonexistent reduced.mat file."""
        data, pt, downsample = sub7.load_reduced_mat('/nonexistent.mat')
        assert data is None
        assert pt is None
        assert downsample is None
    
    def test_load_reduced_mat_missing_data_field(self):
        """Test loading reduced.mat missing pt field."""
        temp_dir = tempfile.mkdtemp()
        try:
            mat_path = os.path.join(temp_dir, 'bad.mat')
            with h5py.File(mat_path, 'w') as f:
                rg = f.create_group('reduced')
                rg.create_dataset('data', data=np.array([1.0, 2.0]))
                # Missing 'pt' field
            
            data, pt, downsample = sub7.load_reduced_mat(mat_path)
            assert data is None
        finally:
            shutil.rmtree(temp_dir)
    
    def test_load_reduced_mat_default_downsample(self):
        """Test that default downsample factor is 1.0 when not present."""
        temp_dir = tempfile.mkdtemp()
        try:
            mat_path = os.path.join(temp_dir, 'no_ds.mat')
            with h5py.File(mat_path, 'w') as f:
                rg = f.create_group('reduced')
                rg.create_dataset('data', data=np.array([1.0, 2.0]))
                rg.create_dataset('pt', data=np.array([0.1, 0.2]))
                # No downsample factor
            
            data, pt, downsample = sub7.load_reduced_mat(mat_path)
            assert downsample == 1.0
        finally:
            shutil.rmtree(temp_dir)
    
    def test_load_event_data_valid_hdf5(self):
        """Test loading valid HDF5 event.mat file."""
        temp_dir = tempfile.mkdtemp()
        try:
            mat_path = os.path.join(temp_dir, 'event.mat')
            with h5py.File(mat_path, 'w') as f:
                eg = f.create_group('event')
                eg.create_dataset('eventnum', data=np.array([1, 2, 3, 4, 5]))
                eg.create_dataset('eventStartPt', data=np.array([10, 20, 30, 40, 50]))
                eg.create_dataset('eventEndPt', data=np.array([15, 25, 35, 45, 55]))
                eg.create_dataset('eventStartNdx', data=np.array([0, 1, 2, 3, 4]))
                eg.create_dataset('eventEndNdx', data=np.array([5, 6, 7, 8, 9]))
                eg.create_dataset('quality', data=np.array([0.8, 0.9, 0.7, 0.85, 0.92]))
                eg.create_dataset('localIOS', data=np.array([1.0, 1.1, 0.9, 1.05, 1.02]))
            
            event_data = sub7.load_event_data(mat_path)
            
            assert len(event_data['eventnum']) == 5
            assert len(event_data['quality']) == 5
            assert event_data['eventnum'][0] == 1
        finally:
            shutil.rmtree(temp_dir)
    
    def test_load_event_data_nonexistent_file(self):
        """Test loading nonexistent event.mat file returns empty."""
        event_data = sub7.load_event_data('/nonexistent.mat')
        
        # Should return dict with all keys as empty arrays
        assert all(isinstance(v, np.ndarray) for v in event_data.values())
        assert all(v.size == 0 for v in event_data.values())
    
    def test_load_fsamp_from_event_mat_valid(self):
        """Test extracting sampling frequency from event.mat."""
        temp_dir = tempfile.mkdtemp()
        try:
            mat_path = os.path.join(temp_dir, 'event_fsamp.mat')
            with h5py.File(mat_path, 'w') as f:
                eg = f.create_group('event')
                eg.create_dataset('fsamp', data=np.array([100000.0]))
            
            fsamp = sub7.load_fsamp_from_event_mat(mat_path)
            assert fsamp == 100000.0
        finally:
            shutil.rmtree(temp_dir)
    
    def test_load_fsamp_from_event_mat_nonexistent(self):
        """Test extracting fsamp from nonexistent file."""
        fsamp = sub7.load_fsamp_from_event_mat('/nonexistent.mat')
        assert fsamp is None
    
    def test_load_fsamp_from_meta_mat_valid(self):
        """Test extracting sampling frequency from meta.mat."""
        temp_dir = tempfile.mkdtemp()
        try:
            mat_path = os.path.join(temp_dir, 'meta_fsamp.mat')
            with h5py.File(mat_path, 'w') as f:
                mg = f.create_group('meta')
                mg.create_dataset('fsamp', data=np.array([50000.0]))
            
            fsamp = sub7.load_fsamp_from_meta_mat(mat_path)
            assert fsamp == 50000.0
        finally:
            shutil.rmtree(temp_dir)
    
    def test_load_fsamp_from_meta_mat_nonexistent(self):
        """Test extracting fsamp from nonexistent meta.mat."""
        fsamp = sub7.load_fsamp_from_meta_mat('/nonexistent.mat')
        assert fsamp is None
    
    def test_safe_get_scalar_with_array(self):
        """Test _safe_get_scalar with numpy array."""
        result = sub7._safe_get_scalar(np.array([42.5]))
        assert result == 42.5
    
    def test_safe_get_scalar_with_scalar(self):
        """Test _safe_get_scalar with scalar value."""
        result = sub7._safe_get_scalar(3.14)
        assert result == 3.14
    
    def test_safe_get_scalar_with_none(self):
        """Test _safe_get_scalar with None."""
        result = sub7._safe_get_scalar(None)
        assert result is None
    
    def test_normalize_key(self):
        """Test _normalize_key function."""
        assert sub7._normalize_key('EventNum') == 'eventnum'
        assert sub7._normalize_key('event_num') == 'eventnum'
        assert sub7._normalize_key('Event-Num-123') == 'eventnum123'
    
    def test_first_matching_key_found(self):
        """Test _first_matching_key finds matching key."""
        container = {'EventNum': 1, 'startPt': 2, 'EndPt': 3}
        
        result = sub7._first_matching_key(container, ['eventnum'])
        assert result == 'EventNum'
        
        result = sub7._first_matching_key(container, ['startpt'])
        assert result == 'startPt'
    
    def test_first_matching_key_not_found(self):
        """Test _first_matching_key returns None when not found."""
        container = {'data': 1, 'info': 2}
        
        result = sub7._first_matching_key(container, ['nonexistent'])
        assert result is None


# ============================================================================
# Additional MAT File Loader Helper Tests
# ============================================================================

class TestMatFileLoaderHelpers:
    """Tests for helper functions in subcomponent 7."""
    
    def test_extract_numeric_from_dataset_simple(self):
        """Test extracting numeric data from HDF5 dataset."""
        temp_dir = tempfile.mkdtemp()
        try:
            mat_path = os.path.join(temp_dir, 'test.mat')
            with h5py.File(mat_path, 'w') as f:
                f.create_dataset('data', data=np.array([1.0, 2.0, 3.0]))
                result = sub7._extract_numeric_from_dataset(f['data'], f)
                assert len(result) == 3
                assert np.allclose(result[0], 1.0)
        finally:
            shutil.rmtree(temp_dir)
    
    def test_find_dataset_case_insensitive(self):
        """Test case-insensitive dataset lookup."""
        temp_dir = tempfile.mkdtemp()
        try:
            mat_path = os.path.join(temp_dir, 'test.mat')
            with h5py.File(mat_path, 'w') as f:
                f.create_dataset('EventNum', data=np.array([1, 2, 3]))
                result = sub7._find_dataset_case_insensitive(f, 'eventnum')
                assert result is not None
        finally:
            shutil.rmtree(temp_dir)
    
    def test_load_event_vector(self):
        """Test loading event vector from HDF5."""
        temp_dir = tempfile.mkdtemp()
        try:
            mat_path = os.path.join(temp_dir, 'test.mat')
            with h5py.File(mat_path, 'w') as f:
                eg = f.create_group('event')
                eg.create_dataset('eventnum', data=np.array([1, 2, 3]))
                result = sub7._load_event_vector(f, eg, 'eventnum')
                assert len(result) == 3
        finally:
            shutil.rmtree(temp_dir)
    
    def test_safe_get_scalar_empty_array(self):
        """Test _safe_get_scalar with empty array."""
        result = sub7._safe_get_scalar(np.array([]))
        assert result is None
    
    def test_safe_get_scalar_multielement_array(self):
        """Test _safe_get_scalar returns first element."""
        result = sub7._safe_get_scalar(np.array([5.0, 10.0, 15.0]))
        assert result == 5.0


# ============================================================================
# GUI Tests - DataNaviGUI Methods
# ============================================================================

class TestDataNaviGUILogic:
    """Tests for DataNaviGUI logic without using GUI dialogs."""
    
    @pytest.fixture(autouse=True)
    def cleanup_config(self):
        sub4.clear_config()
        yield
        sub4.clear_config()
    
    def test_datanavi_gui_can_instantiate(self):
        """Test DataNaviGUI initialization with mocked Tk."""
        from nanoporethon.data_navi_gui import DataNaviGUI
        
        root = mock.MagicMock()
        
        with mock.patch('nanoporethon.data_navi_gui.tk.StringVar', return_value=mock.MagicMock()), \
             mock.patch('nanoporethon.data_navi_gui.tk.Frame'), \
             mock.patch('nanoporethon.data_navi_gui.tk.Label'), \
             mock.patch('nanoporethon.data_navi_gui.tk.Entry'), \
             mock.patch('nanoporethon.data_navi_gui.tk.Button'), \
             mock.patch('nanoporethon.data_navi_gui.tk.LabelFrame'), \
             mock.patch('nanoporethon.data_navi_gui.tk.Listbox'), \
             mock.patch('nanoporethon.data_navi_gui.tk.Scrollbar'), \
             mock.patch('nanoporethon.data_navi_gui.scrolledtext.ScrolledText'), \
             mock.patch.object(DataNaviGUI, 'load_saved_directory'):
            
            gui = DataNaviGUI(root)
            assert gui.root == root
            assert gui.database_directory is None
            assert gui.logs_directory is None
            assert gui.selected_files == []
            assert gui.all_available_files == []


# ============================================================================
# GUI Tests - EventClassifierGUI Methods
# ============================================================================

class TestEventClassifierGUILogic:
    """Tests for EventClassifierGUI logic without GUI dialogs."""
    
    def test_eventclassifier_gui_can_instantiate(self):
        """Test EventClassifierGUI initialization with mocked Tk."""
        from nanoporethon.event_classifier_gui import EventClassifierGUI
        
        root = mock.MagicMock()
        
        with mock.patch('nanoporethon.event_classifier_gui.tk.StringVar', return_value=mock.MagicMock()), \
             mock.patch('nanoporethon.event_classifier_gui.tk.Frame'), \
             mock.patch('nanoporethon.event_classifier_gui.tk.Label'), \
             mock.patch('nanoporethon.event_classifier_gui.tk.Entry'), \
             mock.patch('nanoporethon.event_classifier_gui.tk.Button'), \
             mock.patch('nanoporethon.event_classifier_gui.tk.LabelFrame'), \
             mock.patch('nanoporethon.event_classifier_gui.tk.Listbox'), \
             mock.patch('nanoporethon.event_classifier_gui.tk.Scrollbar'), \
             mock.patch('nanoporethon.event_classifier_gui.tk.OptionMenu'), \
             mock.patch('nanoporethon.event_classifier_gui.tk.Canvas'), \
             mock.patch('nanoporethon.event_classifier_gui.FigureCanvasTkAgg'), \
             mock.patch.object(EventClassifierGUI, 'load_saved_directory'), \
             mock.patch.object(EventClassifierGUI, '_bind_keyboard_shortcuts'):
            
            gui = EventClassifierGUI(root)
            assert gui.root == root
            assert gui.logs_directory is None
            assert gui.database_directory is None


# ============================================================================
# Edge Cases and Boundary Tests
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""
    
    def test_file_search_with_special_characters(self):
        """Test file searching with special characters."""
        temp_dir = tempfile.mkdtemp()
        try:
            Path(temp_dir, 'file_[bracket]_test.txt').touch()
            Path(temp_dir, 'file_(paren)_test.txt').touch()
            
            results = sub2.data_navi(temp_dir, ['bracket'], [])
            assert 'file_[bracket]_test.txt' in results
            
            results = sub2.data_navi(temp_dir, ['paren'], [])
            assert 'file_(paren)_test.txt' in results
        finally:
            shutil.rmtree(temp_dir)
    
    def test_config_with_empty_values(self):
        """Test config manager with empty string values."""
        sub4.set_config_value('empty_key', '')
        assert sub4.get_config_value('empty_key') == ''
    
    def test_config_with_zero_value(self):
        """Test config manager with zero value."""
        sub4.set_config_value('zero_key', 0)
        assert sub4.get_config_value('zero_key') == 0
    
    def test_config_with_false_value(self):
        """Test config manager with False value."""
        sub4.set_config_value('false_key', False)
        assert sub4.get_config_value('false_key') is False
    
    def test_data_navi_with_very_long_filename(self):
        """Test searching with very long filenames."""
        temp_dir = tempfile.mkdtemp()
        try:
            long_name = 'a' * 200 + '.txt'
            Path(temp_dir, long_name).touch()
            
            results = sub2.data_navi(temp_dir, ['a'], [])
            assert long_name in results
        finally:
            shutil.rmtree(temp_dir)
    
    def test_data_navi_with_unicode_filenames(self):
        """Test searching with unicode filenames."""
        temp_dir = tempfile.mkdtemp()
        try:
            Path(temp_dir, 'café_data.txt').touch()
            Path(temp_dir, '数据文件.mat').touch()
            
            results = sub2.data_navi(temp_dir, ['café'], [])
            assert 'café_data.txt' in results
            
            results = sub2.data_navi(temp_dir, ['数据'], [])
            assert '数据文件.mat' in results
        finally:
            shutil.rmtree(temp_dir)
    
    def test_log_file_with_many_files(self):
        """Test log creation with many files."""
        src = tempfile.mkdtemp()
        dst = tempfile.mkdtemp()
        
        try:
            # Create many files
            many_files = [f'file_{i:04d}.mat' for i in range(50)]
            for fname in many_files:
                Path(src, fname).touch()
            
            sub3.data_navi_sub_directory(src, many_files, dst, 'many_files', [], [])
            
            log_dir = os.listdir(dst)[0]
            log_path = os.path.join(dst, log_dir, 'search_query.txt')
            
            with open(log_path) as f:
                content = f.read()
            
            # All files should be listed
            for fname in many_files:
                assert fname in content
        finally:
            shutil.rmtree(src)
            shutil.rmtree(dst)


# ============================================================================
# Comprehensive Workflow Tests
# ============================================================================

class TestComplexWorkflows:
    """Tests for complex multi-step workflows."""
    
    @pytest.fixture(autouse=True)
    def cleanup_config(self):
        sub4.clear_config()
        yield
        sub4.clear_config()
    
    def test_search_with_complex_criteria(self):
        """Test search with complex inclusion/exclusion patterns."""
        src = tempfile.mkdtemp()
        try:
            # Create diverse files
            files = [
                'experiment_2NNN1_p180_v1_control.mat',
                'experiment_2NNN1_p190_v1_treatment.mat',
                'experiment_2NNN2_p180_v1_control.mat',
                'calibration_2NNN1.mat',
                'metadata.json'
            ]
            for f in files:
                Path(src, f).touch()
            
            # Search for experiments but exclude calibration and control
            results = sub2.data_navi(src, ['experiment'], ['calibration', 'control'])
            
            assert 'experiment_2NNN1_p190_v1_treatment.mat' in results
            assert 'experiment_2NNN1_p180_v1_control.mat' not in results
            assert 'calibration_2NNN1.mat' not in results
            assert 'metadata.json' not in results
        finally:
            shutil.rmtree(src)
    
    def test_sequential_searches_and_logs(self):
        """Test creating multiple search logs in sequence."""
        src = tempfile.mkdtemp()
        dst = tempfile.mkdtemp()
        
        try:
            for f in ['sample_A_rep1.txt', 'sample_A_rep2.txt', 'sample_B_rep1.txt']:
                Path(src, f).touch()
            
            # Search 1: All A samples
            results1 = sub2.data_navi(src, ['sample_A'], [])
            sub3.data_navi_sub_directory(src, results1, dst, 'search_A', ['sample_A'], [])
            
            # Search 2: All rep1 samples
            results2 = sub2.data_navi(src, ['rep1'], [])
            sub3.data_navi_sub_directory(src, results2, dst, 'search_rep1', ['rep1'], [])
            
            # Verify both logs exist
            logs = sub6.find_search_queries(dst)
            assert len(logs) >= 2
            
            # Verify contents are different
            log1_path = os.path.join(dst, [l for l in logs if 'search_A' in l][0], 'search_query.txt')
            log2_path = os.path.join(dst, [l for l in logs if 'search_rep1' in l][0], 'search_query.txt')
            
            with open(log1_path) as f:
                log1_content = f.read()
            with open(log2_path) as f:
                log2_content = f.read()
            
            # Log 1 should have A samples
            assert 'sample_A_rep1.txt' in log1_content
            # Log 2 should have rep1 samples
            assert 'rep1' in log2_content
        finally:
            shutil.rmtree(src)
            shutil.rmtree(dst)


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests combining multiple components."""
    
    @pytest.fixture(autouse=True)
    def clean_config(self):
        sub4.clear_config()
        yield
        sub4.clear_config()
    
    def test_complete_search_workflow(self):
        """Test complete workflow from config to log."""
        source_dir = tempfile.mkdtemp()
        dest_dir = tempfile.mkdtemp()
        
        try:
            # Create test files
            for fname in ['exp_A_1.mat', 'exp_A_2.mat', 'exp_B_1.mat', 'ctrl.txt']:
                Path(source_dir, fname).touch()
            
            # Save config
            sub4.set_database_directory(source_dir)
            sub4.set_logs_directory(dest_dir)
            assert sub4.get_database_directory() == source_dir
            
            # Search
            results = sub2.data_navi(source_dir, ['exp_A'], [])
            assert len(results) == 2
            assert 'exp_A_1.mat' in results
            assert 'exp_B_1.mat' not in results
            
            # Log results
            sub3.data_navi_sub_directory(source_dir, results, dest_dir, 'exp_query', ['exp_A'], [])
            assert len(os.listdir(dest_dir)) == 1
            
            # Load log
            log_dir = os.listdir(dest_dir)[0]
            log_file = os.path.join(dest_dir, log_dir, 'search_query.txt')
            loaded_source, loaded_files = sub6.load_search_log(log_file)
            
            assert loaded_source == source_dir
            assert len(loaded_files) == 2
            assert 'exp_A_1.mat' in loaded_files
        finally:
            shutil.rmtree(source_dir)
            shutil.rmtree(dest_dir)
    
    def test_multiple_searches(self):
        """Test performing multiple searches."""
        source_dir = tempfile.mkdtemp()
        dest_dir = tempfile.mkdtemp()
        
        try:
            for fname in ['sample_A.txt', 'sample_B.txt', 'control.txt']:
                Path(source_dir, fname).touch()
            
            # Search 1
            results1 = sub2.data_navi(source_dir, ['sample_A'], [])
            sub3.data_navi_sub_directory(source_dir, results1, dest_dir, 'search1', [], [])
            
            # Search 2
            results2 = sub2.data_navi(source_dir, ['control'], [])
            sub3.data_navi_sub_directory(source_dir, results2, dest_dir, 'search2', [], [])
            
            # Verify both logs created
            logs = sub6.find_search_queries(dest_dir)
            assert len(logs) >= 2
        finally:
            shutil.rmtree(source_dir)
            shutil.rmtree(dest_dir)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
