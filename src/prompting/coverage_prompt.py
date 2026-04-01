# 覆盖率提升提示构建模块

from typing import Any

from .report_focus import extract_coverage_focus, load_defects4j_run_report


def build_coverage_improve_prompt(
    prompt_result: Any,
    report_or_path: dict[str, Any] | str,
) -> str:
    # 构建针对覆盖率提升的提示文本
    report = load_defects4j_run_report(report_or_path)
    focus = extract_coverage_focus(report)

    lines: list[str] = []
    lines.append("=== Coverage Improvement Prompt ===")
    lines.append("目标：在保持可运行性的前提下，提高目标类行覆盖率和分支覆盖率。")
    lines.append("")
    lines.append("=== Target Code ===")
    lines.append("```java")
    lines.append(prompt_result.source_info.target_code.rstrip("\n"))
    lines.append("```")
    lines.append("")
    lines.append("=== Coverage Focus ===")
    lines.append(f"line_coverage_percent: {focus['line_coverage_percent']}")
    lines.append(f"condition_coverage_percent: {focus['condition_coverage_percent']}")
    lines.append(
        f"covered_lines: {focus['covered_lines']}/{focus['total_executable_lines']}"
    )
    lines.append(
        f"covered_conditions: {focus['covered_conditions']}/{focus['total_conditions']}"
    )
    lines.append("uncovered_lines_preview:")
    if focus["uncovered_lines_preview"]:
        lines.append("- " + ", ".join(str(x) for x in focus["uncovered_lines_preview"]))
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("=== Instruction ===")
    lines.append("请输出完整 Java 测试类代码，优先覆盖未覆盖行与分支，仅输出代码，不要解释。")
    return "\n".join(lines)
