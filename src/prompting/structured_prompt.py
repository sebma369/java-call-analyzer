"""Build structured prompts from static analysis results."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from typing import Any

from ..analysis.call_chain import build_call_chains
from ..analysis.execution_paths import analyze_execution_paths
from ..analysis.java_parser import collect_methods_and_calls, collect_target_methods


@dataclass
class PromptSourceInfo:
    """Stores prompt source metadata for reuse and later extension."""

    repo_root: str
    target_file: str
    language: str = "Java"
    analysis_depth: int = 10
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    target_code: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_metadata(self, key: str, value: Any) -> None:
        """Add or update custom metadata for future reuse."""
        self.metadata[key] = value


@dataclass
class PromptBuildResult:
    """Structured prompt output and intermediate data."""

    prompt: str
    source_info: PromptSourceInfo
    target_methods: list[str]
    up_chains: list[tuple[str, list[str]]]
    down_chains: list[tuple[str, list[str]]]
    execution_paths: dict[str, list[list[str]]]
    feedback_rounds: list[dict[str, Any]] = field(default_factory=list)

    def add_feedback_round(
        self,
        round_id: int,
        result_type: str,
        summary: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Append one feedback round for iterative regeneration."""
        self.feedback_rounds.append(
            {
                "round_id": round_id,
                "result_type": result_type,
                "summary": summary,
                "details": details or {},
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def to_payload(
        self,
        include_target_code: bool = True,
        include_call_chains: bool = True,
        include_execution_paths: bool = True,
        include_feedback_rounds: bool = True,
    ) -> dict[str, Any]:
        """Export a machine-friendly payload for programmatic prompt assembly."""
        payload: dict[str, Any] = {
            "source": {
                "language": self.source_info.language,
                "repo_root": self.source_info.repo_root,
                "target_file": self.source_info.target_file,
                "analysis_depth": self.source_info.analysis_depth,
                "generated_at": self.source_info.generated_at,
                "metadata": dict(self.source_info.metadata),
            },
            "analysis_summary": {
                "target_method_count": len(self.target_methods),
                "up_chain_count": len(self.up_chains),
                "down_chain_count": len(self.down_chains),
                "execution_path_method_count": len(self.execution_paths),
            },
            "target_methods": list(self.target_methods),
        }

        if include_target_code:
            payload["target_code"] = {
                "file": self.source_info.target_file,
                "language": "java",
                "content": self.source_info.target_code,
            }

        if include_call_chains:
            payload["call_chains"] = {
                "upward": [
                    {"method": method, "path": list(path)}
                    for method, path in self.up_chains
                ],
                "downward": [
                    {"method": method, "path": list(path)}
                    for method, path in self.down_chains
                ],
            }

        if include_execution_paths:
            payload["execution_paths"] = {
                method: [list(path) for path in paths]
                for method, paths in self.execution_paths.items()
            }

        if include_feedback_rounds:
            payload["feedback_rounds"] = list(self.feedback_rounds)

        return payload

    def to_json(
        self,
        include_target_code: bool = True,
        include_call_chains: bool = True,
        include_execution_paths: bool = True,
        include_feedback_rounds: bool = True,
    ) -> str:
        """Serialize machine-friendly payload as JSON string."""
        payload = self.to_payload(
            include_target_code=include_target_code,
            include_call_chains=include_call_chains,
            include_execution_paths=include_execution_paths,
            include_feedback_rounds=include_feedback_rounds,
        )
        return json.dumps(payload, ensure_ascii=False, indent=2)


def read_target_code(target_file: str) -> str:
    """Read target Java code for prompt grounding."""
    with open(target_file, "r", encoding="utf-8", errors="ignore") as file_obj:
        return file_obj.read()


def get_default_prompt_output_path(project_root: str, target_file: str) -> str:
    """Build a deterministic output path under <project_root>/tmp/prompts/."""
    prompt_dir = os.path.join(project_root, "tmp", "prompts")
    os.makedirs(prompt_dir, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(target_file))[0]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    file_name = f"{base_name}_structured_prompt_{timestamp}.txt"
    return os.path.join(prompt_dir, file_name)


def get_default_prompt_json_output_path(project_root: str, target_file: str) -> str:
    """Build a deterministic JSON output path under <project_root>/tmp/prompts/."""
    prompt_dir = os.path.join(project_root, "tmp", "prompts")
    os.makedirs(prompt_dir, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(target_file))[0]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    file_name = f"{base_name}_structured_prompt_{timestamp}.json"
    return os.path.join(prompt_dir, file_name)


def save_prompt_text(prompt_text: str, output_path: str) -> str:
    """Persist prompt text and return the absolute output path."""
    abs_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as file_obj:
        file_obj.write(prompt_text)
    return abs_path


def save_prompt_json(payload: dict[str, Any], output_path: str) -> str:
    """Persist prompt payload as JSON and return the absolute output path."""
    abs_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as file_obj:
        json.dump(payload, file_obj, ensure_ascii=False, indent=2)
    return abs_path


def compose_round_prompt(
    prompt_result: PromptBuildResult,
    scenario: str,
    extra_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose scenario-specific payload for iterative test generation."""
    scenario = scenario.strip().lower()
    extra_context = extra_context or {}

    selector = {
        "include_target_code": True,
        "include_call_chains": True,
        "include_execution_paths": True,
        "include_feedback_rounds": True,
    }
    instructions: list[str] = [
        "Generate JUnit test code for the target class.",
        "Return compilable Java code only.",
    ]

    if scenario == "initial-generation":
        instructions.append("Prioritize broad branch coverage for all target methods.")
    elif scenario == "compile-fix":
        instructions.append("Fix compilation issues from the latest feedback while keeping test intent unchanged.")
    elif scenario == "test-failure-fix":
        instructions.append("Adjust assertions and test setup based on latest failing test feedback.")
    elif scenario == "coverage-boost":
        instructions.append("Add or refine tests to improve uncovered lines and branches.")
    else:
        instructions.append("Adapt tests based on feedback context and maximize useful coverage.")

    payload = prompt_result.to_payload(**selector)
    payload["orchestration"] = {
        "scenario": scenario,
        "instructions": instructions,
        "extra_context": extra_context,
    }
    return payload


class StructuredPromptBuilder:
    """Builds structured prompts from call-chain and execution-path outputs."""

    def __init__(self, source_info: PromptSourceInfo):
        self.source_info = source_info

    def build(self) -> PromptBuildResult:
        """Run analyses and build a structured prompt."""
        method_defs, callers, callees = collect_methods_and_calls(self.source_info.repo_root)
        target_methods = collect_target_methods(self.source_info.target_file)
        if not self.source_info.target_code:
            self.source_info.target_code = read_target_code(self.source_info.target_file)
        up_chains, down_chains = build_call_chains(
            target_methods,
            callers,
            callees,
            max_depth=self.source_info.analysis_depth,
        )
        execution_paths = analyze_execution_paths(self.source_info.target_file)

        prompt = self._format_prompt(target_methods, up_chains, down_chains, execution_paths)
        return PromptBuildResult(
            prompt=prompt,
            source_info=self.source_info,
            target_methods=target_methods,
            up_chains=up_chains,
            down_chains=down_chains,
            execution_paths=execution_paths,
        )

    def _format_prompt(
        self,
        target_methods: list[str],
        up_chains: list[tuple[str, list[str]]],
        down_chains: list[tuple[str, list[str]]],
        execution_paths: dict[str, list[list[str]]],
    ) -> str:
        """Create a deterministic, structured prompt text."""
        lines: list[str] = []

        lines.append("=== Prompt Source ===")
        lines.append(f"language: {self.source_info.language}")
        lines.append(f"repo_root: {self.source_info.repo_root}")
        lines.append(f"target_file: {self.source_info.target_file}")
        lines.append(f"analysis_depth: {self.source_info.analysis_depth}")
        lines.append(f"generated_at: {self.source_info.generated_at}")
        if self.source_info.metadata:
            lines.append("metadata:")
            for key in sorted(self.source_info.metadata):
                lines.append(f"  {key}: {self.source_info.metadata[key]}")
        lines.append("")

        lines.append("=== Target Code ===")
        lines.append(f"file: {self.source_info.target_file}")
        lines.append("```java")
        lines.append(self.source_info.target_code.rstrip("\n"))
        lines.append("```")
        lines.append("")

        lines.append("=== Analysis Summary ===")
        lines.append(f"target_method_count: {len(target_methods)}")
        lines.append(f"up_chain_count: {len(up_chains)}")
        lines.append(f"down_chain_count: {len(down_chains)}")
        lines.append(f"execution_path_method_count: {len(execution_paths)}")
        lines.append("")

        lines.append("=== Target Methods ===")
        for method in target_methods:
            lines.append(f"- {method}")
        if not target_methods:
            lines.append("- (none)")
        lines.append("")

        lines.append("=== Call Chains ===")
        for method in target_methods:
            lines.append(f"method: {method}")

            method_up = [chain for m, chain in up_chains if m == method]
            lines.append("  upward:")
            if method_up:
                for idx, chain in enumerate(method_up, 1):
                    lines.append(f"    {idx}. {' -> '.join(chain)}")
            else:
                lines.append("    1. (none)")

            method_down = [chain for m, chain in down_chains if m == method]
            lines.append("  downward:")
            if method_down:
                for idx, chain in enumerate(method_down, 1):
                    lines.append(f"    {idx}. {' -> '.join(chain)}")
            else:
                lines.append("    1. (none)")
        lines.append("")

        lines.append("=== Execution Paths ===")
        for method in target_methods:
            method_paths = execution_paths.get(method, [])
            lines.append(f"method: {method}")
            if method_paths:
                for idx, path in enumerate(method_paths, 1):
                    lines.append(f"  {idx}. {' -> '.join(path)}")
            else:
                lines.append("  1. (none)")
        lines.append("")

        lines.append("=== Task Instruction ===")
        lines.append("Generate JUnit test code for the target Java class using the target code and analysis context above.")
        lines.append("Use call chains to cover interaction behavior and execution paths to cover branches and edge cases.")
        lines.append("Return compilable Java test code only.")

        return "\n".join(lines)


def build_structured_prompt(
    repo_root: str,
    target_file: str,
    depth: int = 10,
    metadata: dict[str, Any] | None = None,
) -> PromptBuildResult:
    """Convenience helper to build a prompt in one call."""
    source_info = PromptSourceInfo(
        repo_root=repo_root,
        target_file=target_file,
        analysis_depth=depth,
        target_code=read_target_code(target_file),
    )
    if metadata:
        for key, value in metadata.items():
            source_info.add_metadata(key, value)

    builder = StructuredPromptBuilder(source_info)
    return builder.build()
