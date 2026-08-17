"""Video to AV1 converter package."""

__version__ = "1.0.0"
__author__ = "wizzemraw"
__license__ = "MIT"

from .cli import app, main
from .converter import VideoConverter
from .config import Config, load_config, save_config

__all__ = [
    "app",
    "main",
    "VideoConverter",
    "Config",
    "load_config",
    "save_config",
]