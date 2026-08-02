# Smart Rosary Audio

Speech MP3 source and generated audio folders for the ESP32-S3 Smart Rosary
audio LittleFS partition.

## Layout

- `text.json` defines prayer texts and available TTS voice variants.
- `generate_audio.py` generates MP3 files through the local Chatterbox API.
- `pl-zofia/` contains generated Polish MP3s using `Zofia-PL.wav`.
- `pl-marek/` contains generated Polish MP3s using `Marek-PL.wav`.

Generated MP3 files are placed directly in each voice directory:

```text
pl-zofia/010.mp3
pl-zofia/020.mp3
pl-zofia/021.mp3
...
```

The firmware filesystem image packages one selected voice directory, so MP3
paths on the device are generic root paths such as `/010.mp3` and `/020.mp3`.

## Generate Audio

The default API endpoint is `http://192.168.3.201:8004`.
Chatterbox API docs are available at `http://192.168.3.201:8004/docs`.

Generate all Polish voice variants:

```sh
./generate_audio.py pl
```

Generate selected voice variants:

```sh
./generate_audio.py pl-zofia pl-marek
```

Regenerate selected clip IDs only:

```sh
./generate_audio.py pl-zofia --only 090
./generate_audio.py pl --only 030 031
```

Use a different Chatterbox endpoint:

```sh
./generate_audio.py pl-marek --api-url http://192.168.3.201:8004
```

## Chatterbox Settings

`generate_audio.py` calls the Chatterbox `/tts` endpoint and writes the returned
MP3 bytes to the selected voice directory.

The request uses these fixed generation options:

- `voice_mode`: `predefined`
- `output_format`: `mp3`
- `split_text`: `true`
- `stream`: `false`

Per-voice settings live in `text.json`. Current Polish voices use slow,
neutral speech parameters:

- `temperature`: `0.25`
- `exaggeration`: `0.12`
- `cfg_weight`: `0.35`
- `speed_factor`: `1.0`
- `chunk_size`: `240`

Each voice variant selects its Chatterbox voice file through
`predefined_voice_id`, for example `Zofia-PL.wav` or `Marek-PL.wav`.

## Add A Voice Variant

Add a new entry under `voices` in `text.json`. The key should be
`language-voice`, for example `pl-marek`, `de-anna`, or `en-john`.

Example:

```json
"pl-marek": {
  "texts": "pl",
  "language": "polish",
  "voice": "Marek PL",
  "predefined_voice_id": "Marek-PL.wav",
  "temperature": 0.25,
  "exaggeration": 0.12,
  "cfg_weight": 0.35,
  "speed_factor": 1.0,
  "chunk_size": 240,
  "output_format": "mp3"
}
```

The generator expands a language key to all matching voice variants. For
example, `./generate_audio.py pl` generates every `pl-*` voice.

## Add A Language

Add a new text set under `texts`, then add one or more voice variants that point
to it. Planned language keys include `en`, `de`, `pl`, `fr`, `es`, and `pt`.

The `language` field is sent to Chatterbox. Common language names such as
`polish`, `german`, `english`, `french`, `spanish`, and `portuguese` are mapped
to their API codes.

## Firmware Packaging

The firmware repo selects the audio directory with `custom_audio_language` in
`platformio.ini`.

```ini
custom_audio_data_dir = /Users/lech/Projects/smartrosary-audio
custom_audio_language = pl-zofia
```

Build the ESP32-S3 filesystem image from the firmware repo:

```sh
/Users/lech/.platformio/penv/bin/pio run -e esp32-s3-touch-amoled-1-75 -t buildfs
```

This creates `audio.bin` from the selected voice directory and flashes it to the
S3 `audio` partition when using `uploadfs`.
