
import argparse
import json
import os

from .analysis.java_parser import collect_methods_and_calls, collect_target_methods
from .analysis.call_chain import build_call_chains
from .analysis.execution_paths import analyze_execution_paths
from .integration.openai_client import (
    LLMConfig,
    call_llm_with_prompt,
    get_default_llm_output_path,
    save_llm_output_text,
)
from .control.iterative_controller import run_iterative_feedback_loop
from .runners.defects4j_runner import (
    Defects4jRunner,
    MutantInput,
)
from .prompting.structured_prompt import (
    build_structured_prompt,
    get_default_prompt_output_path,
    get_default_prompt_json_output_path,
    save_prompt_json,
    save_prompt_text,
)


def main():
    # CLI 入口，解析命令行参数，根据选择的分析模式执行相应的功能，并输出结果。
    parser = argparse.ArgumentParser(description='Java 静态分析工具')
    parser.add_argument('target', type=str, help='目标 Java 文件路径(绝对或相对)')
    parser.add_argument(
        '--mode',
        choices=['call-chain', 'execution-path', 'structured-prompt', 'llm-generate'],
        default='llm-generate',
        help='分析模式:call-chain(调用链)、execution-path(执行路径)、structured-prompt(结构化Prompt)或 llm-generate(调用大模型生成测试)'
    )
    parser.add_argument('--repo', type=str, help='Java 代码仓库根目录')
    parser.add_argument('--depth', type=int, default=10, help='最大深度')
    parser.add_argument('--prompt-out', type=str, help='structured-prompt模式下输出文件路径(可选)')
    parser.add_argument('--prompt-json-out', type=str, help='structured-prompt模式下JSON输出文件路径(可选)')
    parser.add_argument('--llm-out', type=str, help='llm-generate模式下模型输出保存路径(可选)')
    parser.add_argument(
        '--apply-generated-test',
        dest='apply_generated_test',
        action='store_true',
        default=True,
        help='llm-generate后自动提取并写入测试代码，然后编译并运行测试(默认开启)'
    )
    parser.add_argument(
        '--no-apply-generated-test',
        dest='apply_generated_test',
        action='store_false',
        help='关闭llm-generate后自动写入并执行测试'
    )
    parser.add_argument('--test-project-root', type=str, help='测试代码写入与执行的项目根目录(默认与--repo相同)')
    parser.add_argument('--defects4j-bin', type=str, default='/usr/src/defects4j/framework/bin/defects4j', help='defects4j 可执行文件路径')
    parser.add_argument('--no-auto-clean', action='store_true', help='关闭自动清理模式（默认开启）')
    parser.add_argument('--iterative', action='store_true', help='在 llm-generate 模式下启用多轮执行反馈循环')
    parser.add_argument('--max-rounds', type=int, default=3, help='多轮执行反馈循环的最大轮次（--iterative 启用时生效）')
    parser.add_argument('--mutant-count', type=int, default=5, help='每轮变异生成对话要求生成的变异体数量')
    parser.add_argument('--mutants-json', type=str, help='可选：变异体输入JSON文件路径（仅 llm-generate 模式使用）')
    args = parser.parse_args()

    def load_mutants_from_json(json_path: str) -> list[MutantInput]:
        with open(json_path, 'r', encoding='utf-8') as file_obj:
            payload = json.load(file_obj)

        raw_items = payload.get('mutants') if isinstance(payload, dict) else payload
        if not isinstance(raw_items, list):
            raise SystemExit('mutants-json 内容必须是数组，或包含 mutants 数组字段')

        mutants: list[MutantInput] = []
        for idx, item in enumerate(raw_items, start=1):
            if not isinstance(item, dict):
                raise SystemExit(f'mutants-json 第 {idx} 项必须是对象')

            mutant_id = str(item.get('mutant_id', f'mutant_{idx}')).strip()
            target_rel_path = str(item.get('target_rel_path', '')).strip()
            mutated_source = item.get('mutated_source')

            if not target_rel_path:
                raise SystemExit(f'mutants-json 第 {idx} 项缺少 target_rel_path')
            if not isinstance(mutated_source, str) or not mutated_source.strip():
                raise SystemExit(f'mutants-json 第 {idx} 项缺少 mutated_source')

            mutants.append(
                MutantInput(
                    mutant_id=mutant_id,
                    target_rel_path=target_rel_path,
                    mutated_source=mutated_source,
                )
            )
        return mutants

    target_file = os.path.abspath(args.target)
    mutants: list[MutantInput] | None = None
    if args.mutants_json:
        mutants_json = os.path.abspath(args.mutants_json)
        if not os.path.isfile(mutants_json):
            raise SystemExit(f'变异体 JSON 文件不存在：{mutants_json}')
        mutants = load_mutants_from_json(mutants_json)

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

    elif args.mode == 'structured-prompt':
        if not args.repo:
            raise SystemExit('structured-prompt 模式需要指定 --repo 参数')
        repo_root = os.path.abspath(args.repo)
        if not os.path.isdir(repo_root):
            raise SystemExit(f'仓库目录不存在：{repo_root}')
        print(f'仓库目录：{repo_root}')

        result = build_structured_prompt(repo_root, target_file, depth=args.depth)

        print('\n===== 结构化 Prompt =====')
        print(result.prompt)

        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        temp_out_path = get_default_prompt_output_path(project_root, target_file)
        temp_out_path = save_prompt_text(result.prompt, temp_out_path)
        print(f'\n临时 Prompt 已写入：{temp_out_path}')

        temp_json_path = get_default_prompt_json_output_path(project_root, target_file)
        payload = result.to_payload()
        temp_json_path = save_prompt_json(payload, temp_json_path)
        print(f'临时 Prompt JSON 已写入：{temp_json_path}')

        if args.prompt_out:
            custom_out_path = save_prompt_text(result.prompt, args.prompt_out)
            print(f'Prompt 已写入指定路径：{custom_out_path}')

        if args.prompt_json_out:
            custom_json_path = save_prompt_json(payload, args.prompt_json_out)
            print(f'Prompt JSON 已写入指定路径：{custom_json_path}')

    elif args.mode == 'llm-generate':
        if not args.repo:
            raise SystemExit('llm-generate 模式需要指定 --repo 参数')
        repo_root = os.path.abspath(args.repo)
        if not os.path.isdir(repo_root):
            raise SystemExit(f'仓库目录不存在：{repo_root}')
        print(f'仓库目录：{repo_root}')

        if args.iterative:
            if args.max_rounds <= 0:
                raise SystemExit('--max-rounds 必须为正整数')

            print('\n===== 开始多轮执行反馈循环 =====')
            llm_config = LLMConfig()
            result = run_iterative_feedback_loop(
                repo_root=repo_root,
                target_file=target_file,
                max_rounds=args.max_rounds,
                depth=args.depth,
                llm_config=llm_config,
                defects4j_bin=args.defects4j_bin,
                auto_clean=not args.no_auto_clean,
                mutants=mutants,
                mutant_count=args.mutant_count,
            )

            print(f'执行轮次：{result.rounds_executed}')
            print(f'最终状态：{result.final_status}')
            print(f'变异体数量：{result.final_mutant_count}/{result.requested_mutant_count}')
            print(f'循环输出目录：{result.run_root}')
            print(f'轮次汇总报告：{result.summary_path}')
            for item in result.rounds:
                print(
                    f"  round {item.round_id}: prompt_type={item.prompt_type}, "
                    f"status={item.status}, report={item.run_report_path}"
                )
            print(f'变异生成轮次：{len(result.mutation_generations)}')
            return

        result = build_structured_prompt(repo_root, target_file, depth=args.depth)
        print('\n===== 结构化 Prompt 已生成，开始调用 LLM =====')

        llm_config = LLMConfig()
        try:
            llm_result = call_llm_with_prompt(result.prompt, llm_config)
        except (ValueError, RuntimeError) as ex:
            raise SystemExit(f'LLM 调用失败：{ex}') from ex

        print('\n===== LLM 输出 =====')
        print(llm_result.response_text)

        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        default_llm_out = get_default_llm_output_path(project_root, target_file)
        saved_out = save_llm_output_text(llm_result.response_text, default_llm_out)
        print(f'\n临时 LLM 输出已写入：{saved_out}')

        if args.llm_out:
            custom_out = save_llm_output_text(llm_result.response_text, args.llm_out)
            print(f'LLM 输出已写入指定路径：{custom_out}')

        if args.apply_generated_test:
            test_project_root = os.path.abspath(args.test_project_root) if args.test_project_root else repo_root
            if not os.path.isdir(test_project_root):
                raise SystemExit(f'测试项目目录不存在：{test_project_root}')

            print('\n===== 开始提取并执行生成测试 =====')
            runner = Defects4jRunner(
                defects4j_bin=args.defects4j_bin,
                auto_clean=not args.no_auto_clean,
            )
            run_result = runner.run(
                llm_output_text=llm_result.response_text,
                target_file=target_file,
                project_root=test_project_root,
                mutants=mutants,
            )

            print(f"测试文件：{run_result.test_file_path}")
            print(f"测试类：{run_result.test_class}")
            print(f"执行状态：{run_result.status}")
            print(f"覆盖率命令退出码：{run_result.coverage_command_result.exit_code}")
            print(f"临时结果目录：{run_result.temp_result_dir}")
            print(f"结果报告JSON：{run_result.report_json_path}")
            print(f"自动清理：{'开启' if run_result.auto_clean_enabled else '关闭'}")

            if run_result.failing_tests_content:
                print('运行失败详情(failing_tests)：')
                print(run_result.failing_tests_content)

            if run_result.coverage_summary:
                summary = run_result.coverage_summary
                print('覆盖率摘要：')
                print(f'  行覆盖率：{summary.line_coverage_percent}% ({summary.covered_lines}/{summary.total_executable_lines})')
                print(f'  分支覆盖率：{summary.condition_coverage_percent}% ({summary.covered_conditions}/{summary.total_conditions})')
                print(f'  未覆盖行：{", ".join(map(str, summary.uncovered_lines)) if summary.uncovered_lines else "(无)"}')

            if run_result.auto_clean_enabled:
                print(f"已清理路径数量：{len(run_result.cleaned_paths)}")

            if run_result.mutation_result is not None:
                mutation = run_result.mutation_result
                print('变异测试摘要：')
                print(f"  是否执行：{'是' if mutation.executed else '否'}")
                if not mutation.executed:
                    print(f'  跳过原因：{mutation.reason}')
                print(f'  总变异体：{mutation.total_mutants}')
                print(f'  已执行：{mutation.executed_mutants}')
                print(f'  killed：{mutation.killed}')
                print(f'  survived：{mutation.survived}')
                print(f'  error：{mutation.error_count}')
                print(f'  score：{mutation.mutation_score}%')


if __name__ == '__main__':
    main()