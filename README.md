# Smart Rosary Audio

Speech MP3 source and generated audio folders for the ESP32-S3 Smart Rosary
audio LittleFS partition.

## Layout

- `basic-prayer-texts.json` defines prayer texts and available TTS voice variants.
- `languages/` is the `smartrosary-language` Git submodule with canonical device language definitions.
- `audio-languages/` contains audio-only normalized language text derived from the canonical submodule.
- `mystery-prefix.json` contains language-specific text used to prefix mystery title audio.
- `replace-for-audio.json` contains language-specific text replacements applied before TTS.
- `generate_audio.py` generates MP3 files through the local Chatterbox API.
- `pl-florian/` and `pl-seraphina/` contain generated Polish MP3s using the German multilingual voice references.
- `de-florian/` and `de-seraphina/` contain generated German MP3s using those same voice references.
- `en-florian/` and `en-seraphina/` contain generated English MP3s using those same voice references.

Generated MP3 files are placed directly in each voice directory:

```text
en-seraphina/010.mp3
en-seraphina/020.mp3
en-seraphina/021.mp3
...
```

The firmware filesystem image packages one selected voice directory, so MP3
paths on the device are generic root paths such as `/010.mp3` and `/020.mp3`.

## Generate Audio

The default API endpoint is `http://192.168.3.201:8004`.
Chatterbox API docs are available at `http://192.168.3.201:8004/docs`.

Generate all English voice variants:

```sh
./generate_audio.py en
```

Generate selected voice variants:

```sh
./generate_audio.py en-florian en-seraphina
```

Regenerate selected clip IDs only:

```sh
./generate_audio.py en-seraphina --only 090
./generate_audio.py en --only 030 031
./generate_audio.py en --only mT1 m11
```

Use a different Chatterbox endpoint:

```sh
./generate_audio.py en-seraphina --api-url http://192.168.3.201:8004
```

Use a different audio-only language text directory:

```sh
./generate_audio.py en --audio-languages-dir ./audio-languages
```

Use a different replacement file:

```sh
./generate_audio.py en --replace-for-audio ./replace-for-audio.json
```

Use a different mystery prefix file:

```sh
./generate_audio.py en --mystery-prefix ./mystery-prefix.json
```

Disable generated-MP3 trailing silence trimming:

```sh
./generate_audio.py en --no-trim-trailing-silence
```

## Chatterbox Settings

Audio generation requires a running
[Chatterbox TTS](https://github.com/resemble-ai/chatterbox) service. This repo
uses the local Chatterbox HTTP API at `http://192.168.3.201:8004`; its API docs
are available at `http://192.168.3.201:8004/docs`.

Current voice variants use the German multilingual references
`de-DE-FlorianMultilingualNeural.wav` and
`de-DE-SeraphinaMultilingualNeural.wav`.

`generate_audio.py` calls the Chatterbox `/tts` endpoint and writes the returned
MP3 bytes to the selected voice directory. For Polish, German, and English voices, it also reads
non-empty `mT1`..`mT5` and `m11`..`m55` mystery strings from
`audio-languages/<language>.json` and generates matching MP3 files such as `mT1.mp3`
and `m11.mp3`. That audio-only file is derived from the canonical `languages/`
submodule, but it strips display-only leading Roman numbering such as `I.` and
trailing whitespace or `-` characters before TTS. The canonical language
submodule remains unchanged for firmware and editor use.

For mystery title clips such as `m11.mp3`, `mystery-prefix.json` adds spoken
prefixes before TTS. Polish currently uses phrases such as `pierwsza tajemnica
radosna`; German uses phrases such as `erstes freudenreiches Geheimnis`;
English uses phrases such as `First Joyful Mystery`.

After language text is loaded and mystery prefixes are applied,
`replace-for-audio.json` applies ordered string replacements before the text is
sent to TTS. The file is scoped by language:

```json
{
  "pl": [
    { "from": "NMP", "to": "Najświętszej Maryi Panny" }
  ]
}
```

Every generated MP3 is postprocessed with `ffmpeg` to trim trailing low-level
audio once the tail is at least `0.5` seconds long. The default trim keeps
`0.15` seconds at the end and treats audio below `-30dB` as silence/noise floor.
It also trims when that low-level tail is followed by up to `0.75` seconds of
generated ramp/noise. Tune this with `--trim-silence-duration`,
`--trim-silence-keep`, `--trim-silence-threshold`, and
`--trim-trailing-noise-window`.

The request uses these fixed generation options:

- `voice_mode`: `predefined`
- `output_format`: `mp3`
- `split_text`: `true`
- `stream`: `false`

Per-voice settings live in `basic-prayer-texts.json`. Current voices use slow,
neutral speech parameters:

- `temperature`: `0.25`
- `exaggeration`: `0.12`
- `cfg_weight`: `0.35`
- `speed_factor`: `1.0`
- `chunk_size`: `240`

Each voice variant selects its Chatterbox voice file through
`predefined_voice_id`, for example `de-DE-SeraphinaMultilingualNeural.wav`.

## Add A Voice Variant

Add a new entry under `voices` in `basic-prayer-texts.json`. The key should be
`language-voice`, for example `en-seraphina`, `de-florian`, or `en-john`.

Example:

```json
"en-seraphina": {
  "texts": "en",
  "language": "english",
  "voice": "Seraphina Multilingual",
  "predefined_voice_id": "de-DE-SeraphinaMultilingualNeural.wav",
  "temperature": 0.25,
  "exaggeration": 0.12,
  "cfg_weight": 0.35,
  "speed_factor": 1.0,
  "chunk_size": 240,
  "output_format": "mp3"
}
```

The generator expands a language key to all matching voice variants. For
example, `./generate_audio.py en` generates every `en-*` voice.

## Add A Language

Add a new text set under `texts`, then add one or more voice variants that point
to it. Use the `languages/` submodule for the matching canonical device
language definitions, and put any spoken-only normalized strings in
`audio-languages/` so firmware language text remains unchanged. Planned language
keys include `en`, `de`, `pl`, `fr`, `es`, and `pt`.

The `language` field is sent to Chatterbox. Common language names such as
`polish`, `german`, `english`, `french`, `spanish`, and `portuguese` are mapped
to their API codes.

## Firmware Packaging

The firmware repo selects the audio directory with `custom_audio_language` in
`platformio.ini`.

```ini
custom_audio_data_dir = /Users/lech/Projects/smartrosary-audio
custom_audio_language = en-seraphina
```

Build the ESP32-S3 filesystem image from the firmware repo:

```sh
/Users/lech/.platformio/penv/bin/pio run -e esp32-s3-touch-amoled-1-75 -t buildfs
```

This creates `audio-rosary.bin` from the selected voice directory and flashes it
to the S3 `audio-rosary` partition when using `uploadfs`. Firmware build outputs keep
the image under the selected voice subdirectory, for example
`.pio/build/esp32-s3-touch-amoled-1-75/en-seraphina/audio-rosary.bin`.
The image also contains a generated `/audio-manifest.json` file with MP3
durations in milliseconds so firmware auto-play countdowns do not need to scan
MP3 frames at runtime.

## Standalone Audio Partition Image

`build_audiofs.py` creates the same kind of LittleFS image directly from this
audio repo. By default it packages `en-seraphina` using the ESP32-S3 `audio-rosary`
partition size, `0x134000` bytes. The separate S3 `audio-contemplation` space is
reserved for future content.
The standalone builder also embeds `/audio-manifest.json` with per-file MP3
durations in milliseconds.

Build the default image:

```sh
./build_audiofs.py
```

Build a specific voice variant:

```sh
./build_audiofs.py en-seraphina
./build_audiofs.py en-florian
```

Write to a custom output path:

```sh
./build_audiofs.py en-seraphina -o audio-rosary.bin
```

The default output is:

```text
build/<voice-variant>/audio-rosary.bin
```

The script uses the Python `littlefs` package. If the system Python does not
have it installed, the script automatically re-runs with PlatformIO's Python at
`~/.platformio/penv/bin/python`, which is the same environment used by the
firmware build.
