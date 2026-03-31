"""Tests for structured prompt builder."""

from pathlib import Path

from src.prompting.structured_prompt import (
    PromptSourceInfo,
    StructuredPromptBuilder,
    build_structured_prompt,
    compose_round_prompt,
    get_default_prompt_output_path,
    get_default_prompt_json_output_path,
    save_prompt_json,
    save_prompt_text,
)


def test_prompt_source_info_is_extensible():
    """PromptSourceInfo should allow appending reusable metadata."""
    info = PromptSourceInfo(
        repo_root="/tmp/repo",
        target_file="/tmp/repo/A.java",
    )
    info.add_metadata("bug_id", "Cli-1b")
    info.add_metadata("model", "gpt")

    assert info.metadata["bug_id"] == "Cli-1b"
    assert info.metadata["model"] == "gpt"


def test_build_structured_prompt_with_test_data():
    """Structured prompt should include call chains and execution paths."""
    test_dir = Path(__file__).parent / "test_data"
    target_file = test_dir / "B.java"

    result = build_structured_prompt(
        repo_root=str(test_dir),
        target_file=str(target_file),
        depth=10,
        metadata={"dataset": "unit-test"},
    )

    assert len(result.target_methods) == 2
    assert "dataset: unit-test" in result.prompt
    assert "=== Call Chains ===" in result.prompt
    assert "=== Execution Paths ===" in result.prompt
    assert "testdata.B.bar(0)" in result.prompt


def test_structured_prompt_builder_direct_use():
    """Builder class should be reusable via stored source info."""
    test_dir = Path(__file__).parent / "test_data"
    target_file = test_dir / "ExecutionPathTest.java"

    source = PromptSourceInfo(
        repo_root=str(test_dir),
        target_file=str(target_file),
        analysis_depth=8,
    )
    source.add_metadata("scenario", "reusable-source-info")

    builder = StructuredPromptBuilder(source)
    result = builder.build()

    assert result.source_info.analysis_depth == 8
    assert result.source_info.metadata["scenario"] == "reusable-source-info"
    assert "target_method_count" in result.prompt
    assert "Task Instruction" in result.prompt


def test_structured_prompt_contains_target_code_section():
    """Prompt should include the target Java code section for LLM test generation."""
    test_dir = Path(__file__).parent / "test_data"
    target_file = test_dir / "B.java"

    result = build_structured_prompt(
        repo_root=str(test_dir),
        target_file=str(target_file),
        depth=6,
    )

    assert "=== Target Code ===" in result.prompt
    assert "```java" in result.prompt
    assert "class B" in result.prompt


def test_prompt_can_be_saved_under_project_prompt_dir(tmp_path):
    """Prompt helper should create tmp/prompts output path and persist prompt text."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    target_file = project_root / "Demo.java"
    target_file.write_text("public class Demo {}", encoding="utf-8")

    out_path = get_default_prompt_output_path(str(project_root), str(target_file))
    assert str(project_root / "tmp" / "prompts") in out_path

    saved_path = save_prompt_text("hello prompt", out_path)
    assert Path(saved_path).is_file()
    assert Path(saved_path).read_text(encoding="utf-8") == "hello prompt"


def test_prompt_payload_supports_feedback_rounds_and_json():
    """Structured result should support feedback rounds and JSON export."""
    test_dir = Path(__file__).parent / "test_data"
    target_file = test_dir / "B.java"

    result = build_structured_prompt(
        repo_root=str(test_dir),
        target_file=str(target_file),
        depth=6,
    )
    result.add_feedback_round(
        round_id=1,
        result_type="compile-error",
        summary="Missing import for Assert",
        details={"line": 18},
    )

    payload = result.to_payload()
    assert "feedback_rounds" in payload
    assert payload["feedback_rounds"][0]["result_type"] == "compile-error"

    json_text = result.to_json()
    assert "\"feedback_rounds\"" in json_text
    assert "compile-error" in json_text


def test_compose_round_prompt_for_coverage_boost():
    """Scenario composition should inject orchestration instructions."""
    test_dir = Path(__file__).parent / "test_data"
    target_file = test_dir / "B.java"
    result = build_structured_prompt(
        repo_root=str(test_dir),
        target_file=str(target_file),
        depth=6,
    )

    payload = compose_round_prompt(
        result,
        scenario="coverage-boost",
        extra_context={"goal_line_coverage": 0.9},
    )

    assert payload["orchestration"]["scenario"] == "coverage-boost"
    assert payload["orchestration"]["extra_context"]["goal_line_coverage"] == 0.9
    assert any("improve uncovered" in text for text in payload["orchestration"]["instructions"])


def test_prompt_json_path_and_save(tmp_path):
    """JSON helper should create tmp/prompts output path and persist payload."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    target_file = project_root / "Demo.java"
    target_file.write_text("public class Demo {}", encoding="utf-8")

    out_path = get_default_prompt_json_output_path(str(project_root), str(target_file))
    assert str(project_root / "tmp" / "prompts") in out_path

    saved_path = save_prompt_json({"ok": True}, out_path)
    assert Path(saved_path).is_file()
    assert '"ok": true' in Path(saved_path).read_text(encoding="utf-8")
