"""Iterative orchestration for execution-feedback based generation."""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from typing import Any

from ..integration.openai_client import (
    LLMConfig,
    call_llm_with_conversation,
    create_llm_conversation,
)
from ..prompting.report_focus import load_defects4j_run_report
from ..prompting.structured_prompt import (
    build_structured_prompt,
    build_targeted_prompt,
)
from ..runners.defects4j_runner import Defects4jRunner, get_testgen_root


@dataclass
class IterativeRoundRecord:
    round_id: int
    prompt_type: str
    prompt_path: str
    llm_output_path: str
    run_report_path: str
    status: str
    coverage_summary: dict[str, Any] | None


@dataclass
class IterativeRunResult:
    final_status: str
    rounds_executed: int
    rounds: list[IterativeRoundRecord]
    summary_path: str
    run_root: str


def _create_run_root() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base_dir = os.path.join(get_testgen_root(), "tmp", "iterative_runs")
    os.makedirs(base_dir, exist_ok=True)

    run_root = os.path.join(base_dir, f"run_{timestamp}")
    suffix = 1
    while os.path.exists(run_root):
        suffix += 1
        run_root = os.path.join(base_dir, f"run_{timestamp}_{suffix}")
    os.makedirs(run_root, exist_ok=True)
    return run_root


def _save_text(path: str, content: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file_obj:
        file_obj.write(content)
    return path


def _select_next_prompt_type(status: str) -> str:
    if status == "coverage_command_failed":
        return "compile-error"
    if status == "test_execution_failed":
        return "runtime-error"
    return "coverage"


def _build_round_summary_payload(
    result: IterativeRunResult,
) -> dict[str, Any]:
    return {
        "final_status": result.final_status,
        "rounds_executed": result.rounds_executed,
        "run_root": result.run_root,
        "rounds": [
            {
                "round_id": item.round_id,
                "prompt_type": item.prompt_type,
                "prompt_path": item.prompt_path,
                "llm_output_path": item.llm_output_path,
                "run_report_path": item.run_report_path,
                "status": item.status,
                "coverage_summary": item.coverage_summary,
            }
            for item in result.rounds
        ],
    }


def run_iterative_feedback_loop(
    repo_root: str,
    target_file: str,
    max_rounds: int,
    depth: int = 10,
    llm_config: LLMConfig | None = None,
    defects4j_bin: str = "/usr/src/defects4j/framework/bin/defects4j",
    auto_clean: bool = True,
) -> IterativeRunResult:
    if max_rounds <= 0:
        raise ValueError("max_rounds must be positive")

    llm_config = llm_config or LLMConfig()
    conversation = create_llm_conversation()

    run_root = _create_run_root()

    prompt_result = build_structured_prompt(repo_root, target_file, depth=depth)
    runner = Defects4jRunner(defects4j_bin=defects4j_bin, auto_clean=auto_clean)

    round_records: list[IterativeRoundRecord] = []
    next_prompt_type = "initialization"

    for round_id in range(1, max_rounds + 1):
        prompt_text = build_targeted_prompt(
            prompt_result,
            next_prompt_type,
            report_or_path=(round_records[-1].run_report_path if round_records and next_prompt_type != "initialization" else None),
        )

        prompt_path = _save_text(
            os.path.join(run_root, f"round_{round_id:02d}_{next_prompt_type}_prompt.txt"),
            prompt_text,
        )

        llm_result = call_llm_with_conversation(prompt_text, llm_config, conversation)
        response_id = llm_result.raw_response.get("id") if isinstance(llm_result.raw_response, dict) else None
        print(f"[round {round_id}] llm response_id: {response_id}")
        llm_output_path = _save_text(
            os.path.join(run_root, f"round_{round_id:02d}_{next_prompt_type}_llm_output.txt"),
            llm_result.response_text,
        )

        run_result = runner.run(
            llm_output_text=llm_result.response_text,
            target_file=target_file,
            project_root=repo_root,
        )

        report = load_defects4j_run_report(run_result.report_json_path)
        coverage_summary = report.get("coverage_summary")
        status = str(report.get("status", run_result.status))

        prompt_result.add_feedback_round(
            round_id=round_id,
            result_type=next_prompt_type,
            summary=f"status={status}",
            details={
                "run_report_path": run_result.report_json_path,
                "coverage_summary": coverage_summary,
            },
        )

        round_records.append(
            IterativeRoundRecord(
                round_id=round_id,
                prompt_type=next_prompt_type,
                prompt_path=prompt_path,
                llm_output_path=llm_output_path,
                run_report_path=run_result.report_json_path,
                status=status,
                coverage_summary=coverage_summary,
            )
        )

        next_prompt_type = _select_next_prompt_type(status)

    final_status = round_records[-1].status if round_records else "unknown"
    result = IterativeRunResult(
        final_status=final_status,
        rounds_executed=len(round_records),
        rounds=round_records,
        summary_path=os.path.join(run_root, "rounds_summary.json"),
        run_root=run_root,
    )

    with open(result.summary_path, "w", encoding="utf-8") as file_obj:
        json.dump(_build_round_summary_payload(result), file_obj, ensure_ascii=False, indent=2)

    return result
