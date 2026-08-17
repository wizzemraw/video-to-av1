"""Core video conversion logic."""

import subprocess
import logging
import shutil
from pathlib import Path
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from .config import Config

logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm",
    ".m4v", ".mpg", ".mpeg", ".3gp", ".ogv", ".ts", ".mts", ".m2ts"
}


class VideoConverter:
    """Handles video conversion to AV1 format."""
    
    def __init__(self, config: Config):
        """Initialize converter with configuration."""
        self.config = config
        self.ffmpeg_path = None
    
    def check_ffmpeg(self) -> bool:
        """Check if FFmpeg is installed and accessible."""
        try:
            self.ffmpeg_path = shutil.which("ffmpeg")
            if self.ffmpeg_path:
                result = subprocess.run(
                    [self.ffmpeg_path, "-version"],
                    capture_output=True,
                    timeout=5
                )
                return result.returncode == 0
        except Exception as e:
            logger.error(f"Error checking FFmpeg: {e}")
        return False
    
    def get_video_files(self, source: Path) -> List[Path]:
        """Get all video files from source."""
        files = []
        if source.is_file():
            if source.suffix.lower() in VIDEO_EXTENSIONS:
                files.append(source)
            else:
                logger.warning(f"Skipping {source}: not a video file")
        elif source.is_dir():
            for file in source.iterdir():
                if file.is_file() and file.suffix.lower() in VIDEO_EXTENSIONS:
                    files.append(file)
        return sorted(files)
    
    def _build_ffmpeg_command(self, input_file: Path, output_file: Path) -> List[str]:
        """Build FFmpeg command for AV1 encoding."""
        return [
            self.ffmpeg_path,
            "-i", str(input_file),
            "-c:v", "libsvtav1",
            "-b:v", self.config.bitrate,
            "-preset", str(self.config.preset),
            "-c:a", "aac",
            "-b:a", self.config.audio_bitrate,
            "-threads", str(self.config.threads),
            "-y",
            str(output_file)
        ]
    
    def _convert_single_file(self, input_file: Path, output_file: Path) -> Dict[str, any]:
        """Convert a single video file to AV1."""
        try:
            logger.info(f"Converting: {input_file.name}")
            if output_file.exists():
                logger.warning(f"Output file exists, will overwrite: {output_file}")
            cmd = self._build_ffmpeg_command(input_file, output_file)
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            if result.returncode != 0:
                error_msg = result.stderr or "Unknown FFmpeg error"
                logger.error(f"FFmpeg error for {input_file.name}: {error_msg}")
                return {"file": input_file.name, "success": False, "error": "FFmpeg conversion failed"}
            logger.info(f"✓ Converted: {output_file.name}")
            return {"file": input_file.name, "success": True, "output": str(output_file)}
        except subprocess.TimeoutExpired:
            logger.error(f"Conversion timeout for {input_file.name}")
            return {"file": input_file.name, "success": False, "error": "Conversion timeout (>1 hour)"}
        except Exception as e:
            logger.error(f"Error converting {input_file.name}: {e}")
            return {"file": input_file.name, "success": False, "error": str(e)}
    
    def convert_files(self, input_files: List[Path], output_dir: Path, parallel_jobs: int = 1) -> List[Dict]:
        """Convert multiple video files to AV1."""
        results = []
        if parallel_jobs == 1:
            for input_file in input_files:
                output_file = output_dir / f"{input_file.stem}{self.config.suffix}.mkv"
                result = self._convert_single_file(input_file, output_file)
                results.append(result)
        else:
            with ThreadPoolExecutor(max_workers=parallel_jobs) as executor:
                futures = {}
                for input_file in input_files:
                    output_file = output_dir / f"{input_file.stem}{self.config.suffix}.mkv"
                    future = executor.submit(self._convert_single_file, input_file, output_file)
                    futures[future] = input_file
                for future in as_completed(futures):
                    try:
                        result = future.result()
                        results.append(result)
                    except Exception as e:
                        input_file = futures[future]
                        logger.error(f"Parallel conversion error for {input_file}: {e}")
                        results.append({"file": input_file.name, "success": False, "error": str(e)})
        return results