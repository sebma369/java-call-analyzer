"""Initialization prompt builder."""

from typing import Any


def build_initialization_prompt(prompt_result: Any) -> str:
    """Return first-round initialization prompt."""
    return prompt_result.prompt
