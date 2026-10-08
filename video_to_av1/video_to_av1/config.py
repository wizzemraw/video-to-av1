"""Configuration management for video converter."""

import json
import logging
import re
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

try:
    import yaml
    HAS_YAML = True
except ImportError:
    yaml = None
    HAS_YAML = False


# Common resolution presets offered by the interactive wizard (label -> value)
RESOLUTION_PRESETS = {
    "2160p (4K)": "2160p",
    "1440p (2K)": "1440p",
    "1080p (Full HD)": "1080p",
    "720p (HD)": "720p",
    "480p (SD)": "480p",
    "360p": "360p",
}


def build_scale_filter(resolution: Optional[str]) -> Optional[str]:
    """
    Turn a resolution string into an FFmpeg scale filter.

    Accepted forms:
        None / "" / "original"  -> no scaling (returns None)
        "720p" or "720"         -> scale to 720 high, keep aspect ratio,
                                   never upscale
        "1280x720"              -> force exact width x height

    Raises:
        ValueError: if the string isn't a recognised resolution.
    """
    if resolution is None:
        return None
    value = str(resolution).strip().lower()
    if value in ("", "original", "source", "keep"):
        return None

    match = re.fullmatch(r"(\d{2,5})x(\d{2,5})", value)
    if match:
        width, height = int(match.group(1)), int(match.group(2))
        return f"scale={width}:{height}"

    match = re.fullmatch(r"(\d{3,4})p?", value)
    if match:
        height = int(match.group(1))
        # -2 keeps aspect ratio with an even width; min() prevents upscaling
        return f"scale=-2:'min({height},ih)'"

    raise ValueError(
        f"Invalid resolution '{resolution}'. Use e.g. 720p, 1080, or 1280x720."
    )


def validate_bitrate(value: str) -> str:
    """Validate an FFmpeg-style bitrate such as 400k, 1.5M or 96000."""
    cleaned = str(value).strip()
    if not re.fullmatch(r"\d+(\.\d+)?[kKmM]?", cleaned):
        raise ValueError(
            f"Invalid bitrate '{value}'. Use e.g. 400k, 1.5M or 96000."
        )
    return cleaned


@dataclass
class Config:
    """Configuration for video conversion.

    Rate control: set either ``crf`` (constant quality, lower = better,
    0-63) or ``bitrate`` (target size). If ``crf`` is set it is used and
    ``bitrate`` is ignored.
    """

    bitrate: Optional[str] = "400k"
    crf: Optional[int] = None
    resolution: Optional[str] = None
    preset: int = 6
    audio_bitrate: str = "96k"
    threads: int = 4
    suffix: str = "_converted"

    def __post_init__(self):
        if self.crf is not None:
            self.crf = int(self.crf)
            if not 0 <= self.crf <= 63:
                raise ValueError("crf must be between 0 and 63")
        if self.bitrate is not None:
            self.bitrate = validate_bitrate(self.bitrate)
        if self.crf is None and self.bitrate is None:
            raise ValueError("Set either crf or bitrate")
        self.audio_bitrate = validate_bitrate(self.audio_bitrate)
        if not 0 <= int(self.preset) <= 12:
            raise ValueError("preset must be between 0 and 12")
        build_scale_filter(self.resolution)  # raises on invalid input

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "bitrate": self.bitrate,
            "crf": self.crf,
            "resolution": self.resolution,
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
    except Exception as e:
        if HAS_YAML and isinstance(e, yaml.YAMLError):
            logger.error(f"Invalid YAML in config file: {e}")
        else:
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
