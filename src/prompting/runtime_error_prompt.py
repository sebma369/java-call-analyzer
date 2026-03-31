"""Runtime-error repair prompt builder."""

from typing import Any

from .report_focus import extract_runtime_error_focus, load_defects4j_run_report


def build_runtime_error_prompt(
    prompt_result: Any,
    report_or_path: dict[str, Any] | str,
) -> str:
    """Build prompt targeted at runtime-failure repair."""
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
    lines.append("=== Instruction ===")
    lines.append("请输出可执行通过的完整 Java 测试类代码，仅输出代码，不要解释。")
    return "\n".join(lines)
