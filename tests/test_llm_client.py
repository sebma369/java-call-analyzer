"""Tests for LLM client module."""

from pathlib import Path

from src.integration.openai_client import (
    LLMConfig,
    build_chat_payload,
    call_llm_with_prompt,
    extract_response_text,
    get_default_llm_output_path,
    save_llm_output_text,
)


def test_build_chat_payload_basic_shape():
    """Payload should follow chat-completions structure."""
    config = LLMConfig(endpoint="https://example.com", api_key="k", model="m")
    payload = build_chat_payload("hello", config)

    assert payload["model"] == "m"
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][1]["content"] == "hello"


def test_extract_response_text_from_choices():
    """Extractor should read assistant content from first choice."""
    raw = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "public class DemoTest {}",
                }
            }
        ]
    }
    assert extract_response_text(raw) == "public class DemoTest {}"


def test_call_llm_with_prompt_parses_response(monkeypatch):
    """LLM call should parse response text from API result."""
    config = LLMConfig(endpoint="https://example.com", api_key="k", model="m")

    class FakeResponse:
        def model_dump(self):
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "public class DemoTest {}",
                        }
                    }
                ]
            }

    class FakeCompletions:
        @staticmethod
        def create(**kwargs):
            return FakeResponse()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    def fake_create_client(local_config):
        return FakeClient()

    monkeypatch.setattr("src.integration.openai_client._create_openai_client", fake_create_client)
    result = call_llm_with_prompt("hello", config)

    assert result.model == "m"
    assert result.response_text == "public class DemoTest {}"


def test_default_llm_output_path_and_save(tmp_path):
    """LLM output should be saved under tmp/prompts directory."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    target_file = project_root / "Target.java"
    target_file.write_text("public class Target {}", encoding="utf-8")

    out_path = get_default_llm_output_path(str(project_root), str(target_file))
    assert str(project_root / "tmp" / "prompts") in out_path

    saved = save_llm_output_text("class T {}", out_path)
    assert Path(saved).is_file()
    assert Path(saved).read_text(encoding="utf-8") == "class T {}"
