# 变异体生成提示构建模块

from __future__ import annotations

import json
import os
import re
from typing import Any

from ..runners.defects4j_runner import MutantInput
from .reward_context import append_reward_score_section
from .report_focus import extract_mutation_focus, load_defects4j_run_report

MUTATION_SYSTEM_PROMPT = "You are an expert Java source code mutation generator."


def _target_rel_path(prompt_result: Any) -> str:
    repo_root = prompt_result.source_info.repo_root
    target_file = prompt_result.source_info.target_file
    return os.path.relpath(target_file, repo_root)


def _base_prompt_prefix(prompt_result: Any) -> str:
    prompt_text = prompt_result.prompt.rstrip()
    prefix, separator, _ = prompt_text.rpartition("=== Task Instruction ===")
    if separator:
        return prefix.rstrip()
    return prompt_text


def build_mutation_initialization_prompt(
    prompt_result: Any,
    mutant_count: int = 5,
    reward_context: dict[str, Any] | None = None,
) -> str:
    """Build the first-round mutation prompt from the same analysis context as test generation."""
    lines = [_base_prompt_prefix(prompt_result)]
    lines.append("")
    lines.append("=== Task Instruction ===")
    lines.append("请以提升 mutation_loop Reward Score 为目标。")
    lines.append(f"为目标 Java 源文件生成 {mutant_count} 个变异体。")
    lines.append("要求输出 JSON 纯文本，不要代码块，不要解释。")
    lines.append("JSON 格式必须为：{\"mutants\":[{\"mutant_id\":\"m1\",\"target_rel_path\":\"...\",\"mutated_source\":\"...\"}]}")
    lines.append("每个 mutant 都必须是完整可编译的 Java 源文件，保留 package 和 public class 名称。")
    lines.append("优先生成语义不同、较难被测试杀死的变异体，避免只做重命名或空改动。")
    lines.append(f"target_rel_path 固定为 {_target_rel_path(prompt_result)}。")
    append_reward_score_section(lines, reward_context)
    return "\n".join(lines)


def build_mutation_feedback_prompt(
    prompt_result: Any,
    report_or_path: dict[str, Any] | str,
    mutant_count: int = 5,
    reward_context: dict[str, Any] | None = None,
) -> str:
    """Build a mutation replenishment prompt from the latest mutation-testing feedback."""
    report = load_defects4j_run_report(report_or_path)
    focus = extract_mutation_focus(report)

    lines = [_base_prompt_prefix(prompt_result)]
    lines.append("")
    lines.append("=== Mutation Focus ===")
    lines.append(f"mutation_score: {focus['mutation_score']}")
    lines.append(f"killed: {focus['killed']}")
    lines.append(f"survived: {focus['survived']}")
    lines.append(f"executed_mutants: {focus['executed_mutants']}/{focus['total_mutants']}")
    lines.append(f"error_count: {focus['error_count']}")
    if focus["surviving_cases_preview"]:
        lines.append("surviving_cases_preview:")
        for case in focus["surviving_cases_preview"]:
            lines.append(f"- {case['mutant_id']} | {case['target_rel_path']} | {case['status']}")
    lines.append("")
    append_reward_score_section(lines, reward_context)
    lines.append("=== Task Instruction ===")
    lines.append("请以提升 mutation_loop Reward Score 为目标。")
    lines.append(f"请补充新的、比上一轮更难杀死的 {mutant_count} 个变异体，并替换掉已存活的弱变异体。")
    lines.append("要求输出 JSON 纯文本，不要代码块，不要解释。")
    lines.append("JSON 格式必须为：{\"mutants\":[{\"mutant_id\":\"m1\",\"target_rel_path\":\"...\",\"mutated_source\":\"...\"}]}")
    lines.append("每个 mutant 都必须是完整可编译的 Java 源文件，保留 package 和 public class 名称。")
    lines.append(f"target_rel_path 固定为 {_target_rel_path(prompt_result)}。")
    return "\n".join(lines)


def build_mutation_prompt(
    prompt_result: Any,
    mutant_count: int = 5,
    report_or_path: dict[str, Any] | str | None = None,
    reward_context: dict[str, Any] | None = None,
) -> str:
    if report_or_path is None:
        return build_mutation_initialization_prompt(
            prompt_result,
            mutant_count=mutant_count,
            reward_context=reward_context,
        )
    return build_mutation_feedback_prompt(
        prompt_result,
        report_or_path,
        mutant_count=mutant_count,
        reward_context=reward_context,
    )


def _extract_json_text(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        raise ValueError("变异体生成输出为空")

    fenced_match = re.search(r"```(?:json)?\s*(.*?)```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fenced_match:
        candidate = fenced_match.group(1).strip()
        if candidate:
            return candidate

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return stripped[start : end + 1]

    if stripped.startswith("[") and stripped.endswith("]"):
        return stripped

    raise ValueError("无法从 LLM 输出中提取 JSON")


def parse_mutant_generation_output(
    response_text: str,
    prompt_result: Any,
    expected_count: int,
) -> list[MutantInput]:
    json_text = _extract_json_text(response_text)
    payload = json.loads(json_text)
    items = payload.get("mutants") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise ValueError("变异体输出必须包含 mutants 数组")

    default_target_rel_path = _target_rel_path(prompt_result)
    mutants: list[MutantInput] = []
    for idx, item in enumerate(items[:expected_count], start=1):
        if not isinstance(item, dict):
            continue

        mutant_id = str(item.get("mutant_id", f"m{idx}")).strip()
        target_rel_path = str(item.get("target_rel_path", default_target_rel_path)).strip() or default_target_rel_path
        mutated_source = item.get("mutated_source")
        if not isinstance(mutated_source, str) or not mutated_source.strip():
            continue

        mutants.append(
            MutantInput(
                mutant_id=mutant_id,
                target_rel_path=target_rel_path,
                mutated_source=mutated_source.strip(),
            )
        )

    return mutants
