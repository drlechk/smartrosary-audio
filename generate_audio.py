#!/usr/bin/env python3
"""Generate Smart Rosary speech MP3 files from text.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_API_URL = "http://192.168.3.201:8004"
LANGUAGE_ALIASES = {
    "english": "en",
    "french": "fr",
    "german": "de",
    "polish": "pl",
    "portuguese": "pt",
    "spanish": "es",
}


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


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


def generate_variant(api_url: str, root: Path, variant_key: str, config: dict, texts: dict, only: set[str]) -> None:
    if not isinstance(texts, dict) or not texts:
        raise ValueError(f"{variant_key}: missing texts")

    output_dir = root / variant_key
    output_dir.mkdir(parents=True, exist_ok=True)

    for clip_id in sorted(texts):
        if only and clip_id not in only:
            continue

        payload = {
            "text": texts[clip_id],
            "voice_mode": "predefined",
            "predefined_voice_id": config["predefined_voice_id"],
            "output_format": config.get("output_format", "mp3"),
            "split_text": True,
            "chunk_size": config.get("chunk_size"),
            "temperature": config.get("temperature"),
            "exaggeration": config.get("exaggeration"),
            "cfg_weight": config.get("cfg_weight"),
            "speed_factor": config.get("speed_factor"),
            "language": api_language(config.get("language")),
            "stream": False,
        }
        payload = {key: value for key, value in payload.items() if value is not None}

        output_path = output_dir / f"{clip_id}.mp3"
        print(f"[tts] {variant_key}/{clip_id}.mp3 voice={config.get('voice', config['predefined_voice_id'])}")
        output_path.write_bytes(post_tts(api_url, payload))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "targets",
        nargs="*",
        help="Voice variants or language groups to generate, e.g. pl-zofia pl-marek or pl",
    )
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument(
        "--language",
        "-l",
        action="append",
        default=[],
        help="Deprecated alias for a positional target",
    )
    parser.add_argument("--text-json", type=Path, default=Path(__file__).with_name("text.json"))
    parser.add_argument("--only", nargs="*", default=[], help="Clip ids to regenerate, e.g. 010 020")
    args = parser.parse_args()

    root = args.text_json.resolve().parent
    config = load_config(args.text_json)
    voices = voice_configs(config)
    targets = args.targets or args.language or ["pl"]

    try:
        variants = expand_targets(targets, voices)
        for variant_key in variants:
            voice_config = voices[variant_key]
            texts = resolve_texts(config, variant_key, voice_config)
            generate_variant(args.api_url, root, variant_key, voice_config, texts, set(args.only))
    except (HTTPError, URLError, RuntimeError, OSError, ValueError) as exc:
        print(f"generation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
