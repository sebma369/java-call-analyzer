#工具函数，用于 Java 文件处理和 AST 分析。

import os


def find_java_files(root):
    # 找到给定目录下的所有 Java 文件，递归搜索。
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if fn.endswith('.java'):
                yield os.path.join(dirpath, fn)


def get_package(tree):
    #从 Java AST 树中提取包名。
    return tree.package.name if tree.package else None


def full_class_name(package_name, class_stack, class_decl):
    #构建完整的类名，包括包名和嵌套类。
    class_name = class_decl.name
    if class_stack:
        class_name = '.'.join(class_stack + [class_name])
    if package_name:
        return package_name + '.' + class_name
    return class_name