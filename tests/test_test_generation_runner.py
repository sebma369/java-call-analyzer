"""Tests for generated test extraction and execution helpers."""

import textwrap
from pathlib import Path

from src.runners.defects4j_runner import (
    CommandResult,
    Defects4jRunner,
    MutantInput,
    cleanup_generated_run,
    ensure_package_declaration,
    extract_java_code_block,
    extract_package_name,
    extract_public_class_name,
    extract_test_method_names,
    resolve_test_file_path,
    snapshot_file_contents,
    write_generated_test_file,
)


def test_extract_java_code_block_prefers_fenced_java():
    text = """
hello
```java
package a;
public class T {}
```
bye
"""
    code = extract_java_code_block(text)
    assert "public class T" in code


def test_extract_package_class_and_methods():
    code = """
package x.y;
public class DemoTest {
    @Test
    public void testA() {}
    @Test public void testB() {}
}
"""
    assert extract_package_name(code) == "x.y"
    assert extract_public_class_name(code) == "DemoTest"
    assert extract_test_method_names(code) == ["testA", "testB"]


def test_ensure_package_declaration_when_missing():
    code = "public class DemoTest {}"
    updated = ensure_package_declaration(code, "org.example")
    assert updated.startswith("package org.example;")


def test_write_generated_test_file(tmp_path):
    project_root = tmp_path / "proj"
    project_root.mkdir()
    code = """
package org.example;
public class DemoTest {}
"""

    path, pkg, cls, prev = write_generated_test_file(str(project_root), code)
    assert pkg == "org.example"
    assert cls == "DemoTest"
    assert prev is None
    assert Path(path).is_file()
    assert str(project_root / "src" / "test" / "org" / "example" / "DemoTest.java") == path


def test_resolve_test_file_path_without_package(tmp_path):
    project_root = tmp_path / "proj"
    project_root.mkdir()
    path = resolve_test_file_path(str(project_root), "", "DemoTest")
    assert path.endswith("src/test/DemoTest.java")


def test_cleanup_generated_run_restores_overwritten_file(tmp_path):
    project_root = tmp_path / "proj"
    target_dir = project_root / "src" / "test" / "org" / "example"
    target_dir.mkdir(parents=True)
    test_file = target_dir / "DemoTest.java"
    original = "package org.example;\npublic class DemoTest { int x = 1; }\n"
    test_file.write_text(original, encoding="utf-8")

    # Simulate run changes
    test_file.write_text("package org.example;\npublic class DemoTest {}\n", encoding="utf-8")
    generated_artifact = project_root / "coverage.xml"
    generated_artifact.write_text("tmp", encoding="utf-8")

    cleaned = cleanup_generated_run(
        project_root=str(project_root),
        artifact_state={"coverage.xml": False},
        test_file_path=str(test_file),
        previous_test_content=original,
    )

    assert str(test_file) in cleaned
    assert str(generated_artifact) in cleaned
    assert test_file.read_text(encoding="utf-8") == original
    assert not generated_artifact.exists()


def test_cleanup_generated_run_restores_mutable_file_content(tmp_path):
    project_root = tmp_path / "proj"
    project_root.mkdir()

    mutable = project_root / "defects4j.build.properties"
    mutable.write_text("a=1\n", encoding="utf-8")
    snapshot = snapshot_file_contents(str(project_root), ["defects4j.build.properties"])

    mutable.write_text("a=2\n", encoding="utf-8")
    fake_test = project_root / "src" / "test" / "DemoTest.java"
    fake_test.parent.mkdir(parents=True)
    fake_test.write_text("public class DemoTest {}\n", encoding="utf-8")

    cleanup_generated_run(
        project_root=str(project_root),
        artifact_state={},
        test_file_path=str(fake_test),
        previous_test_content=None,
        file_content_snapshot=snapshot,
    )

    assert mutable.read_text(encoding="utf-8") == "a=1\n"


def test_runner_executes_mutation_only_when_success(monkeypatch, tmp_path):
    project_root = tmp_path / "proj"
    target_dir = project_root / "src" / "java" / "org" / "example"
    target_dir.mkdir(parents=True)
    target_file = target_dir / "Target.java"
    original_target_source = "package org.example;\npublic class Target { public int add(int a, int b) { return a + b; } }\n"
    target_file.write_text(original_target_source, encoding="utf-8")

    llm_output = """
```java
package org.example;
public class TargetTest {
    public void testA() {}
}
```
"""

    mutants = [
        MutantInput(
            mutant_id="m1",
            target_rel_path="src/java/org/example/Target.java",
            mutated_source="package org.example;\npublic class Target { public int add(int a, int b) { return a - b; } }\n",
        ),
        MutantInput(
            mutant_id="m2",
            target_rel_path="src/java/org/example/Target.java",
            mutated_source="package org.example;\npublic class Target { public int add(int a, int b) { return a + b; } }\n",
        ),
    ]

    coverage_xml = textwrap.dedent(
        """
        <coverage>
          <packages>
            <package name="org.example">
              <classes>
                <class name="org.example.Target">
                  <methods/>
                  <lines>
                    <line number="1" hits="1"/>
                  </lines>
                </class>
              </classes>
            </package>
          </packages>
        </coverage>
        """
    ).strip()

    command_history: list[list[str]] = []
    coverage_call_count = {"count": 0}
    compile_call_count = {"count": 0}
    test_call_count = {"count": 0}

    def fake_write_suite_archive(run_dir, package_name, class_name, java_code):
        del package_name, class_name, java_code
        archive = Path(run_dir) / "generated_suite.tar.bz2"
        archive.write_text("archive", encoding="utf-8")
        return str(archive)

    def fake_run_command(command, cwd):
        command_history.append(command)
        if command[1] == "compile":
            compile_call_count["count"] += 1
            return CommandResult(command=command, exit_code=0, stdout="compile ok", stderr="")

        if command[1] == "coverage":
            coverage_call_count["count"] += 1
            if coverage_call_count["count"] == 1:
                (Path(cwd) / "coverage.xml").write_text(coverage_xml, encoding="utf-8")
            failing_path = Path(cwd) / "failing_tests"
            if coverage_call_count["count"] == 2:
                failing_path.write_text("--- org.example.TargetTest::testA\n", encoding="utf-8")
            elif failing_path.exists():
                failing_path.unlink()
            return CommandResult(command=command, exit_code=0, stdout="ok", stderr="")

        if command[1] == "test":
            test_call_count["count"] += 1
            assert "-t" in command
            t_arg = command[command.index("-t") + 1]
            assert t_arg == "org.example.TargetTest::testA"
            failing_path = Path(cwd) / "failing_tests"
            if test_call_count["count"] == 1:
                failing_path.write_text("--- org.example.TargetTest::testA\n", encoding="utf-8")
            elif failing_path.exists():
                failing_path.unlink()
            return CommandResult(command=command, exit_code=0, stdout="test ok", stderr="")

        raise AssertionError("unexpected command")

    monkeypatch.setattr("src.runners.defects4j_runner._write_suite_archive_for_generated_test", fake_write_suite_archive)
    monkeypatch.setattr("src.runners.defects4j_runner.run_command", fake_run_command)

    runner = Defects4jRunner(defects4j_bin="/tmp/defects4j", auto_clean=True, temp_root=str(tmp_path / "tmp"))
    result = runner.run(
        llm_output_text=llm_output,
        target_file=str(target_file),
        project_root=str(project_root),
        mutants=mutants,
    )

    assert result.status == "success"
    assert result.mutation_result is not None
    assert result.mutation_result.executed is True
    assert result.mutation_result.killed == 1
    assert result.mutation_result.survived == 1
    assert result.mutation_result.executed_mutants == 2
    assert coverage_call_count["count"] == 1
    assert compile_call_count["count"] == 2
    assert test_call_count["count"] == 2
    assert command_history[0][1] == "coverage"
    assert target_file.read_text(encoding="utf-8") == original_target_source


def test_runner_skips_mutation_when_not_success(monkeypatch, tmp_path):
    project_root = tmp_path / "proj"
    target_dir = project_root / "src" / "java" / "org" / "example"
    target_dir.mkdir(parents=True)
    target_file = target_dir / "Target.java"
    target_file.write_text("package org.example;\npublic class Target {}\n", encoding="utf-8")

    llm_output = "package org.example;\npublic class TargetTest {}\n"

    coverage_call_count = {"count": 0}
    compile_call_count = {"count": 0}

    def fake_write_suite_archive(run_dir, package_name, class_name, java_code):
        del package_name, class_name, java_code
        archive = Path(run_dir) / "generated_suite.tar.bz2"
        archive.write_text("archive", encoding="utf-8")
        return str(archive)

    def fake_run_command(command, cwd):
        del cwd
        if command[1] == "coverage":
            coverage_call_count["count"] += 1
            return CommandResult(command=command, exit_code=1, stdout="", stderr="coverage failed")
        if command[1] == "compile":
            compile_call_count["count"] += 1
            return CommandResult(command=command, exit_code=0, stdout="", stderr="")
        raise AssertionError("mutation test command should not run")

    monkeypatch.setattr("src.runners.defects4j_runner._write_suite_archive_for_generated_test", fake_write_suite_archive)
    monkeypatch.setattr("src.runners.defects4j_runner.run_command", fake_run_command)

    runner = Defects4jRunner(defects4j_bin="/tmp/defects4j", auto_clean=True, temp_root=str(tmp_path / "tmp"))
    result = runner.run(
        llm_output_text=llm_output,
        target_file=str(target_file),
        project_root=str(project_root),
        mutants=[
            MutantInput(
                mutant_id="m1",
                target_rel_path="src/java/org/example/Target.java",
                mutated_source="package org.example;\npublic class Target { int x = 1; }\n",
            )
        ],
    )

    assert result.status == "coverage_command_failed"
    assert result.mutation_result is not None
    assert result.mutation_result.executed is False
    assert result.mutation_result.reason == "status_not_success"
    assert coverage_call_count["count"] == 1
    assert compile_call_count["count"] == 0
