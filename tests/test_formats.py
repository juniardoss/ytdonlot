from app.formats import DEFAULT_PRESET, PRESETS, get_preset, list_presets


def test_preset_default_ada():
    assert DEFAULT_PRESET in PRESETS


def test_preset_tidak_dikenal_mengembalikan_none():
    # Ini yang mencegah string format sembarangan masuk ke yt-dlp.
    assert get_preset("--exec=rm -rf /") is None
    assert get_preset("") is None


def test_list_presets_tidak_membocorkan_string_format():
    # Frontend tidak perlu tahu format yt-dlp, dan tidak boleh bisa mengirimnya balik.
    for item in list_presets():
        assert set(item) == {"id", "label", "ext"}


def test_preset_audio_menghasilkan_mp3():
    preset = get_preset("audio_mp3")
    assert preset is not None
    assert preset.audio_only
    assert preset.ext == "mp3"
