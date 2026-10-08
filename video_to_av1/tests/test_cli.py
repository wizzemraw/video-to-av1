"""End-to-end CLI tests using a fake ffmpeg so no real encoding is needed."""

import os
import stat
import sys

import pytest
from typer.testing import CliRunner

from video_to_av1 import cli

runner = CliRunner()

FAKE_FFMPEG = """#!/bin/sh
case "$1" in
  -version) echo "ffmpeg version fake"; exit 0;;
esac
for last; do :; done
echo "$@" > "$last.args"
echo "out_time_ms=1000000"
echo "progress=end"
: > "$last"
"""


@pytest.fixture
def fake_env(tmp_path, monkeypatch):
    if sys.platform == "win32":
        pytest.skip("fake ffmpeg is a shell script")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ffmpeg = bin_dir / "ffmpeg"
    ffmpeg.write_text(FAKE_FFMPEG)
    ffmpeg.chmod(ffmpeg.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    videos = tmp_path / "videos"
    videos.mkdir()
    (videos / "a.mp4").write_bytes(b"x")
    return tmp_path, videos


def test_dry_run_exits_zero(fake_env):
    tmp, videos = fake_env
    result = runner.invoke(cli.app, ["convert", str(videos), "-n"])
    assert result.exit_code == 0, result.output
    assert "Dry-run" in result.output
    assert "Error" not in result.output


def test_crf_and_bitrate_conflict(fake_env):
    tmp, videos = fake_env
    result = runner.invoke(cli.app, ["convert", str(videos), "--crf", "30", "-b", "400k", "-n"])
    assert result.exit_code == 2
    assert "not both" in result.output


def test_flags_reach_ffmpeg(fake_env):
    tmp, videos = fake_env
    out = tmp / "out"
    result = runner.invoke(
        cli.app, ["convert", str(videos), "-o", str(out), "-q", "32", "-r", "720p", "-ab", "128k"]
    )
    assert result.exit_code == 0, result.output
    args = (out / "a_converted.mkv.args").read_text()
    assert "-crf 32" in args and "min(720,ih)" in args and "-b:a 128k" in args


def test_interactive_wizard_full_flow(fake_env, monkeypatch):
    tmp, videos = fake_env
    out = tmp / "wizard_out"
    monkeypatch.setattr(cli, "_stdin_is_tty", lambda: True)
    # source: type a path (3) | output: type a path (3), create it | resolution 720p (5)
    # quality: CRF (1), value 33 | audio 112k | preset 8 | advanced: no | start: yes
    answers = "\n".join([
        "3", str(videos),
        "3", str(out), "y",
        "5",
        "1", "33",
        "112k",
        "8",
        "n",
        "y",
    ]) + "\n"
    result = runner.invoke(cli.app, [], input=answers)
    assert result.exit_code == 0, result.output
    args = (out / "a_converted.mkv.args").read_text()
    assert "-crf 33" in args
    assert "min(720,ih)" in args
    assert "-b:a 112k" in args
    assert "-preset 8" in args
