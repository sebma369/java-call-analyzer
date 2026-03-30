#java AST 文件解析器，使用 javalang 库从 Java 代码中提取方法定义和调用关系。

import sys
from collections import defaultdict

import javalang

from .utils import find_java_files, get_package, full_class_name


def collect_methods_and_calls(repo_root):
    # 解析所有 Java 文件，收集方法定义和调用关系。
    method_defs = {}
    methods_by_name = defaultdict(set)
    callers = defaultdict(set)  
    callees = defaultdict(set) 

    for java_file in find_java_files(repo_root):
        with open(java_file, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read()
        try:
            tree = javalang.parse.parse(text)
        except Exception as ex:
            # 跳过解析错误
            print(f'WARN: 无法解析 Java 文件 {java_file}: {ex}', file=sys.stderr)
            continue

        package_name = get_package(tree)

        # class stack 支持嵌套类
        class_stack = []

        for path, node in tree.filter(javalang.tree.TypeDeclaration):
            if not isinstance(node, (javalang.tree.ClassDeclaration, javalang.tree.InterfaceDeclaration, javalang.tree.EnumDeclaration)):
                continue
            # 通过遍历祖先节点构建嵌套类路径
            ancestors = [n for n in path if isinstance(n, javalang.tree.TypeDeclaration)]
            class_stack = [n.name for n in ancestors[:-1] if n is not node]
            cls_name = full_class_name(package_name, class_stack, node)

            # 收集当前类的方法
            for method in node.methods:
                method_key = f'{cls_name}.{method.name}({len(method.parameters)})'
                method_defs[method_key] = {
                    'file': java_file,
                    'class': cls_name,
                    'name': method.name,
                    'params': len(method.parameters),
                }
                methods_by_name[method.name].add(method_key)

            # 收集构造器也当作方法
            for ctor in node.constructors:
                ctor_key = f'{cls_name}.{node.name}({len(ctor.parameters)})'
                method_defs[ctor_key] = {
                    'file': java_file,
                    'class': cls_name,
                    'name': node.name,
                    'params': len(ctor.parameters),
                }
                methods_by_name[node.name].add(ctor_key)

        # 解析调用关系，按方法 scope 收集
        for path, method in tree.filter(javalang.tree.MethodDeclaration):
            # 查找包含类名
            parent_class = None
            for ancestor in reversed(path[:-1]):
                if isinstance(ancestor, javalang.tree.TypeDeclaration):
                    parent_class = ancestor
                    break
            if not parent_class:
                continue
            class_parent = full_class_name(package_name, [], parent_class)
            caller_id = f'{class_parent}.{method.name}({len(method.parameters)})'

            # 从方法体中查找方法调用
            if method.body:
                for _, invocation in method.filter(javalang.tree.MethodInvocation):
                    member = invocation.member
                    qualifier = invocation.qualifier
                    # 对于所有可能的方法名称都做近似匹配
                    for candidate in methods_by_name.get(member, []):
                        callers[candidate].add(caller_id)
                        callees[caller_id].add(candidate)

                    if qualifier:
                        # 如果限定符是类名（首字母大写），尝试完整匹配
                        if qualifier and qualifier[0].isupper():
                            qname = f'{qualifier}.{member}()'
                            callers[qname].add(caller_id)
                            callees[caller_id].add(qname)

                for _, invocation in method.filter(javalang.tree.SuperMethodInvocation):
                    member = invocation.member
                    for candidate in methods_by_name.get(member, []):
                        callers[candidate].add(caller_id)
                        callees[caller_id].add(candidate)

        # 解析构造器调用关系
        for path, ctor in tree.filter(javalang.tree.ConstructorDeclaration):
            parent_class = None
            for ancestor in reversed(path[:-1]):
                if isinstance(ancestor, javalang.tree.TypeDeclaration):
                    parent_class = ancestor
                    break
            if not parent_class:
                continue
            class_parent = full_class_name(package_name, [], parent_class)
            caller_id = f'{class_parent}.{parent_class.name}({len(ctor.parameters)})'
            if ctor.body:
                for _, invocation in ctor.filter(javalang.tree.ClassCreator):
                    typ = invocation.type.name
                    # Package unknown,匹配同名构造器
                    for candidate in methods_by_name.get(typ, []):
                        callers[candidate].add(caller_id)
                        callees[caller_id].add(candidate)

    return method_defs, callers, callees


def collect_target_methods(target_java_file):
    # 从目标 Java 文件中收集方法定义，返回方法标识符列表。
    methods = []
    with open(target_java_file, 'r', encoding='utf-8', errors='ignore') as f:
        text = f.read()
    tree = javalang.parse.parse(text)
    package_name = get_package(tree)

    for path, node in tree.filter(javalang.tree.TypeDeclaration):
        if not isinstance(node, (javalang.tree.ClassDeclaration, javalang.tree.InterfaceDeclaration, javalang.tree.EnumDeclaration)):
            continue
        cls_name = full_class_name(package_name, [], node)
        for method in node.methods:
            methods.append(f'{cls_name}.{method.name}({len(method.parameters)})')
        for ctor in node.constructors:
            methods.append(f'{cls_name}.{node.name}({len(ctor.parameters)})')

    if not methods:
        print('WARN: 未找到目标文件中方法', target_java_file, file=sys.stderr)
    return methods