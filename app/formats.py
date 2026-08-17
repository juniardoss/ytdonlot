"""Preset kualitas.

User HANYA boleh memilih salah satu id di bawah. String format yt-dlp yang
sebenarnya tidak pernah datang dari input user -- kalau dibiarkan, opsi
seperti --exec atau -o bisa dipakai untuk menjalankan perintah di server.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Preset:
    id: str
    label: str
    fmt: str
    ext: str
    audio_only: bool = False


_PRESETS = [
    Preset("audio_mp3", "Audio saja (MP3)", "bestaudio/best", "mp3", audio_only=True),
    Preset("360p", "Video 360p", "bv*[height<=360]+ba/b[height<=360]", "mp4"),
    Preset("720p", "Video 720p", "bv*[height<=720]+ba/b[height<=720]", "mp4"),
    Preset("1080p", "Video 1080p", "bv*[height<=1080]+ba/b[height<=1080]", "mp4"),
    Preset("best", "Kualitas terbaik", "bv*+ba/b", "mp4"),
]

PRESETS: dict[str, Preset] = {p.id: p for p in _PRESETS}
DEFAULT_PRESET = "720p"


def get_preset(preset_id: str) -> Preset | None:
    return PRESETS.get(preset_id)


def list_presets() -> list[dict]:
    return [{"id": p.id, "label": p.label, "ext": p.ext} for p in _PRESETS]
