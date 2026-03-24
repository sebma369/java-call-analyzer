"""Command line interface for Java static analyzer."""

import argparse
import os

from .parser import collect_methods_and_calls, collect_target_methods
from .analyzer import build_call_chains
from .execution_path_analyzer import analyze_execution_paths


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(description='Java 静态分析工具')
    parser.add_argument('target', type=str, help='目标 Java 文件路径(绝对或相对)')
    parser.add_argument('--mode', choices=['call-chain', 'execution-path'], default='call-chain',
                       help='分析模式:call-chain(调用链)或 execution-path(执行路径)')
    parser.add_argument('--repo', type=str, help='Java 代码仓库根目录(call-chain)')
    parser.add_argument('--depth', type=int, default=10, help='最大深度(call-chain)')
    args = parser.parse_args()

    target_file = os.path.abspath(args.target)

    if not os.path.isfile(target_file):
        raise SystemExit(f'目标 Java 文件不存在：{target_file}')

    print(f'目标文件：{target_file}')
    print(f'分析模式：{args.mode}')

    if args.mode == 'call-chain':
        if not args.repo:
            raise SystemExit('call-chain 模式需要指定 --repo 参数')
        repo_root = os.path.abspath(args.repo)
        if not os.path.isdir(repo_root):
            raise SystemExit(f'仓库目录不存在：{repo_root}')
        print(f'仓库目录：{repo_root}')

        method_defs, callers, callees = collect_methods_and_calls(repo_root)
        target_methods = collect_target_methods(target_file)

        up_chains, down_chains = build_call_chains(target_methods, callers, callees, max_depth=args.depth)

        print('\n===== 调用链结果 =====')
        for target_method in target_methods:
            print(f'\n目标方法：{target_method}')
            print('  ↑ 向上调用链（谁调用了我）：')
            related_up = [c for m, c in up_chains if m == target_method]
            if not related_up:
                print('    (未检测到向上调用链)')
            else:
                for idx, path in enumerate(related_up, 1):
                    print(f'    链 {idx}: ' + ' -> '.join(path))

            print('  ↓ 向下调用链（我调用了谁）：')
            related_down = [c for m, c in down_chains if m == target_method]
            if not related_down:
                print('    (未检测到向下调用链)')
            else:
                for idx, path in enumerate(related_down, 1):
                    print(f'    链 {idx}: ' + ' -> '.join(path))

    elif args.mode == 'execution-path':
        results = analyze_execution_paths(target_file)

        print('\n===== 执行路径结果 =====')
        for method, paths in results.items():
            print(f'\n方法：{method}')
            if not paths:
                print('  (无执行路径)')
            else:
                for idx, path in enumerate(paths, 1):
                    print(f'  路径 {idx}: ' + ' -> '.join(path))


if __name__ == '__main__':
    main()