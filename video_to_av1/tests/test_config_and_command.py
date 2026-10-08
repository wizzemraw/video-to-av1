"""Tests for config validation, scale filters and ffmpeg command building."""

from pathlib import Path

import pytest

from video_to_av1.config import Config, build_scale_filter, validate_bitrate
from video_to_av1.converter import VideoConverter


def test_scale_filter_variants():
    assert build_scale_filter(None) is None
    assert build_scale_filter("original") is None
    assert build_scale_filter("720p") == "scale=-2:'min(720,ih)'"
    assert build_scale_filter("1080") == "scale=-2:'min(1080,ih)'"
    assert build_scale_filter("1280x720") == "scale=1280:720"


def test_scale_filter_rejects_garbage():
    with pytest.raises(ValueError):
        build_scale_filter("huge")


def test_bitrate_validation():
    assert validate_bitrate("400k") == "400k"
    assert validate_bitrate("1.5M") == "1.5M"
    with pytest.raises(ValueError):
        validate_bitrate("fast")


def test_config_validation():
    with pytest.raises(ValueError):
        Config(crf=64)
    with pytest.raises(ValueError):
        Config(preset=13)
    with pytest.raises(ValueError):
        Config(bitrate=None, crf=None)


def _cmd(config):
    converter = VideoConverter(config)
    converter.ffmpeg_path = "ffmpeg"
    return converter._build_ffmpeg_command(Path("in.mp4"), Path("out.mkv"))


def test_command_bitrate_mode():
    cmd = _cmd(Config(bitrate="500k"))
    assert "-b:v" in cmd and cmd[cmd.index("-b:v") + 1] == "500k"
    assert "-crf" not in cmd and "-vf" not in cmd


def test_command_crf_mode_with_resolution():
    cmd = _cmd(Config(bitrate=None, crf=30, resolution="720p"))
    assert cmd[cmd.index("-crf") + 1] == "30"
    assert "-b:v" not in cmd
    assert cmd[cmd.index("-vf") + 1] == "scale=-2:'min(720,ih)'"


def test_progress_parser_uses_microseconds():
    converter = VideoConverter(Config())
    assert converter._parse_ffmpeg_progress("out_time_ms=5000000\n") == 5.0
    assert converter._parse_ffmpeg_progress("out_time=00:00:07.500000\n") == 7.5
    assert converter._parse_ffmpeg_progress("out_time_ms=-1\n") is None
