#!/usr/bin/env python3
"""Build an ESP32-S3 Smart Rosary audio LittleFS image."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


DEFAULT_VARIANT = "pl-marek"
DEFAULT_FS_SIZE = "0x2C1000"
DEFAULT_BLOCK_SIZE = "4096"
DEFAULT_LITTLEFS_VERSION = "2.1"


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


def add_source_tree(fs: LittleFS, source_dir: Path) -> tuple[int, int]:
    file_count = 0
    skipped_count = 0

    for item in sorted(source_dir.rglob("*")):
        rel_path = item.relative_to(source_dir)
        fs_path = rel_path.as_posix()

        if item.name == ".DS_Store":
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
        help="Output image path, default: build/<variant>/audio.bin",
    )
    parser.add_argument(
        "--fs-size",
        type=parse_size,
        default=parse_size(DEFAULT_FS_SIZE),
        help=f"LittleFS image size, default: {DEFAULT_FS_SIZE} bytes for S3 audio partition",
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
    output_path = args.output or (repo_root / "build" / args.variant / "audio.bin")
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
