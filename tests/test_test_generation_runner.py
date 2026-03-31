"""Tests for generated test extraction and execution helpers."""

from pathlib import Path

from src.runners.defects4j_runner import (
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
