"""AI temel veri sınıfları ve görev önerisi ayrıştırma testleri."""

from linwas.ai.base import extract_task_suggestion


class TestExtractTaskSuggestion:
    def test_no_tag_returns_unchanged(self):
        text = "Just a normal response."
        clean, suggestion = extract_task_suggestion(text)
        assert clean == text
        assert suggestion is None

    def test_valid_tag_extracted(self):
        tag = (
            '<linwas_task op_id="package.install" params=\'{"name": "vlc"}\'>'
            "Install VLC</linwas_task>"
        )
        text = f"You should install VLC.\n{tag}"
        clean, suggestion = extract_task_suggestion(text)
        assert "<linwas_task" not in clean
        assert suggestion is not None
        assert suggestion.op_id == "package.install"
        assert suggestion.params == {"name": "vlc"}
        assert suggestion.label == "Install VLC"

    def test_tag_removed_from_text(self):
        tag = (
            '<linwas_task op_id="service.restart" params=\'{"name":"ssh"}\'>'
            "Restart SSH</linwas_task>"
        )
        text = f"Here is advice.{tag}"
        clean, _ = extract_task_suggestion(text)
        assert clean.strip() == "Here is advice."

    def test_invalid_json_params_returns_none(self):
        text = "<linwas_task op_id=\"package.install\" params='NOT JSON'>label</linwas_task>"
        _, suggestion = extract_task_suggestion(text)
        assert suggestion is None

    def test_params_coerced_to_str(self):
        text = '<linwas_task op_id="package.install" params=\'{"count": 1}\'>label</linwas_task>'
        _, suggestion = extract_task_suggestion(text)
        assert suggestion is not None
        assert suggestion.params["count"] == "1"

    def test_empty_text(self):
        clean, suggestion = extract_task_suggestion("")
        assert clean == ""
        assert suggestion is None
