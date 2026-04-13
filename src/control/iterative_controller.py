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
from ..prompting.mutation_prompt import (
    MUTATION_SYSTEM_PROMPT,
    build_mutation_prompt,
    parse_mutant_generation_output,
)
from ..prompting.report_focus import extract_mutation_focus, load_defects4j_run_report
from ..prompting.structured_prompt import (
    build_structured_prompt,
    build_targeted_prompt,
)
from ..runners.defects4j_runner import Defects4jRunner, MutantInput, get_testgen_root


@dataclass
class IterativeRoundRecord:
    round_id: int
    prompt_type: str
    prompt_path: str
    llm_output_path: str
    run_report_path: str
    status: str
    coverage_summary: dict[str, Any] | None
    reward_score: dict[str, Any]


@dataclass
class MutationGenerationRecord:
    generation_id: int
    source_round_id: int | None
    prompt_type: str
    prompt_path: str
    llm_output_path: str
    requested_mutant_count: int
    parsed_mutant_count: int
    fallback_used: bool
    mutation_score: float | None
    feedback_status: str | None
    reward_score: dict[str, Any] | None


@dataclass
class IterativeRunResult:
    final_status: str
    rounds_executed: int
    rounds: list[IterativeRoundRecord]
    mutation_generations: list[MutationGenerationRecord]
    summary_path: str
    run_root: str
    requested_mutant_count: int
    final_mutant_count: int


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


def _build_round_summary_payload(result: IterativeRunResult) -> dict[str, Any]:
    return {
        "final_status": result.final_status,
        "rounds_executed": result.rounds_executed,
        "run_root": result.run_root,
        "requested_mutant_count": result.requested_mutant_count,
        "final_mutant_count": result.final_mutant_count,
        "rounds": [
            {
                "round_id": item.round_id,
                "prompt_type": item.prompt_type,
                "prompt_path": item.prompt_path,
                "llm_output_path": item.llm_output_path,
                "run_report_path": item.run_report_path,
                "status": item.status,
                "coverage_summary": item.coverage_summary,
                "reward_score": item.reward_score,
            }
            for item in result.rounds
        ],
        "mutation_generations": [
            {
                "generation_id": item.generation_id,
                "source_round_id": item.source_round_id,
                "prompt_type": item.prompt_type,
                "prompt_path": item.prompt_path,
                "llm_output_path": item.llm_output_path,
                "requested_mutant_count": item.requested_mutant_count,
                "parsed_mutant_count": item.parsed_mutant_count,
                "fallback_used": item.fallback_used,
                "mutation_score": item.mutation_score,
                "feedback_status": item.feedback_status,
                "reward_score": item.reward_score,
            }
            for item in result.mutation_generations
        ],
    }


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coverage_quality(summary: dict[str, Any] | None) -> float | None:
    if not isinstance(summary, dict):
        return None
    line_cov = _safe_float(summary.get("line_coverage_percent"))
    cond_cov = _safe_float(summary.get("condition_coverage_percent"))
    if line_cov is None and cond_cov is None:
        return None
    if line_cov is None:
        return cond_cov
    if cond_cov is None:
        return line_cov
    return (line_cov + cond_cov) / 2.0


def _has_full_line_coverage(summary: dict[str, Any] | None) -> bool:
    if not isinstance(summary, dict):
        return False
    line_cov = _safe_float(summary.get("line_coverage_percent"))
    return line_cov is not None and line_cov >= 100.0


def _mutation_score_from_report(report: dict[str, Any] | None) -> float | None:
    if not isinstance(report, dict):
        return None
    mutation = report.get("mutation")
    if not isinstance(mutation, dict):
        return None
    return _safe_float(mutation.get("mutation_score"))


def _compute_test_loop_reward(
    status: str,
    report: dict[str, Any],
    prev_report: dict[str, Any] | None,
) -> dict[str, Any]:
    breakdown: dict[str, float] = {}

    if status == "success":
        breakdown["compile_run"] = 20.0
    elif status == "coverage_report_missing":
        breakdown["compile_run"] = 12.0
    elif status == "test_execution_failed":
        breakdown["compile_run"] = -10.0
    else:
        breakdown["compile_run"] = -18.0

    if prev_report is not None:
        prev_status = str(prev_report.get("status", "unknown"))
        success_states = {"success", "coverage_report_missing"}
        if prev_status in success_states and status not in success_states:
            breakdown["compile_run_regression"] = -8.0
        elif prev_status not in success_states and status in success_states:
            breakdown["compile_run_recovery"] = 8.0

    cur_cov_quality = _coverage_quality(report.get("coverage_summary"))
    prev_cov_quality = _coverage_quality(
        prev_report.get("coverage_summary") if isinstance(prev_report, dict) else None
    )
    if cur_cov_quality is not None and prev_cov_quality is not None:
        cov_delta = round(cur_cov_quality - prev_cov_quality, 2)
        if cov_delta > 0:
            breakdown["coverage_delta"] = round(min(20.0, cov_delta * 0.6), 2)
        elif cov_delta < 0:
            breakdown["coverage_delta"] = round(-min(20.0, abs(cov_delta) * 0.8), 2)
    elif cur_cov_quality is not None and prev_cov_quality is None:
        breakdown["coverage_baseline"] = 2.0

    cur_mut_score = _mutation_score_from_report(report)
    prev_mut_score = _mutation_score_from_report(prev_report)
    if cur_mut_score is not None and prev_mut_score is not None:
        mut_delta = round(cur_mut_score - prev_mut_score, 2)
        if mut_delta > 0:
            breakdown["mutation_delta"] = round(min(20.0, mut_delta * 0.5), 2)
        elif mut_delta < 0:
            breakdown["mutation_delta"] = round(-min(20.0, abs(mut_delta) * 0.7), 2)
    elif cur_mut_score is not None and prev_mut_score is None:
        breakdown["mutation_baseline"] = 2.0

    round_score = round(sum(breakdown.values()), 2)
    return {
        "round_score": round_score,
        "breakdown": breakdown,
    }


def _compute_mutation_loop_reward(
    report: dict[str, Any],
    survival_streaks: dict[str, int],
) -> tuple[dict[str, Any], dict[str, int]]:
    mutation = report.get("mutation") if isinstance(report, dict) else None
    if not isinstance(mutation, dict) or not mutation.get("executed"):
        return {
            "round_score": 0.0,
            "breakdown": {
                "no_mutation_execution": 0.0,
            },
        }, survival_streaks

    cases = mutation.get("cases")
    if not isinstance(cases, list):
        return {
            "round_score": 0.0,
            "breakdown": {
                "no_mutation_cases": 0.0,
            },
        }, survival_streaks

    new_streaks = dict(survival_streaks)
    score = 0.0
    survived_count = 0
    immediate_killed_count = 0
    delayed_killed_count = 0
    error_count = 0
    active_mutants: set[str] = set()

    for case in cases:
        if not isinstance(case, dict):
            continue
        mutant_id = str(case.get("mutant_id", "")).strip()
        if not mutant_id:
            continue
        active_mutants.add(mutant_id)

        status = str(case.get("status", "")).strip()
        prev_streak = int(new_streaks.get(mutant_id, 0))

        if status == "survived":
            current_streak = prev_streak + 1
            new_streaks[mutant_id] = current_streak
            survived_count += 1
            score += min(6.0, 1.5 * current_streak)
            continue

        if status == "killed":
            if prev_streak <= 0:
                immediate_killed_count += 1
                score -= 3.0
            else:
                delayed_killed_count += 1
                score -= 0.5
            new_streaks[mutant_id] = 0
            continue

        error_count += 1
        score -= 1.0
        new_streaks[mutant_id] = 0

    trimmed_streaks = {key: value for key, value in new_streaks.items() if key in active_mutants}
    breakdown = {
        "survived_bonus": round(score, 2),
        "survived_count": float(survived_count),
        "immediate_killed_penalty_count": float(immediate_killed_count),
        "delayed_killed_count": float(delayed_killed_count),
        "mutation_error_count": float(error_count),
    }
    return {
        "round_score": round(score, 2),
        "breakdown": breakdown,
    }, trimmed_streaks


def _generate_mutants(
    prompt_result: Any,
    llm_config: LLMConfig,
    mutation_conversation,
    run_root: str,
    generation_id: int,
    mutant_count: int,
    report_or_path: dict[str, Any] | str | None = None,
    fallback_mutants: list[MutantInput] | None = None,
    source_round_id: int | None = None,
    reward_context: dict[str, Any] | None = None,
) -> tuple[list[MutantInput], MutationGenerationRecord]:
    prompt_type = "initialization" if report_or_path is None else "replenishment"
    prompt_text = build_mutation_prompt(
        prompt_result,
        mutant_count=mutant_count,
        report_or_path=report_or_path,
        reward_context=reward_context,
    )
    prompt_path = _save_text(
        os.path.join(run_root, f"mutation_{generation_id:02d}_{prompt_type}_prompt.txt"),
        prompt_text,
    )

    llm_output_text = ""
    fallback_used = False
    parsed_mutants: list[MutantInput] = []
    mutation_score: float | None = None
    feedback_status: str | None = None

    try:
        llm_result = call_llm_with_conversation(prompt_text, llm_config, mutation_conversation)
        llm_output_text = llm_result.response_text
        response_id = llm_result.raw_response.get("id") if isinstance(llm_result.raw_response, dict) else None
        print(f"[mutation {generation_id}] llm response_id: {response_id}")
        parsed_mutants = parse_mutant_generation_output(llm_output_text, prompt_result, mutant_count)
    except Exception as ex:  # noqa: BLE001
        print(f"[mutation {generation_id}] 变异体生成失败: {ex}")

    llm_output_path = _save_text(
        os.path.join(run_root, f"mutation_{generation_id:02d}_{prompt_type}_llm_output.txt"),
        llm_output_text,
    )

    if not parsed_mutants and fallback_mutants:
        parsed_mutants = list(fallback_mutants[:mutant_count])
        fallback_used = True

    if isinstance(report_or_path, (dict, str)):
        report = load_defects4j_run_report(report_or_path)
        focus = extract_mutation_focus(report)
        mutation_score = focus["mutation_score"]
        feedback_status = focus["status"]

    record = MutationGenerationRecord(
        generation_id=generation_id,
        source_round_id=source_round_id,
        prompt_type=prompt_type,
        prompt_path=prompt_path,
        llm_output_path=llm_output_path,
        requested_mutant_count=mutant_count,
        parsed_mutant_count=len(parsed_mutants),
        fallback_used=fallback_used,
        mutation_score=mutation_score,
        feedback_status=feedback_status,
        reward_score=(reward_context.get("mutation_loop") if isinstance(reward_context, dict) else None),
    )
    return parsed_mutants, record


def run_iterative_feedback_loop(
    repo_root: str,
    target_file: str,
    max_rounds: int,
    depth: int = 10,
    llm_config: LLMConfig | None = None,
    defects4j_bin: str = "/usr/src/defects4j/framework/bin/defects4j",
    auto_clean: bool = True,
    mutants: list[MutantInput] | None = None,
    mutant_count: int = 5,
) -> IterativeRunResult:
    if max_rounds <= 0:
        raise ValueError("max_rounds must be positive")
    if mutant_count <= 0:
        raise ValueError("mutant_count must be positive")

    llm_config = llm_config or LLMConfig()
    test_conversation = create_llm_conversation()
    mutation_conversation = create_llm_conversation(MUTATION_SYSTEM_PROMPT)

    run_root = _create_run_root()

    prompt_result = build_structured_prompt(repo_root, target_file, depth=depth)
    runner = Defects4jRunner(defects4j_bin=defects4j_bin, auto_clean=auto_clean)

    round_records: list[IterativeRoundRecord] = []
    mutation_generations: list[MutationGenerationRecord] = []
    next_prompt_type = "initialization"
    previous_report: dict[str, Any] | None = None
    test_cumulative_score = 0.0
    mutation_cumulative_score = 0.0
    mutation_survival_streaks: dict[str, int] = {}

    current_mutants, initial_mutation_record = _generate_mutants(
        prompt_result=prompt_result,
        llm_config=llm_config,
        mutation_conversation=mutation_conversation,
        run_root=run_root,
        generation_id=1,
        mutant_count=mutant_count,
        report_or_path=None,
        fallback_mutants=mutants,
        source_round_id=None,
        reward_context=None,
    )
    mutation_generations.append(initial_mutation_record)

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

        llm_result = call_llm_with_conversation(prompt_text, llm_config, test_conversation)
        response_id = llm_result.raw_response.get("id") if isinstance(llm_result.raw_response, dict) else None
        print(f"[round {round_id}] llm response_id: {response_id}")
        llm_output_path = _save_text(
            os.path.join(run_root, f"round_{round_id:02d}_{next_prompt_type}_llm_output.txt"),
            llm_result.response_text,
        )

        run_kwargs = {
            "llm_output_text": llm_result.response_text,
            "target_file": target_file,
            "project_root": repo_root,
        }
        if current_mutants:
            run_kwargs["mutants"] = current_mutants
        run_result = runner.run(**run_kwargs)

        report = load_defects4j_run_report(run_result.report_json_path)
        coverage_summary = report.get("coverage_summary")
        status = str(report.get("status", run_result.status))

        test_loop_reward = _compute_test_loop_reward(status, report, previous_report)
        test_cumulative_score = round(test_cumulative_score + float(test_loop_reward["round_score"]), 2)
        test_loop_reward["cumulative_score"] = test_cumulative_score

        mutation_loop_reward, mutation_survival_streaks = _compute_mutation_loop_reward(
            report,
            mutation_survival_streaks,
        )
        mutation_cumulative_score = round(
            mutation_cumulative_score + float(mutation_loop_reward["round_score"]),
            2,
        )
        mutation_loop_reward["cumulative_score"] = mutation_cumulative_score

        reward_score = {
            "test_loop": test_loop_reward,
            "mutation_loop": mutation_loop_reward,
        }

        prompt_result.add_feedback_round(
            round_id=round_id,
            result_type=next_prompt_type,
            summary=f"status={status}",
            details={
                "run_report_path": run_result.report_json_path,
                "coverage_summary": coverage_summary,
                "mutation_summary": report.get("mutation"),
                "reward_score": reward_score,
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
                reward_score=reward_score,
            )
        )

        previous_report = report

        # 收敛提前停止：行覆盖率达到 100% 即结束外层测试循环。
        if _has_full_line_coverage(coverage_summary):
            break

        next_prompt_type = _select_next_prompt_type(status)

        if status == "success":
            current_mutants, mutation_record = _generate_mutants(
                prompt_result=prompt_result,
                llm_config=llm_config,
                mutation_conversation=mutation_conversation,
                run_root=run_root,
                generation_id=len(mutation_generations) + 1,
                mutant_count=mutant_count,
                report_or_path=run_result.report_json_path,
                fallback_mutants=current_mutants,
                source_round_id=round_id,
                reward_context=reward_score,
            )
            mutation_generations.append(mutation_record)

    final_status = round_records[-1].status if round_records else "unknown"
    result = IterativeRunResult(
        final_status=final_status,
        rounds_executed=len(round_records),
        rounds=round_records,
        mutation_generations=mutation_generations,
        summary_path=os.path.join(run_root, "rounds_summary.json"),
        run_root=run_root,
        requested_mutant_count=mutant_count,
        final_mutant_count=len(current_mutants),
    )

    with open(result.summary_path, "w", encoding="utf-8") as file_obj:
        json.dump(_build_round_summary_payload(result), file_obj, ensure_ascii=False, indent=2)

    return result
