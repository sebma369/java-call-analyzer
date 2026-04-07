"""Tests for LLM client module."""

from pathlib import Path

from src.integration.openai_client import (
    LLMConfig,
    build_chat_payload,
    call_llm_with_prompt,
    call_llm_with_conversation,
    create_llm_conversation,
    extract_response_text,
    get_default_llm_output_path,
    save_llm_output_text,
)


def test_build_chat_payload_basic_shape():
    """Payload should follow responses.create structure."""
    config = LLMConfig(endpoint="https://example.com", api_key="k", model="m")
    payload = build_chat_payload("hello", config)

    assert payload["model"] == "m"
    assert payload["instructions"]
    assert payload["input"] == "hello"


def test_extract_response_text_from_responses_output():
    raw = {
        "id": "resp_1",
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": "hello from responses"}
                ],
            }
        ],
    }
    assert extract_response_text(raw) == "hello from responses"


def test_call_llm_with_prompt_parses_response(monkeypatch):
    """LLM call should parse response text from API result."""
    config = LLMConfig(endpoint="https://example.com", api_key="k", model="m")

    class FakeResponse:
        def model_dump(self):
            return {
                "id": "resp_single",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": "public class DemoTest {}"}
                        ],
                    }
                ]
            }

    class FakeResponses:
        @staticmethod
        def create(**kwargs):
            return FakeResponse()

    class FakeClient:
        responses = FakeResponses()

    def fake_create_client(local_config):
        return FakeClient()

    monkeypatch.setattr("src.integration.openai_client._create_openai_client", fake_create_client)
    result = call_llm_with_prompt("hello", config)

    assert result.model == "m"
    assert result.response_text == "public class DemoTest {}"


def test_call_llm_with_conversation_reuses_history(monkeypatch):
    """Conversation call should chain requests with previous_response_id."""
    config = LLMConfig(endpoint="https://example.com", api_key="k", model="m")
    conversation = create_llm_conversation(system_prompt="sys")
    sent_payloads = []

    class FakeResponse:
        def __init__(self, response_id, content):
            self.response_id = response_id
            self.content = content

        def model_dump(self):
            return {
                "id": self.response_id,
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": self.content}
                        ],
                    }
                ]
            }

    class FakeResponses:
        _counter = 0

        @staticmethod
        def create(**kwargs):
            FakeResponses._counter += 1
            sent_payloads.append(kwargs)
            return FakeResponse(f"resp_{FakeResponses._counter}", "ok")

    class FakeClient:
        responses = FakeResponses()

    monkeypatch.setattr("src.integration.openai_client._create_openai_client", lambda _config: FakeClient())

    call_llm_with_conversation("hello", config, conversation)
    call_llm_with_conversation("next", config, conversation)

    assert len(sent_payloads) == 2
    assert sent_payloads[0]["input"][0]["content"] == "hello"
    assert "previous_response_id" not in sent_payloads[0]
    assert sent_payloads[1]["input"][0]["content"] == "next"
    assert sent_payloads[1]["previous_response_id"] == "resp_1"
    assert conversation.previous_response_id == "resp_2"


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
