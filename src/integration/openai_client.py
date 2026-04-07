#调用LLM API的实用程序函数和数据类，并获取LLM响应文本

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from typing import Any


DEFAULT_LLM_ENDPOINT = "https://api.nuwaapi.com/v1"
DEFAULT_LLM_API_KEY = "sk-UPWcTqXl2sU5VI6CmYUPOeHhUmSd9vSXhNrlXu9bFv2BKvZd"
DEFAULT_LLM_MODEL = "gpt-5-mini"
DEFAULT_SYSTEM_PROMPT = "You are an expert Java unit test generator."


@dataclass
class LLMConfig:

    endpoint: str = DEFAULT_LLM_ENDPOINT
    api_key: str = DEFAULT_LLM_API_KEY
    model: str = DEFAULT_LLM_MODEL
    temperature: float = 0.2
    timeout_seconds: int = 60


@dataclass
class LLMCallResult:
    # LLM调用结果的结构化表示，包括响应文本、原始响应数据和使用的模型名称。

    response_text: str
    raw_response: dict[str, Any]
    model: str


@dataclass
class LLMConversation:
    # Responses API 会话状态：上一轮响应ID + system 指令。
    previous_response_id: str | None = None
    system_prompt: str = DEFAULT_SYSTEM_PROMPT


def create_llm_conversation(system_prompt: str = DEFAULT_SYSTEM_PROMPT) -> LLMConversation:
    return LLMConversation(previous_response_id=None, system_prompt=system_prompt)


def build_chat_payload(prompt_text: str, config: LLMConfig) -> dict[str, Any]:
    # 构建 Responses API 请求负载，保持函数名不变以兼容现有调用。
    return {
        "model": config.model,
        "temperature": config.temperature,
        "instructions": DEFAULT_SYSTEM_PROMPT,
        "input": prompt_text,
    }


def extract_response_text(raw_response: dict[str, Any]) -> str:
    # 从 Responses 原始响应中提取助手文本。
    output_text = raw_response.get("output_text")
    if isinstance(output_text, str) and output_text:
        return output_text

    output = raw_response.get("output", [])
    if isinstance(output, list):
        texts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content", [])
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") in {"output_text", "text"}:
                    text_val = part.get("text", "")
                    if isinstance(text_val, str) and text_val:
                        texts.append(text_val)
        if texts:
            return "\n".join(texts)
    return ""


def _create_openai_client(config: LLMConfig):
    # 创建并返回一个配置好的OpenAI客户端实例，用于后续的API调用。
    from openai import OpenAI

    return OpenAI(
        api_key=config.api_key,
        base_url=config.endpoint,
        timeout=config.timeout_seconds,
    )


def _normalize_raw_response(response_obj: Any) -> dict[str, Any]:
    if hasattr(response_obj, "model_dump"):
        return response_obj.model_dump()
    if isinstance(response_obj, dict):
        return response_obj
    return {"output": []}


def call_llm_with_prompt(prompt_text: str, config: LLMConfig) -> LLMCallResult:
    # 单轮调用：使用 Responses API 直接生成结果。

    payload = build_chat_payload(prompt_text, config)
    try:
        client = _create_openai_client(config)
        response_obj = client.responses.create(**payload)
    except Exception as ex:  # pragma: no cover - exact SDK exceptions vary
        raise RuntimeError(f"LLM 请求失败: {ex}") from ex

    raw_response = _normalize_raw_response(response_obj)

    response_text = extract_response_text(raw_response)
    return LLMCallResult(
        response_text=response_text,
        raw_response=raw_response,
        model=config.model,
    )


def call_llm_with_conversation(
    prompt_text: str,
    config: LLMConfig,
    conversation: LLMConversation,
) -> LLMCallResult:
    # 会话式调用：通过 previous_response_id 将本轮请求串接到上轮响应。
    payload: dict[str, Any] = {
        "model": config.model,
        "temperature": config.temperature,
        "input": [{"role": "user", "content": prompt_text}],
    }
    if conversation.system_prompt:
        payload["instructions"] = conversation.system_prompt
    if conversation.previous_response_id:
        payload["previous_response_id"] = conversation.previous_response_id

    try:
        client = _create_openai_client(config)
        response_obj = client.responses.create(**payload)
    except Exception as ex:  # pragma: no cover - exact SDK exceptions vary
        raise RuntimeError(f"LLM 请求失败: {ex}") from ex

    raw_response = _normalize_raw_response(response_obj)
    response_text = extract_response_text(raw_response)
    response_id = raw_response.get("id")
    if isinstance(response_id, str) and response_id:
        conversation.previous_response_id = response_id

    return LLMCallResult(
        response_text=response_text,
        raw_response=raw_response,
        model=config.model,
    )


def get_default_llm_output_path(project_root: str, target_file: str) -> str:
    # 生成默认的LLM输出文件路径，位于项目的tmp/prompts目录下，文件名包含目标文件名和时间戳。
    prompt_dir = os.path.join(project_root, "tmp", "prompts")
    os.makedirs(prompt_dir, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(target_file))[0]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    file_name = f"{base_name}_llm_output_{timestamp}.txt"
    return os.path.join(prompt_dir, file_name)


def save_llm_output_text(output_text: str, output_path: str) -> str:
    # 将LLM输出文本保存到指定路径，确保目录存在，并返回保存的绝对路径。
    abs_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as file_obj:
        file_obj.write(output_text)
    return abs_path
