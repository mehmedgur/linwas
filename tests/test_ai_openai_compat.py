"""OpenAI uyumlu sağlayıcı testleri (ağ yok; urllib sahte yanıt döner)."""

import io
import json
import urllib.error

import pytest

from linwas.ai import openai_compat
from linwas.ai.base import AIError, Message


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def http(monkeypatch):
    """urlopen yerine: istekleri kaydeder, kuyruktaki yanıtları sırayla döner."""
    state = {"requests": [], "responses": []}

    def fake_urlopen(req, timeout=0):
        state["requests"].append(req)
        item = state["responses"].pop(0)
        if isinstance(item, Exception):
            raise item
        return _Resp(json.dumps(item).encode())

    monkeypatch.setattr(openai_compat.urllib.request, "urlopen", fake_urlopen)
    return state


def test_list_models_filters_non_chat(http):
    http["responses"].append({"data": [{"id": "gpt-4o"}, {"id": "text-embed-3"}, {"id": "a"}]})
    assert openai_compat.CHATGPT.list_models("k") == ["a", "gpt-4o"]
    req = http["requests"][0]
    assert req.full_url == "https://api.openai.com/v1/models"
    assert req.get_header("Authorization") == "Bearer k"


def test_chat_payload_and_usage(http):
    http["responses"].append(
        {
            "choices": [{"message": {"content": "Merhaba"}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3},
        }
    )
    resp = openai_compat.DEEPSEEK.chat([Message("user", "selam")], "deepseek-chat", "k")
    assert (resp.text, resp.input_tokens, resp.output_tokens) == ("Merhaba", 7, 3)
    req = http["requests"][0]
    assert req.full_url == "https://api.deepseek.com/chat/completions"
    body = json.loads(req.data)
    assert body["messages"] == [{"role": "user", "content": "selam"}]
    assert body["model"] == "deepseek-chat" and body["max_tokens"] == 2048


def test_chat_sends_images_only_with_vision(http):
    http["responses"].append({"choices": [{"message": {"content": "ok"}}]})
    msg = Message("user", "bak", images=[b"\xff\xd8"])
    openai_compat.CHATGPT.chat([msg], "gpt-4o", "k")
    content = json.loads(http["requests"][0].data)["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "bak"}
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_http_error_is_sanitized_ai_error(http):
    err = urllib.error.HTTPError(
        "u", 401, "no", {}, io.BytesIO(b'{"error": "bad key for /home/ali"}')
    )
    http["responses"].append(err)
    with pytest.raises(AIError) as exc:
        openai_compat.CHATGPT.chat([Message("user", "x")], "gpt-4o-mini", "k")
    assert exc.value.status == 401 and "HTTP 401" in str(exc.value)


def test_connection_error(http):
    http["responses"].append(urllib.error.URLError("offline"))
    with pytest.raises(AIError, match="offline"):
        openai_compat.CHATGPT.list_models("k")


def test_deepseek_vision_from_model_info(http):
    http["responses"] += [{"input_modalities": ["text", "image"]}, urllib.error.URLError("x")]
    assert openai_compat.DEEPSEEK.supports_vision("m", "k") is True
    assert openai_compat.DEEPSEEK.supports_vision("m", "k") is False
