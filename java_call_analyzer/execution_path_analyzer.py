# 路径分析器 - 构建方法的控制流图并提取执行路径

import sys
from collections import defaultdict

import javalang
import networkx as nx

from .utils import get_package, full_class_name


class CFGBuilder:
    # 为Java方法构建控制流图

    def __init__(self):
        self.graph = nx.DiGraph()
        self.node_counter = 0
        self.entry_node = None
        self.exit_nodes = []

    def add_node(self, label):
        # 向图中添加一个节点并返回其 ID
        node_id = self.node_counter
        self.node_counter += 1
        self.graph.add_node(node_id, label=label)
        return node_id

    def build_cfg(self, method_body):
        # 从方法体构建控制流图
        self.entry_node = self.add_node("entry")
        current = self.entry_node
        if method_body:
            if isinstance(method_body, list):
                # method_body 是一个语句列表
                for stmt in method_body:
                    result = self.process_statement(stmt, current)
                    if result is not None:
                        current = result
                    if current in self.exit_nodes:
                        # 如果我们遇到退出，停止处理
                        break
            else:
                # method_body 是一个单独的块
                current = self.process_block(method_body, current)
        
        # 只有在我们没有以 return/break 等结束时才添加 exit。
        if current not in self.exit_nodes and current is not None:
            exit_node = self.add_node("exit")
            self.graph.add_edge(current, exit_node)
            self.exit_nodes.append(exit_node)
        return self.graph

    def process_block(self, block, incoming):
        # 处理一块语句(方法体、if/else 块、循环块等)
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
                # 如果我们遇到退出，停止处理当前块
                return current
        return current

    def process_statement(self, stmt, incoming):
        #处理单个语句，根据类型构建相应的控制流结构
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
            # 对于其他类型的语句，简单地添加一个节点并连接
            stmt_node = self.add_node(str(stmt))
            self.graph.add_edge(incoming, stmt_node)
            return stmt_node

    def process_if_statement(self, stmt, incoming):
        # 处理 if 语句，创建条件节点和分支结构
        cond_node = self.add_node(f"if {stmt.condition}")
        self.graph.add_edge(incoming, cond_node)

        # Then block
        then_end = self.process_block(stmt.then_statement, cond_node)

        if stmt.else_statement:
            # Else block
            else_end = self.process_block(stmt.else_statement, cond_node)
            # 如果 then 和 else 都没有退出点，继续合并
            if then_end not in self.exit_nodes and else_end not in self.exit_nodes:
                # 合并 then 和 else 的后续路径
                merge_node = self.add_node("merge")
                self.graph.add_edge(then_end, merge_node)
                self.graph.add_edge(else_end, merge_node)
                return merge_node
            else:
                # 如果其中一个分支有退出点，这个 if 语句也是一个退出点
                if_exit = self.add_node("if_exit")
                self.exit_nodes.append(if_exit)
                return if_exit
        else:
            # 没有 else 分支，如果 then 分支没有退出点，继续；否则这个 if 语句是一个退出点
            if then_end not in self.exit_nodes:
                return then_end
            else:
                # then 分支有退出点，这个 if 语句也是一个退出点
                if_exit = self.add_node("if_exit")
                self.exit_nodes.append(if_exit)
                return if_exit

    def process_loop_statement(self, stmt, incoming):
        # 处理循环语句，创建条件节点和循环结构
        loop_type = "while" if isinstance(stmt, javalang.tree.WhileStatement) else "for"
        cond_expr = stmt.condition if hasattr(stmt, 'condition') else str(stmt.control)
        cond_node = self.add_node(f"{loop_type} {cond_expr}")
        self.graph.add_edge(incoming, cond_node)

        # Loop body
        body_end = self.process_block(stmt.body, cond_node)
        self.graph.add_edge(body_end, cond_node) 
        
        # Exit from loop
        after_node = self.add_node(f"after_{loop_type}")
        self.graph.add_edge(cond_node, after_node) 
        return after_node

    def process_return_statement(self, stmt, incoming):
        # 处理 return 语句，创建一个退出节点
        ret_node = self.add_node(f"return {stmt.expression if stmt.expression else ''}")
        self.graph.add_edge(incoming, ret_node)
        self.exit_nodes.append(ret_node)
        return ret_node  # 返回节点也是一个退出点

    def process_break_statement(self, stmt, incoming):
        # 处理 break 语句，创建一个退出节点
        break_node = self.add_node("break")
        self.graph.add_edge(incoming, break_node)
        self.exit_nodes.append(break_node)
        return break_node

    def process_continue_statement(self, stmt, incoming):
        # 处理 continue 语句，创建一个节点并连接，但不一定是退出点
        continue_node = self.add_node("continue")
        self.graph.add_edge(incoming, continue_node)
        # continue 语句不一定是退出点，因为它可能跳回循环条件，但我们不需要在这里特别处理它
        return continue_node

    def process_try_statement(self, stmt, incoming):
        # 处理 try-catch-finally 语句，创建相应的控制流结构
        try_node = self.add_node("try")
        self.graph.add_edge(incoming, try_node)
        try_end = self.process_block(stmt.block, try_node)

        merge_nodes = [try_end]

        # Catch blocks
        for catch in stmt.catches:
            catch_node = self.add_node(f"catch {catch.parameter}")
            self.graph.add_edge(try_node, catch_node)  # 异常从 try 到 catch
            catch_end = self.process_block(catch.block, catch_node)
            merge_nodes.append(catch_end)

        # Finally block
        if stmt.finally_block:
            finally_node = self.add_node("finally")
            for merge in merge_nodes:
                self.graph.add_edge(merge, finally_node)
            finally_end = self.process_block(stmt.finally_block, finally_node)
            return finally_end

        # 如果没有 finally，合并 try 和 catch 的后续路径
        if len(merge_nodes) > 1:
            merge_node = self.add_node("merge_catches")
            for node in merge_nodes:
                self.graph.add_edge(node, merge_node)
            return merge_node
        return try_end

    def process_switch_statement(self, stmt, incoming):
        # 处理 switch 语句，创建条件节点和 case 分支结构
        switch_node = self.add_node(f"switch {stmt.expression}")
        self.graph.add_edge(incoming, switch_node)

        merge_nodes = []

        for case in stmt.cases:
            case_node = self.add_node(f"case {case.case}")
            self.graph.add_edge(switch_node, case_node)
            case_end = self.process_block(case, case_node)
            merge_nodes.append(case_end)

        # 合并所有 case 的后续路径
        if merge_nodes:
            merge_node = self.add_node("merge_switch")
            for node in merge_nodes:
                self.graph.add_edge(node, merge_node)
            return merge_node
        return switch_node


def analyze_execution_paths(java_file_path):
    # 分析 Java 文件中每个方法的执行路径，返回一个字典，键是方法标识符，值是执行路径列表
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

            # 从 entry 到 exit 的所有简单路径
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