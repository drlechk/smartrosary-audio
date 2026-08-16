#!/usr/bin/env python3
"""Generate Smart Rosary speech MP3 files from basic-prayer-texts.json."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_API_URL = "http://192.168.3.201:8004"
DEFAULT_LANGUAGES_DIR = Path(__file__).with_name("languages")
DEFAULT_AUDIO_LANGUAGES_DIR = Path(__file__).with_name("audio-languages")
DEFAULT_REPLACE_FOR_AUDIO = Path(__file__).with_name("replace-for-audio.json")
DEFAULT_MYSTERY_PREFIX = Path(__file__).with_name("mystery-prefix.json")
DEFAULT_TRIM_SILENCE_DURATION = 0.5
DEFAULT_TRIM_SILENCE_KEEP = 0.15
DEFAULT_TRIM_SILENCE_THRESHOLD = "-30dB"
DEFAULT_TRIM_TRAILING_NOISE_WINDOW = 0.75
DEFAULT_RAW_DIR = "raw"
DEFAULT_AUTO_EDITOR = "auto-editor"
POSTPROCESS_TOOLS = ("auto", "auto-editor", "ffmpeg", "none")
SENTENCE_END_RE = re.compile(r"([^.!?]+)([.!?]*)")
LANGUAGE_ALIASES = {
    "english": "en",
    "french": "fr",
    "german": "de",
    "italian": "it",
    "latin": "la",
    "polish": "pl",
    "portuguese": "pt",
    "spanish": "es",
}
LANGUAGE_AUDIO_KEYS = {
    "de": (
        re.compile(r"^mT[1-5]$"),
        re.compile(r"^m[1-5][1-5]$"),
    ),
    "en": (
        re.compile(r"^mT[1-5]$"),
        re.compile(r"^m[1-5][1-5]$"),
    ),
    "es": (
        re.compile(r"^mT[1-5]$"),
        re.compile(r"^m[1-5][1-5]$"),
    ),
    "fr": (
        re.compile(r"^mT[1-5]$"),
        re.compile(r"^m[1-5][1-5]$"),
    ),
    "it": (
        re.compile(r"^mT[1-5]$"),
        re.compile(r"^m[1-5][1-5]$"),
    ),
    "la": (
        re.compile(r"^mT[1-5]$"),
        re.compile(r"^m[1-5][1-5]$"),
    ),
    "pl": (
        re.compile(r"^mT[1-5]$"),
        re.compile(r"^m[1-5][1-5]$"),
    ),
    "pt": (
        re.compile(r"^mT[1-5]$"),
        re.compile(r"^m[1-5][1-5]$"),
    ),
}


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_language_fixture(languages_dir: Path, language_key: str) -> dict | None:
    fixture_path = languages_dir / "fixtures" / f"{language_key}.json"
    if fixture_path.exists():
        with fixture_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    fixture_path = languages_dir / "fixtures" / f"{language_key}.js"
    if not fixture_path.exists():
        return None

    source = fixture_path.read_text(encoding="utf-8")
    start = source.find("{")
    end = source.rfind("}")
    if start < 0 or end < start:
        raise ValueError(f"{fixture_path}: cannot find fixture JSON object")

    return json.loads(source[start:end + 1])


def audio_text_from_language_value(value: str) -> str:
    text = re.sub(r"\s+", " ", value.replace("\r", "\n")).strip()
    text = re.sub(r"^(?=[MDCLXVI]+\.\s+)[MDCLXVI]+\.\s*", "", text, flags=re.IGNORECASE)
    return re.sub(r"[\s-]+$", "", text).strip()


def load_audio_language_texts(audio_languages_dir: Path, language_key: str) -> dict[str, str]:
    audio_language_path = audio_languages_dir / f"{language_key}.json"
    if not audio_language_path.exists():
        return {}

    with audio_language_path.open("r", encoding="utf-8") as handle:
        audio_language = json.load(handle)

    texts = audio_language.get("texts", {})
    if not isinstance(texts, dict):
        raise ValueError(f"{audio_language_path}: texts must be an object")

    return {
        str(key): str(value)
        for key, value in texts.items()
        if str(value).strip()
    }


def load_audio_replacements(path: Path, language_key: str) -> list[dict[str, str]]:
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)

    rules: list[dict[str, str]] = []
    for scope in ("*", language_key):
        scoped_rules = config.get(scope, [])
        if not isinstance(scoped_rules, list):
            raise ValueError(f"{path}: {scope} replacements must be a list")
        for index, rule in enumerate(scoped_rules):
            if not isinstance(rule, dict):
                raise ValueError(f"{path}: {scope}[{index}] must be an object")
            source = rule.get("from")
            replacement = rule.get("to")
            if not isinstance(source, str) or not source:
                raise ValueError(f"{path}: {scope}[{index}].from must be a non-empty string")
            if not isinstance(replacement, str):
                raise ValueError(f"{path}: {scope}[{index}].to must be a string")
            rules.append({"from": source, "to": replacement})

    return rules


def load_mystery_prefix(path: Path, language_key: str) -> dict:
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)

    prefix = config.get(language_key, {})
    if not isinstance(prefix, dict):
        raise ValueError(f"{path}: {language_key} prefix must be an object")
    return prefix


def apply_mystery_prefixes(texts: dict[str, str], prefix: dict) -> dict[str, str]:
    if not prefix:
        return texts

    template = str(prefix.get("template") or "{ordinal} {noun} {set}. {title}")
    noun = str(prefix.get("noun") or "mystery")
    ordinals = prefix.get("ordinals", {})
    sets = prefix.get("sets", {})
    if not isinstance(ordinals, dict) or not isinstance(sets, dict):
        raise ValueError("mystery prefix ordinals and sets must be objects")

    prefixed: dict[str, str] = {}
    for key, value in texts.items():
        match = re.match(r"^m([1-5])([1-5])$", key)
        if not match:
            prefixed[key] = value
            continue

        mystery_number, set_number = match.groups()
        ordinal = ordinals.get(mystery_number)
        set_name = sets.get(set_number)
        if not isinstance(ordinal, str) or not isinstance(set_name, str):
            prefixed[key] = value
            continue

        prefixed[key] = template.format(
            ordinal=ordinal,
            noun=noun,
            set=set_name,
            title=value,
        ).strip()

    return prefixed


def apply_audio_replacements(text: str, replacements: list[dict[str, str]]) -> str:
    for rule in replacements:
        text = text.replace(rule["from"], rule["to"])
    return text


def apply_audio_text_replacements(
    texts: dict[str, str],
    replacements: list[dict[str, str]],
) -> dict[str, str]:
    if not replacements:
        return texts
    return {
        key: apply_audio_replacements(value, replacements)
        for key, value in texts.items()
    }


def language_audio_texts(languages_dir: Path, language_key: str) -> dict[str, str]:
    key_patterns = LANGUAGE_AUDIO_KEYS.get(language_key)
    if key_patterns is None:
        return {}

    fixture = load_language_fixture(languages_dir, language_key)
    if fixture is None:
        return {}

    entries = fixture.get("state", {}).get("entries", [])
    texts: dict[str, str] = {}
    for entry in entries:
        key = entry.get("key")
        value = entry.get("value")
        if entry.get("namespace") != "mysteries" or not isinstance(key, str) or not isinstance(value, str):
            continue
        if not any(pattern.match(key) for pattern in key_patterns):
            continue

        text = audio_text_from_language_value(value)
        if text:
            texts[key] = text

    return texts


def post_tts(api_url: str, payload: dict) -> bytes:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        f"{api_url.rstrip('/')}/tts",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "audio/mpeg, audio/mp3, application/octet-stream",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=600) as response:
            content_type = response.headers.get("Content-Type", "")
            body = response.read()
            if "application/json" in content_type:
                raise RuntimeError(body.decode("utf-8", errors="replace"))
            return body
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def normalized_repeat_phrase(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().rstrip(".!?").casefold()


def repeated_sentence_plan(text: str) -> tuple[str, int] | None:
    parts: list[tuple[str, str]] = []
    for match in SENTENCE_END_RE.finditer(text):
        body = re.sub(r"\s+", " ", match.group(1)).strip()
        punctuation = match.group(2)
        if body:
            parts.append((body, punctuation))

    if len(parts) < 2:
        return None

    normalized = [normalized_repeat_phrase(body) for body, _ in parts]
    if not normalized[0] or any(value != normalized[0] for value in normalized[1:]):
        return None

    body, punctuation = parts[0]
    source_text = f"{body}{punctuation or '.'}"
    return source_text, len(parts)


def write_repeat_marker(path: Path, *, source_text: str, repeat_count: int) -> None:
    marker = {
        "source_text": source_text,
        "repeat_count": repeat_count,
    }
    path.write_text(json.dumps(marker, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def validate_repeat_marker(path: Path, *, source_text: str, repeat_count: int, raw_path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(
            f"repeat-source marker not found for {raw_path}; "
            "regenerate this repeated clip without --clean-only before rerunning cleanup"
        )

    with path.open("r", encoding="utf-8") as handle:
        marker = json.load(handle)
    if marker.get("source_text") != source_text or marker.get("repeat_count") != repeat_count:
        raise ValueError(
            f"repeat-source marker does not match current text for {raw_path}; "
            "regenerate this repeated clip without --clean-only"
        )


def trim_trailing_silence(
    output_path: Path,
    *,
    ffmpeg: str,
    duration: float,
    keep: float,
    threshold: str,
    trailing_noise_window: float,
) -> None:
    ffmpeg_path = shutil.which(ffmpeg) if not Path(ffmpeg).is_absolute() else ffmpeg
    if not ffmpeg_path:
        raise RuntimeError("ffmpeg not found; install ffmpeg or pass --no-trim-trailing-silence")

    ffprobe_path = shutil.which("ffprobe")
    if not ffprobe_path:
        raise RuntimeError("ffprobe not found; install ffmpeg or pass --no-trim-trailing-silence")

    duration_output = subprocess.check_output(
        [
            ffprobe_path,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(output_path),
        ],
        text=True,
    ).strip()
    media_duration = float(duration_output)

    detect = subprocess.run(
        [
            ffmpeg_path,
            "-hide_banner",
            "-nostats",
            "-i",
            str(output_path),
            "-af",
            f"silencedetect=noise={threshold}:d={duration}",
            "-f",
            "null",
            "-",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    silence_ranges: list[tuple[float, float]] = []
    current_start: float | None = None
    for line in detect.stderr.splitlines():
        start_match = re.search(r"silence_start:\s*([0-9.]+)", line)
        if start_match:
            current_start = float(start_match.group(1))
            continue

        end_match = re.search(r"silence_end:\s*([0-9.]+)", line)
        if end_match and current_start is not None:
            silence_ranges.append((current_start, float(end_match.group(1))))
            current_start = None

    if current_start is not None:
        silence_ranges.append((current_start, media_duration))

    final_silence = next(
        (
            (start, end)
            for start, end in reversed(silence_ranges)
            if end >= media_duration - 0.05 or media_duration - end <= trailing_noise_window
        ),
        None,
    )
    if final_silence is None:
        return

    silence_start, silence_end = final_silence
    if silence_end - silence_start < duration:
        return

    cutoff = min(media_duration, silence_start + keep)
    if cutoff >= media_duration - 0.02 or cutoff <= 0:
        return

    trimmed_path = output_path.with_name(f".{output_path.name}.trimmed.mp3")
    command = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(output_path),
        "-t",
        f"{cutoff:.3f}",
        "-codec:a",
        "libmp3lame",
        "-q:a",
        "2",
        str(trimmed_path),
    ]

    try:
        subprocess.run(command, check=True)
        if not trimmed_path.exists() or trimmed_path.stat().st_size <= 0:
            raise RuntimeError(f"ffmpeg produced an empty trimmed file for {output_path}")
        original_size = output_path.stat().st_size
        trimmed_size = trimmed_path.stat().st_size
        trimmed_path.replace(output_path)
        delta = original_size - trimmed_size
        if delta > 0:
            print(f"[trim] {output_path.parent.name}/{output_path.name} trailing silence trimmed ({delta} bytes)")
    finally:
        if trimmed_path.exists():
            trimmed_path.unlink()


def resolve_auto_editor_command(auto_editor: str) -> str | None:
    if Path(auto_editor).is_absolute():
        return auto_editor if Path(auto_editor).is_file() else None

    return shutil.which(auto_editor)


def run_auto_editor(
    input_path: Path,
    output_path: Path,
    *,
    auto_editor: str,
    threshold: str,
    keep: float,
) -> None:
    auto_editor_path = resolve_auto_editor_command(auto_editor)
    if not auto_editor_path:
        raise RuntimeError("auto-editor not found; install auto-editor or use --postprocess-tool ffmpeg")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cleaned_path = output_path.with_name(f".{output_path.name}.auto-editor.mp3")
    command = [
        auto_editor_path,
        str(input_path),
        "-o",
        str(cleaned_path),
        "--edit",
        f"audio:{threshold}",
        "--margin",
        f"0s,{keep}s",
    ]

    try:
        subprocess.run(command, check=True)
        if not cleaned_path.exists() or cleaned_path.stat().st_size <= 0:
            raise RuntimeError(f"auto-editor produced an empty file for {input_path}")
        cleaned_path.replace(output_path)
        print(f"[clean:auto-editor] {output_path.parent.name}/{output_path.name}")
    finally:
        if cleaned_path.exists():
            cleaned_path.unlink()


def postprocess_audio(
    raw_path: Path,
    output_path: Path,
    *,
    tool: str,
    auto_editor: str,
    ffmpeg: str,
    trim_duration: float,
    trim_keep: float,
    trim_threshold: str,
    trim_trailing_noise_window: float,
) -> None:
    selected_tool = tool
    if selected_tool == "auto":
        selected_tool = "auto-editor" if resolve_auto_editor_command(auto_editor) else "ffmpeg"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if selected_tool == "none":
        shutil.copy2(raw_path, output_path)
        print(f"[clean:none] {output_path.parent.name}/{output_path.name}")
        return

    if selected_tool == "auto-editor":
        run_auto_editor(
            raw_path,
            output_path,
            auto_editor=auto_editor,
            threshold=trim_threshold,
            keep=trim_keep,
        )
        return

    if selected_tool == "ffmpeg":
        shutil.copy2(raw_path, output_path)
        trim_trailing_silence(
            output_path,
            ffmpeg=ffmpeg,
            duration=trim_duration,
            keep=trim_keep,
            threshold=trim_threshold,
            trailing_noise_window=trim_trailing_noise_window,
        )
        print(f"[clean:ffmpeg] {output_path.parent.name}/{output_path.name}")
        return

    raise ValueError(f"unknown postprocess tool: {tool}")


def ffmpeg_binary(ffmpeg: str) -> str:
    ffmpeg_path = shutil.which(ffmpeg) if not Path(ffmpeg).is_absolute() else ffmpeg
    if not ffmpeg_path:
        raise RuntimeError("ffmpeg not found; install ffmpeg")
    return str(ffmpeg_path)


def concat_audio_copies(source_path: Path, output_path: Path, *, count: int, ffmpeg: str) -> None:
    if count < 2:
        raise ValueError("repeat count must be at least 2")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{output_path.stem}-repeat-", dir=output_path.parent) as temp_dir:
        temp_path = Path(temp_dir)
        list_path = temp_path / "concat.txt"
        repeated_path = temp_path / output_path.name
        escaped_source = str(source_path.resolve()).replace("'", "'\\''")
        list_path.write_text(
            "".join(f"file '{escaped_source}'\n" for _ in range(count)),
            encoding="utf-8",
        )
        subprocess.run(
            [
                ffmpeg_binary(ffmpeg),
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_path),
                "-codec:a",
                "libmp3lame",
                "-q:a",
                "2",
                str(repeated_path),
            ],
            check=True,
        )
        if not repeated_path.exists() or repeated_path.stat().st_size <= 0:
            raise RuntimeError(f"ffmpeg produced an empty repeated file for {output_path}")
        repeated_path.replace(output_path)
    print(f"[repeat] {output_path.parent.name}/{output_path.name} assembled from {count} cleaned copies")


def postprocess_repeated_audio(
    raw_path: Path,
    output_path: Path,
    *,
    repeat_count: int,
    tool: str,
    auto_editor: str,
    ffmpeg: str,
    trim_duration: float,
    trim_keep: float,
    trim_threshold: str,
    trim_trailing_noise_window: float,
) -> None:
    with tempfile.TemporaryDirectory(prefix=f".{output_path.stem}-single-", dir=output_path.parent) as temp_dir:
        cleaned_source = Path(temp_dir) / output_path.name
        postprocess_audio(
            raw_path,
            cleaned_source,
            tool=tool,
            auto_editor=auto_editor,
            ffmpeg=ffmpeg,
            trim_duration=trim_duration,
            trim_keep=trim_keep,
            trim_threshold=trim_threshold,
            trim_trailing_noise_window=trim_trailing_noise_window,
        )
        concat_audio_copies(cleaned_source, output_path, count=repeat_count, ffmpeg=ffmpeg)


def api_language(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return LANGUAGE_ALIASES.get(normalized.lower(), normalized)


def variant_language(variant_key: str) -> str:
    return variant_key.split("-", 1)[0]


def voice_configs(config: dict) -> dict[str, dict]:
    voices = config.get("voices")
    if isinstance(voices, dict):
        return voices

    # Backward-compatible legacy format:
    # {"pl": {"texts": {...}, "predefined_voice_id": "..."}}
    return {
        key: value
        for key, value in config.items()
        if isinstance(value, dict) and isinstance(value.get("texts"), dict)
    }


def resolve_texts(all_config: dict, variant_key: str, config: dict) -> dict:
    texts_ref = config.get("texts")
    if isinstance(texts_ref, dict):
        return texts_ref

    text_sets = all_config.get("texts", {})
    if isinstance(texts_ref, str) and isinstance(text_sets, dict):
        texts = text_sets.get(texts_ref)
        if isinstance(texts, dict):
            return texts

    language_key = variant_language(variant_key)
    if isinstance(text_sets, dict):
        texts = text_sets.get(language_key)
        if isinstance(texts, dict):
            return texts

    raise ValueError(f"{variant_key}: missing texts")


def expand_targets(targets: list[str], voices: dict[str, dict]) -> list[str]:
    expanded: list[str] = []
    for target in targets:
        target = target.strip()
        if not target:
            continue

        if target in voices:
            matches = [target]
        else:
            matches = [
                key for key in sorted(voices)
                if variant_language(key) == target
            ]

        if not matches:
            raise ValueError(f"target '{target}' not found")

        for key in matches:
            if key not in expanded:
                expanded.append(key)
    return expanded


def generate_variant(
    api_url: str,
    root: Path,
    variant_key: str,
    config: dict,
    texts: dict,
    only: set[str],
    *,
    raw_root: Path,
    clean_only: bool,
    raw_only: bool,
    postprocess_tool: str,
    auto_editor: str,
    ffmpeg: str,
    trim_duration: float,
    trim_keep: float,
    trim_threshold: str,
    trim_trailing_noise_window: float,
) -> None:
    if not isinstance(texts, dict) or not texts:
        raise ValueError(f"{variant_key}: missing texts")

    output_dir = root / variant_key
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = raw_root / variant_key
    raw_dir.mkdir(parents=True, exist_ok=True)

    for clip_id in sorted(texts):
        if only and clip_id not in only:
            continue

        text = texts[clip_id]
        repeat_plan = repeated_sentence_plan(text)
        if repeat_plan is None:
            tts_text = text
        else:
            tts_text, _repeat_count = repeat_plan

        payload = {
            "text": tts_text,
            "voice_mode": "predefined",
            "predefined_voice_id": config["predefined_voice_id"],
            "output_format": config.get("output_format", "mp3"),
            "split_text": True,
            "chunk_size": config.get("chunk_size"),
            "temperature": config.get("temperature"),
            "exaggeration": config.get("exaggeration"),
            "cfg_weight": config.get("cfg_weight"),
            "speed_factor": config.get("speed_factor"),
            "language": api_language(config.get("tts_language", config.get("language"))),
            "stream": False,
        }
        payload = {key: value for key, value in payload.items() if value is not None}

        raw_path = raw_dir / f"{clip_id}.mp3"
        repeat_marker_path = raw_dir / f".{clip_id}.repeat.json"
        output_path = output_dir / f"{clip_id}.mp3"
        if clean_only:
            if not raw_path.exists():
                raise FileNotFoundError(f"raw Chatterbox file not found: {raw_path}")
            if repeat_plan is not None:
                source_text, repeat_count = repeat_plan
                validate_repeat_marker(
                    repeat_marker_path,
                    source_text=source_text,
                    repeat_count=repeat_count,
                    raw_path=raw_path,
                )
        else:
            print(f"[tts:raw] {variant_key}/{clip_id}.mp3 voice={config.get('voice', config['predefined_voice_id'])}")
            raw_path.write_bytes(post_tts(api_url, payload))
            if repeat_plan is not None:
                source_text, repeat_count = repeat_plan
                write_repeat_marker(repeat_marker_path, source_text=source_text, repeat_count=repeat_count)
                print(f"[repeat:raw] {variant_key}/{clip_id}.mp3 source sentence x{repeat_count}")
            elif repeat_marker_path.exists():
                repeat_marker_path.unlink()

        if raw_only:
            continue

        if repeat_plan is None:
            postprocess_audio(
                raw_path,
                output_path,
                tool=postprocess_tool,
                auto_editor=auto_editor,
                ffmpeg=ffmpeg,
                trim_duration=trim_duration,
                trim_keep=trim_keep,
                trim_threshold=trim_threshold,
                trim_trailing_noise_window=trim_trailing_noise_window,
            )
        else:
            _source_text, repeat_count = repeat_plan
            postprocess_repeated_audio(
                raw_path,
                output_path,
                repeat_count=repeat_count,
                tool=postprocess_tool,
                auto_editor=auto_editor,
                ffmpeg=ffmpeg,
                trim_duration=trim_duration,
                trim_keep=trim_keep,
                trim_threshold=trim_threshold,
                trim_trailing_noise_window=trim_trailing_noise_window,
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "targets",
        nargs="*",
        help="Voice variants or language groups to generate, e.g. en-florian en-seraphina or en",
    )
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument(
        "--language",
        "-l",
        action="append",
        default=[],
        help="Deprecated alias for a positional target",
    )
    parser.add_argument("--text-json", type=Path, default=Path(__file__).with_name("basic-prayer-texts.json"))
    parser.add_argument("--languages-dir", type=Path, default=DEFAULT_LANGUAGES_DIR)
    parser.add_argument("--audio-languages-dir", type=Path, default=DEFAULT_AUDIO_LANGUAGES_DIR)
    parser.add_argument("--replace-for-audio", type=Path, default=DEFAULT_REPLACE_FOR_AUDIO)
    parser.add_argument("--mystery-prefix", type=Path, default=DEFAULT_MYSTERY_PREFIX)
    parser.add_argument("--raw-dir", type=Path, default=Path(DEFAULT_RAW_DIR))
    parser.add_argument("--raw-only", action="store_true", help="Generate raw Chatterbox MP3s only")
    parser.add_argument("--clean-only", action="store_true", help="Rebuild final MP3s from existing raw files without TTS")
    parser.add_argument(
        "--postprocess-tool",
        choices=POSTPROCESS_TOOLS,
        default="auto",
        help="Tool used to clean raw MP3s into final variant folders",
    )
    parser.add_argument("--no-trim-trailing-silence", action="store_true", help="Deprecated alias for --postprocess-tool none")
    parser.add_argument("--auto-editor", default=DEFAULT_AUTO_EDITOR)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--trim-silence-duration", type=float, default=DEFAULT_TRIM_SILENCE_DURATION)
    parser.add_argument("--trim-silence-keep", type=float, default=DEFAULT_TRIM_SILENCE_KEEP)
    parser.add_argument("--trim-silence-threshold", default=DEFAULT_TRIM_SILENCE_THRESHOLD)
    parser.add_argument("--trim-trailing-noise-window", type=float, default=DEFAULT_TRIM_TRAILING_NOISE_WINDOW)
    parser.add_argument("--only", nargs="*", default=[], help="Clip ids to regenerate, e.g. 010 020")
    args = parser.parse_args()

    root = args.text_json.resolve().parent
    if args.raw_only and args.clean_only:
        parser.error("--raw-only and --clean-only cannot be used together")
    if args.no_trim_trailing_silence:
        args.postprocess_tool = "none"

    raw_root = args.raw_dir
    if not raw_root.is_absolute():
        raw_root = root / raw_root
    raw_root = raw_root.resolve()

    config = load_config(args.text_json)
    voices = voice_configs(config)
    targets = args.targets or args.language or ["pl"]

    try:
        variants = expand_targets(targets, voices)
        for variant_key in variants:
            voice_config = voices[variant_key]
            texts = resolve_texts(config, variant_key, voice_config)
            language_key = variant_language(variant_key)
            audio_language_texts = load_audio_language_texts(args.audio_languages_dir, language_key)
            if not audio_language_texts:
                audio_language_texts = language_audio_texts(args.languages_dir, language_key)
            audio_language_texts = apply_mystery_prefixes(
                audio_language_texts,
                load_mystery_prefix(args.mystery_prefix, language_key),
            )
            audio_language_texts = apply_audio_text_replacements(
                audio_language_texts,
                load_audio_replacements(args.replace_for_audio, language_key),
            )
            texts = {
                **audio_language_texts,
                **texts,
            }
            generate_variant(
                args.api_url,
                root,
                variant_key,
                voice_config,
                texts,
                set(args.only),
                raw_root=raw_root,
                clean_only=args.clean_only,
                raw_only=args.raw_only,
                postprocess_tool=args.postprocess_tool,
                auto_editor=args.auto_editor,
                ffmpeg=args.ffmpeg,
                trim_duration=args.trim_silence_duration,
                trim_keep=args.trim_silence_keep,
                trim_threshold=args.trim_silence_threshold,
                trim_trailing_noise_window=args.trim_trailing_noise_window,
            )
    except (HTTPError, URLError, RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"generation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
