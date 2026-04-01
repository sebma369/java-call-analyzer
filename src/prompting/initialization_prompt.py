# 初始化提示构建模块

from typing import Any


def build_initialization_prompt(prompt_result: Any) -> str:
    # 返回第一轮初始化提示文本。
    return prompt_result.prompt
