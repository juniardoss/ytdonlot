import pytest

from app.validators import UrlValidationError, validate_url

ALLOWED = ["youtube.com", "youtu.be", "vimeo.com"]


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=abc123",
        "https://youtu.be/abc123",
        "http://m.youtube.com/watch?v=abc123",
        "https://vimeo.com/12345",
    ],
)
def test_menerima_domain_yang_diizinkan(url):
    assert validate_url(url, ALLOWED)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://youtube.com/video",
        "http://169.254.169.254/latest/meta-data/",  # metadata cloud
        "http://127.0.0.1:8000/admin",
        "http://localhost/admin",
        "https://evil.com/video",
        # Domain yang hanya berakhiran mirip, bukan subdomain.
        "https://notyoutube.com/watch?v=1",
        "https://youtube.com.evil.com/watch?v=1",
        "",
        "   ",
    ],
)
def test_menolak_url_berbahaya(url):
    with pytest.raises(UrlValidationError):
        validate_url(url, ALLOWED)


def test_menolak_url_terlalu_panjang():
    with pytest.raises(UrlValidationError):
        validate_url("https://youtube.com/watch?v=" + "a" * 3000, ALLOWED)


def test_membuang_credential_dan_fragment():
    cleaned = validate_url("https://user:pass@youtube.com/watch?v=x#frag", ALLOWED)
    assert "user" not in cleaned
    assert "pass" not in cleaned
    assert "#frag" not in cleaned
    assert cleaned.startswith("https://youtube.com/watch")


def test_mempertahankan_query_string():
    cleaned = validate_url("https://www.youtube.com/watch?v=abc&t=30", ALLOWED)
    assert "v=abc" in cleaned
    assert "t=30" in cleaned
