"""Video to AV1 converter CLI tool."""

import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import typer

from .config import Config, load_config
from .converter import VideoConverter
from .interactive import run_wizard

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = typer.Typer(
    help=(
        "Convert videos to AV1 format using FFmpeg.\n\n"
        "Run with no arguments (or use 'convert --interactive') for a guided, "
        "step-by-step mode."
    ),
)


def _stdin_is_tty() -> bool:
    """Whether we're attached to a real terminal (patched in tests)."""
    return sys.stdin.isatty()


def _merge_config(cli: Dict[str, Any], file_settings: Dict[str, Any]) -> Config:
    """Build a Config. Priority: command-line flag > config file > default."""
    defaults = Config()

    def pick(key: str) -> Any:
        if cli.get(key) is not None:
            return cli[key]
        return file_settings.get(key, getattr(defaults, key))

    if cli.get("crf") is not None and cli.get("bitrate") is not None:
        raise typer.BadParameter("Use either --crf or --bitrate, not both.")

    # SVT-AV1 uses constant quality (CRF) or a target bitrate, never both.
    if cli.get("crf") is not None:
        crf, bitrate = cli["crf"], None
    elif cli.get("bitrate") is not None:
        crf, bitrate = None, cli["bitrate"]
    elif file_settings.get("crf") is not None:
        crf, bitrate = file_settings["crf"], None
    else:
        crf, bitrate = None, file_settings.get("bitrate", defaults.bitrate)

    return Config(
        bitrate=bitrate,
        crf=crf,
        resolution=pick("resolution"),
        preset=pick("preset"),
        audio_bitrate=pick("audio_bitrate"),
        threads=pick("threads"),
        suffix=pick("suffix"),
    )


def _run(
    source: Optional[Path],
    output: Optional[Path],
    cli_values: Dict[str, Any],
    parallel: Optional[int],
    dry_run: bool,
    config_file: Optional[Path],
    verbose: bool,
    interactive: bool,
    no_gui: bool,
) -> None:
    """Shared implementation for `convert` and the no-argument wizard."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    try:
        file_settings: Dict[str, Any] = {}
        if config_file:
            file_settings = load_config(config_file)
        config = _merge_config(cli_values, file_settings)
        parallel = parallel if parallel is not None else file_settings.get("parallel", 1)

        converter = VideoConverter(config=config)
        if not converter.check_ffmpeg():
            typer.secho("FFmpeg not found! Install it and ensure it's in PATH.", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        typer.secho("FFmpeg found", fg=typer.colors.GREEN)

        if interactive or source is None:
            if not _stdin_is_tty():
                typer.secho(
                    "Interactive mode needs a terminal. Pass a source path instead.",
                    fg=typer.colors.RED,
                    err=True,
                )
                raise typer.Exit(code=2)
            result = run_wizard(
                defaults=config,
                source=source,
                output=output,
                parallel=parallel,
                allow_gui=not no_gui,
            )
            if result is None:
                typer.secho("Cancelled.", fg=typer.colors.YELLOW)
                raise typer.Exit(code=0)
            source, output, config, parallel = result.source, result.output, result.config, result.parallel
            converter.config = config

        if not source.exists():
            typer.secho(f"Source not found: {source}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

        if output is None:
            output = Path.cwd()
        output.mkdir(parents=True, exist_ok=True)

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
        for item in results:
            if item["success"]:
                typer.secho(f"OK {item['file']}", fg=typer.colors.GREEN)
            else:
                typer.secho(f"FAIL {item['file']}: {item['error']}", fg=typer.colors.RED)
        typer.secho(
            f"\nComplete! {successful} succeeded, {failed} failed",
            fg=typer.colors.GREEN if failed == 0 else typer.colors.YELLOW,
        )
        if failed > 0:
            raise typer.Exit(code=1)

    except typer.Exit:
        raise  # typer.Exit is an Exception subclass; don't treat it as an error
    except (KeyboardInterrupt, typer.Abort):
        typer.secho("\nCancelled by user", fg=typer.colors.YELLOW)
        raise typer.Exit(code=130)
    except typer.BadParameter as e:
        typer.secho(f"\nError: {e.message}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    except Exception as e:
        typer.secho(f"\nError: {e}", fg=typer.colors.RED, err=True)
        logger.exception("Conversion failed")
        raise typer.Exit(code=1)


@app.callback(invoke_without_command=True)
def default(
    ctx: typer.Context,
    no_gui: bool = typer.Option(False, "--no-gui", help="Never open a folder-picker window"),
):
    """Running with no command starts the interactive wizard."""
    if ctx.invoked_subcommand is not None:
        return
    if not _stdin_is_tty():
        typer.echo(ctx.get_help())
        raise typer.Exit()
    _run(
        source=None, output=None, cli_values={}, parallel=None, dry_run=False,
        config_file=None, verbose=False, interactive=True, no_gui=no_gui,
    )


@app.command()
def convert(
    source: Optional[Path] = typer.Argument(
        None, help="Input video file or folder (omit to be prompted)"
    ),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output folder"),
    resolution: Optional[str] = typer.Option(
        None, "--resolution", "-r", help="e.g. 1080p, 720p, 1280x720 (default: keep original)"
    ),
    crf: Optional[int] = typer.Option(
        None, "--crf", "-q", min=0, max=63, help="Constant quality 0-63 (lower = better). Excludes --bitrate"
    ),
    bitrate: Optional[str] = typer.Option(
        None, "--bitrate", "-b", help="Target video bitrate, e.g. 400k (default). Excludes --crf"
    ),
    preset: Optional[int] = typer.Option(None, "--preset", "-p", min=0, max=12, help="Encoding preset (default 6)"),
    audio_bitrate: Optional[str] = typer.Option(None, "--audio-bitrate", "-ab", help="Audio bitrate (default 96k)"),
    threads: Optional[int] = typer.Option(None, "--threads", "-t", min=1, help="Threads per file (default 4)"),
    parallel: Optional[int] = typer.Option(None, "--parallel", "-j", min=1, help="Parallel jobs (default 1)"),
    suffix: Optional[str] = typer.Option(None, "--suffix", "-s", help="Output suffix (default _converted)"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Preview only"),
    config_file: Optional[Path] = typer.Option(None, "--config", "-c", help="Config file"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Ask for every setting step by step"),
    no_gui: bool = typer.Option(False, "--no-gui", help="Never open a folder-picker window"),
):
    """Convert videos to AV1 format."""
    _run(
        source=source,
        output=output,
        cli_values={
            "bitrate": bitrate,
            "crf": crf,
            "resolution": resolution,
            "preset": preset,
            "audio_bitrate": audio_bitrate,
            "threads": threads,
            "suffix": suffix,
        },
        parallel=parallel,
        dry_run=dry_run,
        config_file=config_file,
        verbose=verbose,
        interactive=interactive,
        no_gui=no_gui,
    )


@app.command()
def show_config():
    """Show default configuration."""
    config = Config()
    typer.echo("Default Configuration:")
    typer.echo(f"  Resolution: {config.resolution or 'original'}")
    typer.echo(f"  Video Bitrate: {config.bitrate}  (or --crf for constant quality)")
    typer.echo(f"  Preset: {config.preset}")
    typer.echo(f"  Audio Bitrate: {config.audio_bitrate}")
    typer.echo(f"  Threads: {config.threads}")
    typer.echo(f"  Suffix: {config.suffix}")


def main():
    """Entry point."""
    app()


if __name__ == "__main__":
    main()
