"""Maskeleme (sanitizer) testleri."""

from linwas.core.sanitizer import sanitize


def test_bearer_token_masked():
    text = "Authorization: Bearer eyJhbGciOiJSUzI1NiJ9.abc123"
    result = sanitize(text)
    assert "[MASKED]" in result
    assert "eyJhbGciOiJSUzI1NiJ9" not in result


def test_api_key_eq_masked():
    result = sanitize("api_key=sk-proj-ABCDEF123456")
    assert "[MASKED]" in result
    assert "sk-proj-ABCDEF123456" not in result


def test_password_colon_masked():
    result = sanitize("password: mysecretpassword")
    assert "[MASKED]" in result
    assert "mysecretpassword" not in result


def test_url_key_param_masked():
    url = "https://generativelanguage.googleapis.com/v1beta/models?key=AIzaSyABCDEF"
    result = sanitize(url)
    assert "[MASKED]" in result
    assert "AIzaSyABCDEF" not in result


def test_authorization_header_masked():
    result = sanitize("Authorization: Bearer token123\nContent-Type: application/json")
    assert "[MASKED]" in result
    assert "token123" not in result
    assert "Content-Type: application/json" in result


def test_json_api_key_masked():
    text = '{"api_key": "sk-ABCDE", "model": "gpt-4"}'
    result = sanitize(text)
    assert "[MASKED]" in result
    assert "sk-ABCDE" not in result
    assert '"model": "gpt-4"' in result


def test_safe_text_unchanged():
    text = "Paket kuruldu: vlc 3.0.18"
    assert sanitize(text) == text


def test_empty_string():
    assert sanitize("") == ""


def test_multiline_mixed():
    text = "İşlem başladı\napi_key=secret123\nİşlem tamamlandı"
    result = sanitize(text)
    assert "secret123" not in result
    assert "İşlem başladı" in result
    assert "İşlem tamamlandı" in result
