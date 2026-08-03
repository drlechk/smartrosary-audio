#!/usr/bin/env python3
"""Build an ESP32-S3 Smart Rosary audio LittleFS image."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


DEFAULT_VARIANT = "en-seraphina"
DEFAULT_IMAGE_NAME = "audio-rosary.bin"
DEFAULT_FS_SIZE = "0x134000"
DEFAULT_BLOCK_SIZE = "4096"
DEFAULT_LITTLEFS_VERSION = "2.1"
AUDIO_MANIFEST_NAME = "audio-manifest.json"


def _platformio_python() -> Path:
    return Path.home() / ".platformio" / "penv" / "bin" / "python"


def _ensure_littlefs():
    try:
        from littlefs import LittleFS

        return LittleFS
    except ModuleNotFoundError:
        pio_python = _platformio_python()
        if pio_python.is_file() and Path(sys.executable).resolve() != pio_python.resolve():
            os.execv(str(pio_python), [str(pio_python), *sys.argv])
        raise


LittleFS = _ensure_littlefs()


def parse_size(value: str) -> int:
    text = str(value).strip()
    if not text:
        raise argparse.ArgumentTypeError("empty size")

    upper = text.upper()
    if upper.endswith("K"):
        return int(upper[:-1], 0) * 1024
    if upper.endswith("M"):
        return int(upper[:-1], 0) * 1024 * 1024
    return int(text, 0)


def parse_littlefs_version(value: str) -> int:
    try:
        major, minor = [int(part) for part in str(value).split(".", 1)]
    except ValueError:
        major, minor = 2, 1
    return (major << 16) | minor


def validate_variant(value: str) -> str:
    variant = value.strip()
    if not variant or Path(variant).name != variant or variant in (".", ".."):
        raise argparse.ArgumentTypeError(f"invalid voice variant: {value!r}")
    return variant


def mp3_data_start_offset(data: bytes) -> int:
    if len(data) < 10 or data[:3] != b"ID3":
        return 0
    tag_size = (
        ((data[6] & 0x7F) << 21)
        | ((data[7] & 0x7F) << 14)
        | ((data[8] & 0x7F) << 7)
        | (data[9] & 0x7F)
    )
    return 10 + tag_size


def bitrate_kbps_for_mp3_frame(version_bits: int, layer_bits: int, bitrate_index: int) -> int:
    if bitrate_index == 0 or bitrate_index == 15:
        return 0

    v1_layer1 = (0, 32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448, 0)
    v1_layer2 = (0, 32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384, 0)
    v1_layer3 = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0)
    v2_layer1 = (0, 32, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 224, 256, 0)
    v2_layer23 = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0)

    if version_bits == 3:
        if layer_bits == 3:
            return v1_layer1[bitrate_index]
        if layer_bits == 2:
            return v1_layer2[bitrate_index]
        if layer_bits == 1:
            return v1_layer3[bitrate_index]
        return 0

    if layer_bits == 3:
        return v2_layer1[bitrate_index]
    if layer_bits in (1, 2):
        return v2_layer23[bitrate_index]
    return 0


def sample_rate_for_mp3_frame(version_bits: int, sample_rate_index: int) -> int:
    if sample_rate_index == 3:
        return 0
    if version_bits == 3:
        return (44100, 48000, 32000)[sample_rate_index]
    if version_bits == 2:
        return (22050, 24000, 16000)[sample_rate_index]
    if version_bits == 0:
        return (11025, 12000, 8000)[sample_rate_index]
    return 0


def mp3_duration_ms(path: Path) -> int:
    data = path.read_bytes()
    pos = mp3_data_start_offset(data)
    total_us = 0
    frames = 0

    while pos + 4 <= len(data):
        header = int.from_bytes(data[pos:pos + 4], "big")
        if (header & 0xFFE00000) != 0xFFE00000:
            pos += 1
            continue

        version_bits = (header >> 19) & 0x03
        layer_bits = (header >> 17) & 0x03
        bitrate_index = (header >> 12) & 0x0F
        sample_rate_index = (header >> 10) & 0x03
        padding = (header >> 9) & 0x01
        if version_bits == 1 or layer_bits == 0:
            pos += 1
            continue

        bitrate_kbps = bitrate_kbps_for_mp3_frame(version_bits, layer_bits, bitrate_index)
        sample_rate = sample_rate_for_mp3_frame(version_bits, sample_rate_index)
        if bitrate_kbps <= 0 or sample_rate <= 0:
            pos += 1
            continue

        if layer_bits == 3:
            frame_length = (((12 * bitrate_kbps * 1000) // sample_rate) + padding) * 4
            samples_per_frame = 384
        else:
            coeff = 72 if layer_bits == 1 and version_bits != 3 else 144
            frame_length = ((coeff * bitrate_kbps * 1000) // sample_rate) + padding
            samples_per_frame = 576 if layer_bits == 1 and version_bits != 3 else 1152

        if frame_length < 4 or pos + frame_length > len(data) + 4:
            pos += 1
            continue

        total_us += (samples_per_frame * 1_000_000) // sample_rate
        pos += frame_length
        frames += 1

    return int((total_us + 500) // 1000) if frames and total_us else 0


def build_audio_manifest(source_dir: Path) -> bytes:
    durations_ms = {}
    for item in sorted(source_dir.rglob("*.mp3")):
        if not item.is_file():
            continue
        rel_path = "/" + item.relative_to(source_dir).as_posix()
        durations_ms[rel_path] = mp3_duration_ms(item)

    manifest = {
        "version": 1,
        "unit": "ms",
        "durations_ms": durations_ms,
    }
    return (json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def add_source_tree(fs: LittleFS, source_dir: Path) -> tuple[int, int]:
    file_count = 0
    skipped_count = 0

    for item in sorted(source_dir.rglob("*")):
        rel_path = item.relative_to(source_dir)
        fs_path = rel_path.as_posix()

        if item.name in (".DS_Store", AUDIO_MANIFEST_NAME):
            skipped_count += 1
            continue

        if item.is_dir():
            fs.makedirs(fs_path, exist_ok=True)
            continue

        if not item.is_file():
            skipped_count += 1
            continue

        if rel_path.parent != Path("."):
            fs.makedirs(rel_path.parent.as_posix(), exist_ok=True)

        with fs.open(fs_path, "wb") as dest:
            dest.write(item.read_bytes())
        file_count += 1

    with fs.open(AUDIO_MANIFEST_NAME, "wb") as dest:
        dest.write(build_audio_manifest(source_dir))
    file_count += 1

    return file_count, skipped_count


def build_audiofs(
    source_dir: Path,
    output_path: Path,
    fs_size: int,
    block_size: int,
    littlefs_version: str,
) -> tuple[int, int]:
    if not source_dir.is_dir():
        raise FileNotFoundError(f"audio source directory not found: {source_dir}")
    if fs_size <= 0:
        raise ValueError("filesystem size must be positive")
    if block_size <= 0:
        raise ValueError("block size must be positive")
    if fs_size % block_size != 0:
        raise ValueError("filesystem size must be a multiple of block size")

    fs = LittleFS(
        block_size=block_size,
        block_count=fs_size // block_size,
        read_size=1,
        prog_size=1,
        cache_size=block_size,
        lookahead_size=32,
        block_cycles=500,
        name_max=64,
        disk_version=parse_littlefs_version(littlefs_version),
        mount=False,
    )
    fs.format()
    fs.mount()

    file_count, skipped_count = add_source_tree(fs, source_dir)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(fs.context.buffer)
    return file_count, skipped_count


def main() -> int:
    root = Path(__file__).resolve().parent

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "variant",
        nargs="?",
        default=DEFAULT_VARIANT,
        type=validate_variant,
        help=f"Voice variant directory to package, default: {DEFAULT_VARIANT}",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=root,
        help="Audio repo root containing voice variant directories",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help=f"Output image path, default: build/<variant>/{DEFAULT_IMAGE_NAME}",
    )
    parser.add_argument(
        "--fs-size",
        type=parse_size,
        default=parse_size(DEFAULT_FS_SIZE),
        help=f"LittleFS image size, default: {DEFAULT_FS_SIZE} bytes for S3 audio-rosary partition",
    )
    parser.add_argument(
        "--block-size",
        type=parse_size,
        default=parse_size(DEFAULT_BLOCK_SIZE),
        help=f"LittleFS block size, default: {DEFAULT_BLOCK_SIZE}",
    )
    parser.add_argument(
        "--littlefs-version",
        default=DEFAULT_LITTLEFS_VERSION,
        help=f"LittleFS disk version, default: {DEFAULT_LITTLEFS_VERSION}",
    )
    args = parser.parse_args()

    repo_root = args.root.resolve()
    source_dir = repo_root / args.variant
    output_path = args.output or (repo_root / "build" / args.variant / DEFAULT_IMAGE_NAME)
    if not output_path.is_absolute():
        output_path = (Path.cwd() / output_path).resolve()

    try:
        file_count, skipped_count = build_audiofs(
            source_dir=source_dir,
            output_path=output_path,
            fs_size=args.fs_size,
            block_size=args.block_size,
            littlefs_version=args.littlefs_version,
        )
    except (OSError, ValueError) as exc:
        print(f"build failed: {exc}", file=sys.stderr)
        return 1

    print(
        f"[audiofs] Built {output_path} from {source_dir} "
        f"({file_count} files, {skipped_count} skipped, {args.fs_size} bytes)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
