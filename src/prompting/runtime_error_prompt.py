# 运行时错误修复提示构建模块

from typing import Any

from .reward_context import append_reward_score_section, get_latest_reward_context
from .report_focus import extract_runtime_error_focus, load_defects4j_run_report


def build_runtime_error_prompt(
    prompt_result: Any,
    report_or_path: dict[str, Any] | str,
) -> str:
    # 构建针对运行时错误修复的提示文本
    report = load_defects4j_run_report(report_or_path)
    focus = extract_runtime_error_focus(report)

    lines: list[str] = []
    lines.append("=== Runtime Error Repair Prompt ===")
    lines.append("目标：修复运行时失败，使生成测试可以通过执行。")
    lines.append("")
    lines.append("=== Target Code ===")
    lines.append("```java")
    lines.append(prompt_result.source_info.target_code.rstrip("\n"))
    lines.append("```")
    lines.append("")
    lines.append("=== Runtime Error Focus ===")
    lines.append(f"status: {focus['status']}")
    lines.append(f"failed_test_headline: {focus['failed_test_headline']}")
    lines.append(f"exception: {focus['exception']}")
    if focus["stack_top"]:
        lines.append("stack_top:")
        for line in focus["stack_top"]:
            lines.append(f"- {line}")
    lines.append("")
    append_reward_score_section(lines, get_latest_reward_context(prompt_result))
    lines.append("=== Instruction ===")
    lines.append("请优先提升 Reward Score，避免导致编译/运行能力倒退。")
    lines.append("请输出可执行通过的完整 Java 测试类代码，仅输出代码，不要解释。")
    return "\n".join(lines)
