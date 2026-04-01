# 编译错误修复提示构建模块

from typing import Any

from .report_focus import extract_compile_error_focus, load_defects4j_run_report


def build_compile_error_prompt(
    prompt_result: Any,
    report_or_path: dict[str, Any] | str,
) -> str:
    # 构建针对编译错误修复的提示文本，包含目标代码和编译错误相关信息，指导生成可编译的测试代码。
    report = load_defects4j_run_report(report_or_path)
    focus = extract_compile_error_focus(report)

    lines: list[str] = []
    lines.append("=== Compile Error Repair Prompt ===")
    lines.append("目标：修复生成测试代码的编译错误，并保持测试意图不变。")
    lines.append("")
    lines.append("=== Target Code ===")
    lines.append("```java")
    lines.append(prompt_result.source_info.target_code.rstrip("\n"))
    lines.append("```")
    lines.append("")
    lines.append("=== Compile Error Focus ===")
    lines.append(f"status: {focus['status']}")
    lines.append(f"coverage_exit_code: {focus['coverage_exit_code']}")
    if focus["compile_error_lines"]:
        for line in focus["compile_error_lines"]:
            lines.append(f"- {line}")
    else:
        lines.append("- (no compile error lines captured)")
    lines.append("")
    lines.append("=== Instruction ===")
    lines.append("请输出可编译的完整 Java 测试类代码，仅输出代码，不要解释。")
    return "\n".join(lines)
