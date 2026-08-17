"""Video to AV1 converter CLI tool."""

import typer
import logging
from pathlib import Path
from typing import Optional
from .converter import VideoConverter
from .config import Config, load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = typer.Typer(help="Convert videos to AV1 format using FFmpeg")


@app.command()
def convert(
    source: Path = typer.Argument(..., help="Input video file or folder", exists=True),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output folder"),
    bitrate: str = typer.Option("400k", "--bitrate", "-b", help="Video bitrate"),
    preset: int = typer.Option(6, "--preset", "-p", min=0, max=12, help="Encoding preset"),
    audio_bitrate: str = typer.Option("96k", "--audio-bitrate", "-ab", help="Audio bitrate"),
    threads: int = typer.Option(4, "--threads", "-t", min=1, help="Threads per file"),
    parallel: int = typer.Option(1, "--parallel", "-j", min=1, help="Parallel jobs"),
    suffix: str = typer.Option("_converted", "--suffix", "-s", help="Output suffix"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Preview only"),
    config_file: Optional[Path] = typer.Option(None, "--config", "-c", help="Config file"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
):
    """Convert videos to AV1 format."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    try:
        config_settings = {}
        if config_file:
            config_settings = load_config(config_file)
            logger.info(f"Loaded config from {config_file}")
        config = Config(
            bitrate=config_settings.get("bitrate", bitrate),
            preset=config_settings.get("preset", preset),
            audio_bitrate=config_settings.get("audio_bitrate", audio_bitrate),
            threads=config_settings.get("threads", threads),
            suffix=config_settings.get("suffix", suffix),
        )
        if output is None:
            output = Path.cwd()
        output.mkdir(parents=True, exist_ok=True)
        converter = VideoConverter(config=config)
        if not converter.check_ffmpeg():
            typer.secho("FFmpeg not found! Install it and ensure it's in PATH.", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        typer.secho("FFmpeg found", fg=typer.colors.GREEN)
        files = converter.get_video_files(source)
        if not files:
            typer.secho(f"No video files found in {source}", fg=typer.colors.YELLOW)
            raise typer.Exit(code=0)
        typer.secho(f"\nFound {len(files)} video file(s)\n", fg=typer.colors.BLUE)
        for video_file in files:
            output_file = output / f"{video_file.stem}{config.suffix}.mkv"
            typer.echo(f"  {video_file.name} -> {output_file.name}")
        if dry_run:
            typer.secho("\nDry-run mode: No files converted", fg=typer.colors.YELLOW)
            raise typer.Exit(code=0)
        typer.secho("\nStarting conversion...\n", fg=typer.colors.CYAN)
        results = converter.convert_files(files, output, parallel_jobs=parallel)
        typer.secho("\nConversion Summary\n", fg=typer.colors.CYAN)
        successful = sum(1 for r in results if r["success"])
        failed = sum(1 for r in results if not r["success"])
        for result in results:
            if result["success"]:
                typer.secho(f"OK {result['file']}", fg=typer.colors.GREEN)
            else:
                typer.secho(f"FAIL {result['file']}: {result['error']}", fg=typer.colors.RED)
        typer.secho(f"\nComplete! {successful} succeeded, {failed} failed", fg=typer.colors.GREEN if failed == 0 else typer.colors.YELLOW)
        if failed > 0:
            raise typer.Exit(code=1)
    except KeyboardInterrupt:
        typer.secho("\nCancelled by user", fg=typer.colors.YELLOW)
        raise typer.Exit(code=130)
    except Exception as e:
        typer.secho(f"\nError: {str(e)}", fg=typer.colors.RED, err=True)
        logger.exception("Conversion failed")
        raise typer.Exit(code=1)


@app.command()
def show_config():
    """Show default configuration."""
    config = Config()
    typer.echo("Default Configuration:")
    typer.echo(f"  Video Bitrate: {config.bitrate}")
    typer.echo(f"  Preset: {config.preset}")
    typer.echo(f"  Audio Bitrate: {config.audio_bitrate}")
    typer.echo(f"  Threads: {config.threads}")
    typer.echo(f"  Suffix: {config.suffix}")


def main():
    """Entry point."""
    app()


if __name__ == "__main__":
    main()