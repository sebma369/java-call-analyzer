"""LLM client for sending structured prompts and receiving test code output."""

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from typing import Any


DEFAULT_LLM_ENDPOINT = "https://api.nuwaapi.com/v1"
DEFAULT_LLM_API_KEY = "sk-UPWcTqXl2sU5VI6CmYUPOeHhUmSd9vSXhNrlXu9bFv2BKvZd"
DEFAULT_LLM_MODEL = "gpt-5-mini"


@dataclass
class LLMConfig:
    """Configuration for LLM API calls."""

    endpoint: str = DEFAULT_LLM_ENDPOINT
    api_key: str = DEFAULT_LLM_API_KEY
    model: str = DEFAULT_LLM_MODEL
    temperature: float = 0.2
    timeout_seconds: int = 60


@dataclass
class LLMCallResult:
    """Result wrapper for LLM call."""

    response_text: str
    raw_response: dict[str, Any]
    model: str


def build_chat_payload(prompt_text: str, config: LLMConfig) -> dict[str, Any]:
    """Build a generic chat-completions payload for LLM APIs."""
    return {
        "model": config.model,
        "temperature": config.temperature,
        "messages": [
            {
                "role": "system",
                "content": "You are an expert Java unit test generator.",
            },
            {
                "role": "user",
                "content": prompt_text,
            },
        ],
    }


def extract_response_text(raw_response: dict[str, Any]) -> str:
    """Extract assistant text from a chat-completions style response."""
    choices = raw_response.get("choices", [])
    if not choices:
        return ""

    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_val = item.get("text", "")
                if isinstance(text_val, str):
                    texts.append(text_val)
        return "\n".join(texts)
    return ""


def _create_openai_client(config: LLMConfig):
    """Create OpenAI SDK client with configured base URL and key."""
    from openai import OpenAI

    return OpenAI(
        api_key=config.api_key,
        base_url=config.endpoint,
        timeout=config.timeout_seconds,
    )


def call_llm_with_prompt(prompt_text: str, config: LLMConfig) -> LLMCallResult:
    """Call LLM endpoint with prompt and return parsed result."""

    payload = build_chat_payload(prompt_text, config)
    try:
        client = _create_openai_client(config)
        response_obj = client.chat.completions.create(**payload)
    except Exception as ex:  # pragma: no cover - exact SDK exceptions vary
        raise RuntimeError(f"LLM 请求失败: {ex}") from ex

    if hasattr(response_obj, "model_dump"):
        raw_response = response_obj.model_dump()
    elif isinstance(response_obj, dict):
        raw_response = response_obj
    else:
        raw_response = {"choices": []}

    response_text = extract_response_text(raw_response)
    return LLMCallResult(
        response_text=response_text,
        raw_response=raw_response,
        model=config.model,
    )


def get_default_llm_output_path(project_root: str, target_file: str) -> str:
    """Build deterministic output path for LLM-generated code."""
    prompt_dir = os.path.join(project_root, "tmp", "prompts")
    os.makedirs(prompt_dir, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(target_file))[0]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    file_name = f"{base_name}_llm_output_{timestamp}.txt"
    return os.path.join(prompt_dir, file_name)


def save_llm_output_text(output_text: str, output_path: str) -> str:
    """Persist LLM output text and return absolute output path."""
    abs_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as file_obj:
        file_obj.write(output_text)
    return abs_path
