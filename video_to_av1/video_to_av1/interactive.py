"""Interactive wizard that asks the user how to convert their videos."""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

import typer

from .browser import pick_directory, pick_file
from .config import (
    Config,
    RESOLUTION_PRESETS,
    build_scale_filter,
    validate_bitrate,
)


@dataclass
class WizardResult:
    """Everything the wizard collected."""

    source: Path
    output: Path
    config: Config
    parallel: int


# --------------------------------------------------------------------------- #
# Small prompt helpers
# --------------------------------------------------------------------------- #

def _menu(title: str, options: List[str], default: int = 1) -> int:
    """Show a numbered menu and return the 0-based index chosen."""
    typer.secho(f"\n{title}", fg=typer.colors.CYAN, bold=True)
    for i, option in enumerate(options, start=1):
        typer.echo(f"  {i}) {option}")
    while True:
        choice = typer.prompt("Choose", default=default, type=int)
        if 1 <= choice <= len(options):
            return choice - 1
        typer.secho(f"Please enter a number from 1 to {len(options)}.", fg=typer.colors.YELLOW)


def _validated_prompt(text: str, default: str, validator: Callable[[str], str]) -> str:
    """Prompt until the validator accepts the answer."""
    while True:
        value = typer.prompt(text, default=default)
        try:
            return validator(value)
        except ValueError as e:
            typer.secho(str(e), fg=typer.colors.YELLOW)


def _int_prompt(text: str, default: int, low: int, high: Optional[int] = None) -> int:
    while True:
        value = typer.prompt(text, default=default, type=int)
        if value >= low and (high is None or value <= high):
            return value
        bound = f"{low}-{high}" if high is not None else f"{low} or more"
        typer.secho(f"Please enter a value of {bound}.", fg=typer.colors.YELLOW)


def _typed_path(text: str, must_exist: bool) -> Path:
    while True:
        raw = typer.prompt(text).strip().strip('"')
        path = Path(raw).expanduser()
        if not must_exist or path.exists():
            return path
        typer.secho(f"Not found: {path}", fg=typer.colors.YELLOW)


# --------------------------------------------------------------------------- #
# Individual steps
# --------------------------------------------------------------------------- #

def _ask_source(allow_gui: bool) -> Path:
    while True:
        choice = _menu(
            "Step 1: What do you want to convert?",
            ["Browse for a video file", "Browse for a folder of videos", "Type a path"],
        )
        if choice == 0:
            picked = pick_file("Choose a video file", Path.cwd(), allow_gui)
        elif choice == 1:
            picked = pick_directory("Choose a folder of videos", Path.cwd(), allow_gui)
        else:
            picked = _typed_path("Path to a video file or folder", must_exist=True)
        if picked is not None:
            return picked
        typer.secho("Nothing selected.", fg=typer.colors.YELLOW)


def _ask_output(source: Path, allow_gui: bool) -> Path:
    same_as_source = source if source.is_dir() else source.parent
    while True:
        choice = _menu(
            "Step 2: Where should converted files be saved?",
            [
                f"Same folder as the source ({same_as_source})",
                "Browse for a folder",
                "Type a path",
            ],
        )
        if choice == 0:
            return same_as_source
        if choice == 1:
            picked = pick_directory("Choose the output folder", same_as_source, allow_gui)
            if picked is not None:
                return picked
            typer.secho("Nothing selected.", fg=typer.colors.YELLOW)
        else:
            path = _typed_path("Output folder", must_exist=False)
            if path.exists() and not path.is_dir():
                typer.secho("That path is a file, not a folder.", fg=typer.colors.YELLOW)
                continue
            if not path.exists() and not typer.confirm(f"'{path}' doesn't exist. Create it?", default=True):
                continue
            return path


def _ask_resolution(default: Optional[str]) -> Optional[str]:
    labels = list(RESOLUTION_PRESETS)
    options = ["Keep original resolution"] + labels + ["Custom (e.g. 900p or 1280x720)"]
    choice = _menu("Step 3: Video resolution", options)
    if choice == 0:
        return None
    if choice <= len(labels):
        return RESOLUTION_PRESETS[labels[choice - 1]]

    def check(value: str) -> str:
        build_scale_filter(value)  # raises ValueError if invalid
        return value.strip()

    return _validated_prompt("Resolution", default or "720p", check)


def _ask_quality(default: Config) -> dict:
    choice = _menu(
        "Step 4: How should video quality be controlled?",
        [
            "Quality level / CRF (consistent quality, file size varies) - recommended",
            "Target bitrate (predictable file size, quality varies)",
        ],
        default=2 if (default.crf is None) else 1,
    )
    if choice == 0:
        typer.secho(
            "  CRF 0-63: lower = better quality & bigger file. ~28 high, ~35 balanced, ~45 small.",
            dim=True,
        )
        crf = _int_prompt("CRF (q)", default.crf if default.crf is not None else 35, 0, 63)
        return {"crf": crf, "bitrate": None}
    bitrate = _validated_prompt("Video bitrate (e.g. 400k, 1.5M)", default.bitrate or "400k", validate_bitrate)
    return {"crf": None, "bitrate": bitrate}


def _ask_audio(default: str) -> str:
    return _validated_prompt("\nStep 5: Audio bitrate (e.g. 96k, 128k)", default, validate_bitrate)


def _ask_preset(default: int) -> int:
    typer.secho(
        "\nStep 6: Encoder preset 0-12 (lower = slower but smaller/better, higher = faster).",
        fg=typer.colors.CYAN,
        bold=True,
    )
    return _int_prompt("Preset", default, 0, 12)


# --------------------------------------------------------------------------- #
# Wizard entry point
# --------------------------------------------------------------------------- #

def run_wizard(
    defaults: Config,
    source: Optional[Path] = None,
    output: Optional[Path] = None,
    parallel: int = 1,
    allow_gui: bool = True,
) -> Optional[WizardResult]:
    """Walk the user through every setting. Returns None if they decline at the end.

    Anything already supplied (source/output/defaults) is used as the starting
    answer instead of being ignored.
    """
    typer.secho("\n=== Video to AV1 ===", fg=typer.colors.CYAN, bold=True)
    typer.echo("Press Enter to accept the value shown in [brackets].")

    if source is None:
        source = _ask_source(allow_gui)
    else:
        typer.echo(f"\nSource: {source}")

    if output is None:
        output = _ask_output(source, allow_gui)
    else:
        typer.echo(f"Output: {output}")

    resolution = _ask_resolution(defaults.resolution)
    quality = _ask_quality(defaults)
    audio_bitrate = _ask_audio(defaults.audio_bitrate)
    preset = _ask_preset(defaults.preset)

    threads, suffix = defaults.threads, defaults.suffix
    if typer.confirm("\nChange advanced settings (threads, parallel jobs, filename suffix)?", default=False):
        threads = _int_prompt("Threads per file", threads, 1)
        parallel = _int_prompt("Files to convert at once", parallel, 1)
        suffix = typer.prompt("Output filename suffix", default=suffix)

    config = Config(
        bitrate=quality["bitrate"],
        crf=quality["crf"],
        resolution=resolution,
        preset=preset,
        audio_bitrate=audio_bitrate,
        threads=threads,
        suffix=suffix,
    )

    typer.secho("\n--- Summary ---", fg=typer.colors.CYAN, bold=True)
    typer.echo(f"  Source:        {source}")
    typer.echo(f"  Output folder: {output}")
    typer.echo(f"  Resolution:    {config.resolution or 'original'}")
    if config.crf is not None:
        typer.echo(f"  Video quality: CRF {config.crf}")
    else:
        typer.echo(f"  Video bitrate: {config.bitrate}")
    typer.echo(f"  Audio bitrate: {config.audio_bitrate}")
    typer.echo(f"  Preset:        {config.preset}")
    typer.echo(f"  Threads:       {config.threads}  |  Parallel files: {parallel}")
    typer.echo(f"  Suffix:        {config.suffix}")

    if not typer.confirm("\nStart conversion?", default=True):
        return None
    return WizardResult(source=source, output=output, config=config, parallel=parallel)
