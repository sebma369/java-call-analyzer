"""Utility functions for Java call analyzer."""

import os


def find_java_files(root):
    """Find all Java files in the given directory recursively."""
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if fn.endswith('.java'):
                yield os.path.join(dirpath, fn)


def get_package(tree):
    """Extract package name from Java AST tree."""
    return tree.package.name if tree.package else None


def type_name(node):
    """Get type name from AST node."""
    if node is None:
        return None
    if hasattr(node, 'name'):
        return node.name
    return str(node)


def full_class_name(package_name, class_stack, class_decl):
    """Build full class name including package and nested classes."""
    class_name = class_decl.name
    if class_stack:
        class_name = '.'.join(class_stack + [class_name])
    if package_name:
        return package_name + '.' + class_name
    return class_name