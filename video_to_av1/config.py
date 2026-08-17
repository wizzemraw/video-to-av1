"""Configuration management for video converter."""

import json
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


@dataclass
class Config:
    """Configuration for video conversion."""
    
    bitrate: str = "400k"
    preset: int = 6
    audio_bitrate: str = "96k"
    threads: int = 4
    suffix: str = "_converted"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "bitrate": self.bitrate,
            "preset": self.preset,
            "audio_bitrate": self.audio_bitrate,
            "threads": self.threads,
            "suffix": self.suffix,
        }


def load_config(config_path: Path) -> Dict[str, Any]:
    """
    Load configuration from file.
    
    Supports YAML and JSON formats.
    
    Args:
        config_path: Path to config file
        
    Returns:
        Dictionary of configuration values
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    try:
        suffix = config_path.suffix.lower()
        
        if suffix in [".yaml", ".yml"]:
            if not HAS_YAML:
                raise ImportError(
                    "PyYAML is required for YAML config files. "
                    "Install with: pip install pyyaml"
                )
            with open(config_path, "r") as f:
                config = yaml.safe_load(f) or {}
        
        elif suffix == ".json":
            with open(config_path, "r") as f:
                config = json.load(f)
        
        else:
            raise ValueError(f"Unsupported config format: {suffix}")
        
        logger.info(f"Loaded config from {config_path}")
        return config
    
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in config file: {e}")
        raise
    except yaml.YAMLError as e:
        logger.error(f"Invalid YAML in config file: {e}")
        raise
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        raise


def save_config(config: Config, output_path: Path, format: str = "json"):
    """
    Save configuration to file.
    
    Args:
        config: Config object to save
        output_path: Path to save config file
        format: File format ('json' or 'yaml')
    """
    try:
        config_dict = config.to_dict()
        
        if format == "yaml":
            if not HAS_YAML:
                raise ImportError("PyYAML is required for YAML format")
            with open(output_path, "w") as f:
                yaml.dump(config_dict, f, default_flow_style=False)
        
        elif format == "json":
            with open(output_path, "w") as f:
                json.dump(config_dict, f, indent=2)
        
        else:
            raise ValueError(f"Unsupported format: {format}")
        
        logger.info(f"Saved config to {output_path}")
    
    except Exception as e:
        logger.error(f"Error saving config: {e}")
        raise