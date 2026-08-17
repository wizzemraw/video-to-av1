"""Core video conversion logic with progress tracking."""

import subprocess
import logging
import shutil
from pathlib import Path
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from .config import Config

logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm",
    ".m4v", ".mpg", ".mpeg", ".3gp", ".ogv", ".ts", ".mts", ".m2ts"
}


def get_video_duration(ffmpeg_path: str, video_file: Path) -> Optional[float]:
    """
    Get video duration in seconds using ffprobe/ffmpeg.
    
    Args:
        ffmpeg_path: Path to ffmpeg executable
        video_file: Path to video file
        
    Returns:
        Duration in seconds or None if unable to determine
    """
    try:
        # Try using ffprobe first (more reliable)
        ffprobe_path = shutil.which("ffprobe")
        if ffprobe_path:
            result = subprocess.run(
                [
                    ffprobe_path,
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1:noprint_wrappers=1",
                    str(video_file)
                ],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.stdout.strip():
                return float(result.stdout.strip())
    except Exception as e:
        logger.debug(f"Could not get duration with ffprobe: {e}")
    
    return None


class VideoConverter:
    """Handles video conversion to AV1 format with progress tracking."""
    
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
        """Build FFmpeg command for AV1 encoding with progress output."""
        return [
            self.ffmpeg_path,
            "-i", str(input_file),
            "-c:v", "libsvtav1",
            "-b:v", self.config.bitrate,
            "-preset", str(self.config.preset),
            "-c:a", "aac",
            "-b:a", self.config.audio_bitrate,
            "-threads", str(self.config.threads),
            "-progress", "pipe:1",
            "-y",
            str(output_file)
        ]
    
    def _parse_ffmpeg_progress(self, line: str) -> Optional[float]:
        """Parse progress from ffmpeg output. Returns time in seconds."""
        try:
            if line.startswith("out_time_ms="):
                time_ms = int(line.split("=")[1])
                return time_ms / 1000.0
        except (ValueError, IndexError):
            pass
        return None
    
    def _convert_single_file(
        self,
        input_file: Path,
        output_file: Path,
        total_duration: Optional[float] = None
    ) -> Dict[str, any]:
        """Convert a single video file to AV1 with progress bar."""
        try:
            if output_file.exists():
                logger.warning(f"Output file exists, will overwrite: {output_file}")
            
            cmd = self._build_ffmpeg_command(input_file, output_file)
            
            # Get video duration if available
            if total_duration is None:
                total_duration = get_video_duration(self.ffmpeg_path, input_file)
            
            # Run ffmpeg with progress tracking
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            
            # Progress bar
            pbar = None
            if total_duration:
                pbar = tqdm(
                    total=total_duration,
                    unit="s",
                    desc=input_file.name,
                    leave=False,
                    dynamic_ncols=True
                )
            
            try:
                # Read progress from ffmpeg
                while True:
                    line = process.stdout.readline()
                    if not line:
                        break
                    
                    # Update progress bar
                    if pbar:
                        current_time = self._parse_ffmpeg_progress(line)
                        if current_time is not None:
                            pbar.n = min(current_time, total_duration)
                            pbar.refresh()
                
                # Wait for process to complete
                returncode = process.wait()
                
                if pbar:
                    pbar.close()
                
                if returncode != 0:
                    stderr = process.stderr.read() if process.stderr else ""
                    error_msg = stderr or "Unknown FFmpeg error"
                    logger.error(f"FFmpeg error for {input_file.name}: {error_msg}")
                    return {
                        "file": input_file.name,
                        "success": False,
                        "error": "FFmpeg conversion failed"
                    }
                
                logger.info(f"✓ Converted: {output_file.name}")
                return {
                    "file": input_file.name,
                    "success": True,
                    "output": str(output_file)
                }
            
            finally:
                if pbar:
                    pbar.close()
                try:
                    process.terminate()
                except:
                    pass
        
        except subprocess.TimeoutExpired:
            logger.error(f"Conversion timeout for {input_file.name}")
            return {
                "file": input_file.name,
                "success": False,
                "error": "Conversion timeout (>1 hour)"
            }
        
        except Exception as e:
            logger.error(f"Error converting {input_file.name}: {e}")
            return {
                "file": input_file.name,
                "success": False,
                "error": str(e)
            }
    
    def convert_files(
        self,
        input_files: List[Path],
        output_dir: Path,
        parallel_jobs: int = 1
    ) -> List[Dict]:
        """Convert multiple video files to AV1 with progress tracking."""
        results = []
        
        # Pre-calculate durations
        durations = {}
        with tqdm(total=len(input_files), desc="Analyzing videos", unit="video", disable=len(input_files) < 2) as pbar:
            for input_file in input_files:
                duration = get_video_duration(self.ffmpeg_path, input_file)
                durations[input_file] = duration
                pbar.update(1)
        
        if parallel_jobs == 1:
            # Sequential conversion with progress bar per file
            with tqdm(total=len(input_files), desc="Converting", unit="video") as pbar:
                for input_file in input_files:
                    output_file = output_dir / f"{input_file.stem}{self.config.suffix}.mkv"
                    result = self._convert_single_file(
                        input_file,
                        output_file,
                        durations.get(input_file)
                    )
                    results.append(result)
                    pbar.update(1)
        
        else:
            # Parallel conversion with overall progress
            with ThreadPoolExecutor(max_workers=parallel_jobs) as executor:
                futures = {}
                
                for input_file in input_files:
                    output_file = output_dir / f"{input_file.stem}{self.config.suffix}.mkv"
                    future = executor.submit(
                        self._convert_single_file,
                        input_file,
                        output_file,
                        durations.get(input_file)
                    )
                    futures[future] = input_file
                
                with tqdm(total=len(input_files), desc="Converting (parallel)", unit="video") as pbar:
                    for future in as_completed(futures):
                        try:
                            result = future.result()
                            results.append(result)
                        except Exception as e:
                            input_file = futures[future]
                            logger.error(f"Parallel conversion error for {input_file}: {e}")
                            results.append({
                                "file": input_file.name,
                                "success": False,
                                "error": str(e)
                            })
                        pbar.update(1)
        
        return results