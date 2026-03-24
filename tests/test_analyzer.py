"""Tests for Java call analyzer."""

import os
import tempfile
from pathlib import Path

from java_call_analyzer.parser import collect_methods_and_calls, collect_target_methods
from java_call_analyzer.analyzer import build_call_chains


def test_collect_target_methods():
    """Test collecting methods from target Java file."""
    test_file = Path(__file__).parent / "test_data" / "B.java"
    methods = collect_target_methods(str(test_file))

    assert len(methods) == 2
    assert "testdata.B.bar(0)" in methods
    assert "testdata.B.baz(0)" in methods


def test_collect_methods_and_calls():
    """Test parsing repository and collecting call relationships."""
    test_dir = Path(__file__).parent / "test_data"

    method_defs, callers, callees = collect_methods_and_calls(str(test_dir))

    # Check method definitions
    assert "testdata.A.foo(0)" in method_defs
    assert "testdata.B.bar(0)" in method_defs
    assert "testdata.B.baz(0)" in method_defs

    # Check callers (who calls whom)
    assert "testdata.A.foo(0)" in callers["testdata.B.bar(0)"]
    assert "testdata.B.bar(0)" in callers["testdata.B.baz(0)"]

    # Check callees (whom does this call)
    assert "testdata.B.bar(0)" in callees["testdata.A.foo(0)"]
    assert "testdata.B.baz(0)" in callees["testdata.B.bar(0)"]


def test_build_call_chains():
    """Test building call chains."""
    test_dir = Path(__file__).parent / "test_data"

    method_defs, callers, callees = collect_methods_and_calls(str(test_dir))
    target_methods = ["testdata.B.bar(0)"]

    up_chains, down_chains = build_call_chains(target_methods, callers, callees)

    # Check upward chains
    assert len(up_chains) == 1
    method, chains = up_chains[0]
    assert method == "testdata.B.bar(0)"
    assert len(chains) > 0
    # Should find A.foo -> B.bar

    # Check downward chains - multiple chains for one method
    assert len(down_chains) >= 1
    # All should be for the same method
    methods = [m for m, c in down_chains]
    assert all(m == "testdata.B.bar(0)" for m in methods)
    # Should have multiple paths