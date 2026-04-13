# 奖励分数上下文工具

from typing import Any


def get_latest_reward_context(prompt_result: Any) -> dict[str, Any] | None:
    """Get the latest reward context from feedback rounds."""
    rounds = getattr(prompt_result, "feedback_rounds", [])
    for item in reversed(rounds):
        details = item.get("details", {}) if isinstance(item, dict) else {}
        reward = details.get("reward_score") if isinstance(details, dict) else None
        if isinstance(reward, dict):
            return reward
    return None


def append_reward_score_section(lines: list[str], reward_context: dict[str, Any] | None) -> None:
    """Append a concise reward-score section for prompt guidance."""
    if not reward_context:
        return

    test_loop = reward_context.get("test_loop") if isinstance(reward_context, dict) else None
    mutation_loop = reward_context.get("mutation_loop") if isinstance(reward_context, dict) else None

    lines.append("=== Reward Score ===")

    if isinstance(test_loop, dict):
        lines.append("test_loop:")
        lines.append(f"- round_score: {test_loop.get('round_score')}")
        lines.append(f"- cumulative_score: {test_loop.get('cumulative_score')}")
        lines.append("- composition:")
        lines.append("  - compile_run: success +20, coverage_report_missing +12, test_execution_failed -10, other failure -18")
        lines.append("  - compile_run_transition: failure->success +8, success->failure -8")
        lines.append("  - coverage_delta: coverage improvement adds up to +20, coverage regression subtracts up to -20")
        lines.append("  - mutation_delta: mutation_score improvement adds up to +20, mutation_score regression subtracts up to -20")
        breakdown = test_loop.get("breakdown")
        if isinstance(breakdown, dict) and breakdown:
            lines.append("- breakdown_now:")
            for key, value in breakdown.items():
                lines.append(f"  - {key}: {value}")

    if isinstance(mutation_loop, dict):
        lines.append("mutation_loop:")
        lines.append(f"- round_score: {mutation_loop.get('round_score')}")
        lines.append(f"- cumulative_score: {mutation_loop.get('cumulative_score')}")
        lines.append("- composition:")
        lines.append("  - survived_bonus: each survived mutant gives +1.5 per consecutive survival round, capped at +6")
        lines.append("  - immediate_killed_penalty: killed without prior survival streak gives -3")
        lines.append("  - delayed_killed_penalty: killed after prior survival gives -0.5")
        lines.append("  - error_penalty: mutation error gives -1")
        breakdown = mutation_loop.get("breakdown")
        if isinstance(breakdown, dict) and breakdown:
            lines.append("- breakdown_now:")
            for key, value in breakdown.items():
                lines.append(f"  - {key}: {value}")

    lines.append("")
