"""Execution path analyzer for Java methods."""

import sys
from collections import defaultdict

import javalang
import networkx as nx

from .utils import get_package, full_class_name


class CFGBuilder:
    """Builds Control Flow Graph for a Java method."""

    def __init__(self):
        self.graph = nx.DiGraph()
        self.node_counter = 0
        self.entry_node = None
        self.exit_nodes = []

    def add_node(self, label):
        """Add a node to the graph and return its ID."""
        node_id = self.node_counter
        self.node_counter += 1
        self.graph.add_node(node_id, label=label)
        return node_id

    def build_cfg(self, method_body):
        """Build CFG from method body."""
        self.entry_node = self.add_node("entry")
        current = self.entry_node
        if method_body:
            if isinstance(method_body, list):
                # method_body is a list of statements
                for stmt in method_body:
                    result = self.process_statement(stmt, current)
                    if result is not None:
                        current = result
                    if current in self.exit_nodes:
                        # If we hit an exit, stop processing
                        break
            else:
                # method_body is a BlockStatement
                current = self.process_block(method_body, current)
        
        # Add exit only if we didn't end with a return/break/etc.
        if current not in self.exit_nodes and current is not None:
            exit_node = self.add_node("exit")
            self.graph.add_edge(current, exit_node)
            self.exit_nodes.append(exit_node)
        return self.graph

    def process_block(self, block, incoming):
        """Process a block of statements."""
        current = incoming
        if isinstance(block, list):
            statements = block
        elif hasattr(block, 'statements'):
            statements = block.statements
        else:
            statements = []

        for stmt in statements:
            current = self.process_statement(stmt, current)
            if current in self.exit_nodes:
                # If we hit an exit, stop processing this block
                return current
        return current

    def process_statement(self, stmt, incoming):
        """Process a single statement."""
        if isinstance(stmt, javalang.tree.IfStatement):
            result = self.process_if_statement(stmt, incoming)
            return result if result is not None else incoming
        elif isinstance(stmt, (javalang.tree.WhileStatement, javalang.tree.ForStatement)):
            return self.process_loop_statement(stmt, incoming)
        elif isinstance(stmt, javalang.tree.ReturnStatement):
            return self.process_return_statement(stmt, incoming)
        elif isinstance(stmt, javalang.tree.BreakStatement):
            return self.process_break_statement(stmt, incoming)
        elif isinstance(stmt, javalang.tree.ContinueStatement):
            return self.process_continue_statement(stmt, incoming)
        elif isinstance(stmt, javalang.tree.TryStatement):
            return self.process_try_statement(stmt, incoming)
        elif isinstance(stmt, javalang.tree.SwitchStatement):
            return self.process_switch_statement(stmt, incoming)
        else:
            # Generic statement (assignment, method call, etc.)
            stmt_node = self.add_node(str(stmt))
            self.graph.add_edge(incoming, stmt_node)
            return stmt_node

    def process_if_statement(self, stmt, incoming):
        """Process if-else statement."""
        cond_node = self.add_node(f"if {stmt.condition}")
        self.graph.add_edge(incoming, cond_node)

        # Then block
        then_end = self.process_block(stmt.then_statement, cond_node)

        if stmt.else_statement:
            # Else block
            else_end = self.process_block(stmt.else_statement, cond_node)
            # Only create merge if neither branch returns
            if then_end not in self.exit_nodes and else_end not in self.exit_nodes:
                # Merge point
                merge_node = self.add_node("merge")
                self.graph.add_edge(then_end, merge_node)
                self.graph.add_edge(else_end, merge_node)
                return merge_node
            else:
                # At least one branch returns, this if statement is an exit point
                if_exit = self.add_node("if_exit")
                self.exit_nodes.append(if_exit)
                return if_exit
        else:
            # No else, continue after then if it doesn't return
            if then_end not in self.exit_nodes:
                return then_end
            else:
                # Then branch returns, this if statement is an exit point
                if_exit = self.add_node("if_exit")
                self.exit_nodes.append(if_exit)
                return if_exit

    def process_loop_statement(self, stmt, incoming):
        """Process while or for loop."""
        loop_type = "while" if isinstance(stmt, javalang.tree.WhileStatement) else "for"
        cond_expr = stmt.condition if hasattr(stmt, 'condition') else str(stmt.control)
        cond_node = self.add_node(f"{loop_type} {cond_expr}")
        self.graph.add_edge(incoming, cond_node)

        # Loop body
        body_end = self.process_block(stmt.body, cond_node)
        self.graph.add_edge(body_end, cond_node)  # Back edge

        # Exit from loop
        after_node = self.add_node(f"after_{loop_type}")
        self.graph.add_edge(cond_node, after_node)  # False branch
        return after_node

    def process_return_statement(self, stmt, incoming):
        """Process return statement."""
        ret_node = self.add_node(f"return {stmt.expression if stmt.expression else ''}")
        self.graph.add_edge(incoming, ret_node)
        self.exit_nodes.append(ret_node)
        return ret_node  # No further connection

    def process_break_statement(self, stmt, incoming):
        """Process break statement."""
        break_node = self.add_node("break")
        self.graph.add_edge(incoming, break_node)
        self.exit_nodes.append(break_node)
        return break_node

    def process_continue_statement(self, stmt, incoming):
        """Process continue statement."""
        continue_node = self.add_node("continue")
        self.graph.add_edge(incoming, continue_node)
        # Note: In full implementation, this should connect back to loop condition
        return continue_node

    def process_try_statement(self, stmt, incoming):
        """Process try-catch-finally."""
        try_node = self.add_node("try")
        self.graph.add_edge(incoming, try_node)
        try_end = self.process_block(stmt.block, try_node)

        merge_nodes = [try_end]

        # Catch blocks
        for catch in stmt.catches:
            catch_node = self.add_node(f"catch {catch.parameter}")
            self.graph.add_edge(try_node, catch_node)  # Exception edge
            catch_end = self.process_block(catch.block, catch_node)
            merge_nodes.append(catch_end)

        # Finally block
        if stmt.finally_block:
            finally_node = self.add_node("finally")
            for merge in merge_nodes:
                self.graph.add_edge(merge, finally_node)
            finally_end = self.process_block(stmt.finally_block, finally_node)
            return finally_end

        # Merge catches
        if len(merge_nodes) > 1:
            merge_node = self.add_node("merge_catches")
            for node in merge_nodes:
                self.graph.add_edge(node, merge_node)
            return merge_node
        return try_end

    def process_switch_statement(self, stmt, incoming):
        """Process switch statement."""
        switch_node = self.add_node(f"switch {stmt.expression}")
        self.graph.add_edge(incoming, switch_node)

        merge_nodes = []

        for case in stmt.cases:
            case_node = self.add_node(f"case {case.case}")
            self.graph.add_edge(switch_node, case_node)
            case_end = self.process_block(case, case_node)
            merge_nodes.append(case_end)

        # Merge all cases
        if merge_nodes:
            merge_node = self.add_node("merge_switch")
            for node in merge_nodes:
                self.graph.add_edge(node, merge_node)
            return merge_node
        return switch_node


def analyze_execution_paths(java_file_path):
    """Analyze all execution paths for methods in a Java class file."""
    with open(java_file_path, 'r', encoding='utf-8', errors='ignore') as f:
        text = f.read()

    try:
        tree = javalang.parse.parse(text)
    except Exception as ex:
        raise SystemExit(f'无法解析 Java 文件 {java_file_path}: {ex}')

    package_name = get_package(tree)
    class_stack = []
    results = {}

    for path, node in tree.filter(javalang.tree.TypeDeclaration):
        if not isinstance(node, (javalang.tree.ClassDeclaration, javalang.tree.InterfaceDeclaration, javalang.tree.EnumDeclaration)):
            continue
        ancestors = [n for n in path if isinstance(n, javalang.tree.TypeDeclaration)]
        class_stack = [n.name for n in ancestors[:-1] if n is not node]
        cls_name = full_class_name(package_name, class_stack, node)

        for method in node.methods:
            method_key = f'{cls_name}.{method.name}({len(method.parameters)})'
            builder = CFGBuilder()
            cfg = builder.build_cfg(method.body)

            # Enumerate all paths from entry to exits
            paths = []
            for exit_node in builder.exit_nodes:
                try:
                    for path_nodes in nx.all_simple_paths(cfg, builder.entry_node, exit_node, cutoff=50):
                        path_labels = [cfg.nodes[n]['label'] for n in path_nodes]
                        paths.append(path_labels)
                except nx.NetworkXNoPath:
                    continue

            results[method_key] = paths

    return results