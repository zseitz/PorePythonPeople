"""
Subcomponent 0: Config Manager
Description: Handles persistent configuration storage for directory paths and settings.
Used by GUIs to save and load user selections across sessions.
"""

import os
import json
from typing import Optional, Dict, Any


# Config file location
CONFIG_FILE = os.path.join(os.path.dirname(__file__), ".nanoporethon_config.json")


def load_config() -> Dict[str, Any]:
    """
    Load the entire configuration from the config file.
    
    Returns:
        Dict[str, Any]: Configuration dictionary, or empty dict if file doesn't exist.
    """
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_config(config: Dict[str, Any]) -> None:
    """
    Save the entire configuration to the config file.
    
    Args:
        config (Dict[str, Any]): Configuration dictionary to save.
    """
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f)
    except Exception:
        pass


def get_config_value(key: str, default: Any = None) -> Any:
    """
    Get a single configuration value by key.
    
    Args:
        key (str): The configuration key.
        default (Any): Default value if key doesn't exist.
    
    Returns:
        Any: The configuration value or default.
    """
    config = load_config()
    return config.get(key, default)


def set_config_value(key: str, value: Any) -> None:
    """
    Set a single configuration value by key.
    
    Args:
        key (str): The configuration key.
        value (Any): The value to set.
    """
    config = load_config()
    config[key] = value
    save_config(config)


def get_database_directory() -> Optional[str]:
    """Get the saved database directory path."""
    path = get_config_value("database_directory")
    return path if path and os.path.isdir(path) else None


def set_database_directory(path: str) -> None:
    """Save the database directory path."""
    set_config_value("database_directory", path)


def get_logs_directory() -> Optional[str]:
    """Get the saved logs directory path."""
    path = get_config_value("logs_directory")
    return path if path and os.path.isdir(path) else None


def set_logs_directory(path: str) -> None:
    """Save the logs directory path."""
    set_config_value("logs_directory", path)


def clear_config() -> None:
    """Clear all saved configuration."""
    try:
        if os.path.exists(CONFIG_FILE):
            os.remove(CONFIG_FILE)
    except Exception:
        pass
