# 报告分析模块，提取编译错误、运行时错误和覆盖率相关的关键信息，构建针对性的提示文本。

import json
import re
from typing import Any


def load_defects4j_run_report(report_or_path: dict[str, Any] | str) -> dict[str, Any]:
    """Load Defects4J run report from dict object or JSON file path."""
    if isinstance(report_or_path, dict):
        return report_or_path

    with open(report_or_path, "r", encoding="utf-8", errors="ignore") as file_obj:
        return json.load(file_obj)


def extract_compile_error_focus(report: dict[str, Any]) -> dict[str, Any]:
    """Extract concise compile-stage error signals from Defects4J report."""
    stderr_text = str(report.get("stderr", ""))
    stdout_text = str(report.get("stdout", ""))
    merged = "\n".join([stdout_text, stderr_text])

    lines = merged.splitlines()
    key_lines = [
        line.strip()
        for line in lines
        if ("compile" in line.lower())
        or ("error" in line.lower())
        or ("cannot find symbol" in line.lower())
    ]

    return {
        "status": report.get("status", "unknown"),
        "coverage_exit_code": report.get("coverage_exit_code"),
        "compile_error_lines": key_lines[:40],
    }


def extract_runtime_error_focus(report: dict[str, Any]) -> dict[str, Any]:
    """Extract concise runtime failure signals from Defects4J report."""
    failing_text = str(report.get("failing_tests", "")).strip()
    lines = [line for line in failing_text.splitlines() if line.strip()]
    headline = lines[0] if lines else ""

    exception_match = re.search(r"([A-Za-z0-9_$.]+(?:Exception|Error))", failing_text)
    exception_name = exception_match.group(1) if exception_match else ""

    stack_top = [line for line in lines if line.startswith("\tat ")][:20]
    return {
        "status": report.get("status", "unknown"),
        "failed_test_headline": headline,
        "exception": exception_name,
        "stack_top": stack_top,
    }


def extract_coverage_focus(report: dict[str, Any]) -> dict[str, Any]:
    """Extract concise coverage summary from Defects4J report."""
    summary = report.get("coverage_summary") or {}
    uncovered_lines = summary.get("uncovered_lines", [])

    return {
        "status": report.get("status", "unknown"),
        "line_coverage_percent": summary.get("line_coverage_percent"),
        "condition_coverage_percent": summary.get("condition_coverage_percent"),
        "covered_lines": summary.get("covered_lines"),
        "total_executable_lines": summary.get("total_executable_lines"),
        "covered_conditions": summary.get("covered_conditions"),
        "total_conditions": summary.get("total_conditions"),
        "uncovered_lines": uncovered_lines,
        "uncovered_lines_preview": uncovered_lines[:40],
    }