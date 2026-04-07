"""Tests for CLI dispatch."""

from pathlib import Path

from src import cli


def test_cli_iterative_mode_dispatches_to_controller(monkeypatch, tmp_path, capsys):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    target_file = repo_root / "Target.java"
    target_file.write_text("public class Target {}\n", encoding="utf-8")

    called = {}

    class FakeResult:
        rounds_executed = 2
        final_status = "success"
        run_root = str(repo_root / "tmp" / "iterative_runs" / "run_fake")
        summary_path = str(Path(run_root) / "rounds_summary.json")
        rounds = []

    def fake_run_iterative_feedback_loop(**kwargs):
        called.update(kwargs)
        return FakeResult()

    monkeypatch.setattr(cli, "run_iterative_feedback_loop", fake_run_iterative_feedback_loop)
    monkeypatch.setattr(cli.os.path, "isfile", lambda path: True)
    monkeypatch.setattr(cli.os.path, "isdir", lambda path: True)
    monkeypatch.setattr(cli, "build_structured_prompt", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "call_llm_with_prompt", lambda *args, **kwargs: None)

    argv = [
        "prog",
        str(target_file),
        "--repo",
        str(repo_root),
        "--mode",
        "llm-generate",
        "--iterative",
        "--max-rounds",
        "2",
    ]
    monkeypatch.setattr("sys.argv", argv)

    cli.main()

    captured = capsys.readouterr().out
    assert "开始多轮执行反馈循环" in captured
    assert called["repo_root"] == str(repo_root)
    assert called["target_file"] == str(target_file.resolve())
    assert called["max_rounds"] == 2
