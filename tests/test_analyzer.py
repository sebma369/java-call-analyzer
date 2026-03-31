"""Tests for Java call analyzer."""

import os
import tempfile
from pathlib import Path

from src.analysis.java_parser import collect_methods_and_calls, collect_target_methods
from src.analysis.call_chain import build_call_chains


def test_collect_target_methods():
    #测试从目标 Java 文件中提取方法定义。
    test_file = Path(__file__).parent / "test_data" / "B.java"
    methods = collect_target_methods(str(test_file))

    assert len(methods) == 2
    assert "testdata.B.bar(0)" in methods
    assert "testdata.B.baz(0)" in methods


def test_collect_methods_and_calls():
    #测试从 Java 代码仓库中收集方法定义和调用关系。
    test_dir = Path(__file__).parent / "test_data"

    method_defs, callers, callees = collect_methods_and_calls(str(test_dir))

    #检查方法定义
    assert "testdata.A.foo(0)" in method_defs
    assert "testdata.B.bar(0)" in method_defs
    assert "testdata.B.baz(0)" in method_defs

    #检查调用者（谁调用了这个方法）
    assert "testdata.A.foo(0)" in callers["testdata.B.bar(0)"]
    assert "testdata.B.bar(0)" in callers["testdata.B.baz(0)"]

    #检查被调用者（这个方法调用了谁）
    assert "testdata.B.bar(0)" in callees["testdata.A.foo(0)"]
    assert "testdata.B.baz(0)" in callees["testdata.B.bar(0)"]


def test_build_call_chains():
    #测试构建调用链的功能。
    test_dir = Path(__file__).parent / "test_data"

    method_defs, callers, callees = collect_methods_and_calls(str(test_dir))
    target_methods = ["testdata.B.bar(0)"]

    up_chains, down_chains = build_call_chains(target_methods, callers, callees)

    #检查向上调用链 - 应该有 A.foo -> B.bar
    assert len(up_chains) == 1
    method, chains = up_chains[0]
    assert method == "testdata.B.bar(0)"
    assert len(chains) > 0

    #多条向下调用链 - B.bar -> B.baz
    assert len(down_chains) >= 1
    #所有向下调用链的起点都应该是 B.bar(0)
    methods = [m for m, c in down_chains]
    assert all(m == "testdata.B.bar(0)" for m in methods)
    #至少有一条链应该是 B.bar(0) -> B.baz(0)


def test_analyze_execution_paths():
    #测试分析方法执行路径的功能。
    from src.analysis.execution_paths import analyze_execution_paths

    test_file = Path(__file__).parent / "test_data" / "ExecutionPathTest.java"
    results = analyze_execution_paths(str(test_file))

    # 检查结果中包含预期的方法和路径
    expected_methods = [
        "testdata.ExecutionPathTest.simpleMethod(1)",
        "testdata.ExecutionPathTest.loopMethod(1)",
        "testdata.ExecutionPathTest.switchMethod(1)"
    ]

    for method in expected_methods:
        assert method in results
        assert isinstance(results[method], list)
        # 确保每个方法至少有一个执行路径
        assert len(results[method]) > 0

    # 检查 simpleMethod 的执行路径，应该至少有 if 和 else 两条路径
    simple_paths = results["testdata.ExecutionPathTest.simpleMethod(1)"]
    assert len(simple_paths) >= 2  #至少有 if 和 else 两条路径

    #检查每条路径的起点和终点
    for path in simple_paths:
        assert "entry" in path[0]
        assert any("return" in step for step in path)