# Video to AV1

A fast and efficient CLI tool to convert videos to AV1 format using FFmpeg.

## Features

- Batch conversion of single files or folders
- Parallel processing for faster throughput
- Dry-run mode to preview conversions
- Custom encoding presets and bitrates
- YAML/JSON configuration file support
- Cross-platform (Windows, macOS, Linux)
- Verbose logging for debugging

## Installation

### Prerequisites
- Python 3.8+
- FFmpeg with libsvtav1 support

### Quick Install

```bash
pip install video-to-av1
```

### From Source

```bash
git clone https://github.com/wizzemraw/video-to-av1.git
cd video-to-av1
pip install -e .
```

## Usage

### Basic Examples

```bash
# Convert a single file
video-to-av1 input.mp4 --output ./converted

# Convert entire folder
video-to-av1 ./videos --output ./converted

# Use parallel processing
video-to-av1 ./videos --output ./converted --parallel 4

# Preview without converting
video-to-av1 ./videos --dry-run
```

### Options

- `--output, -o` : Output folder (default: current directory)
- `--bitrate, -b` : Video bitrate (default: 400k)
- `--preset, -p` : Encoding preset 0-12 (default: 6)
- `--audio-bitrate, -ab` : Audio bitrate (default: 96k)
- `--threads, -t` : Threads per encoding (default: 4)
- `--parallel, -j` : Parallel conversions (default: 1)
- `--suffix, -s` : Output filename suffix (default: _converted)
- `--dry-run, -n` : Preview without converting
- `--config, -c` : Load settings from config file
- `--verbose, -v` : Enable verbose logging

## Configuration

Create a `config.yaml` file:

```yaml
bitrate: "1M"
preset: 6
audio_bitrate: "128k"
threads: 8
suffix: "_av1"
```

Then use it:

```bash
video-to-av1 ./videos --config config.yaml
```

## License

MIT License
