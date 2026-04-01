# 在 Defects4J 项目中运行生成的测试代码，收集覆盖率和执行结果，并进行清理。

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import re
import shutil
import subprocess
from typing import Any


@dataclass
class CommandResult:
    # 执行命令的结果，包括命令本身、退出代码、标准输出和标准错误。

    command: list[str]
    exit_code: int
    stdout: str
    stderr: str


@dataclass
class GeneratedTestRunResult:
    # 生成测试的提取和执行流程摘要。

    test_file_path: str
    package_name: str
    class_name: str
    test_methods: list[str]
    compile_result: CommandResult
    test_results: list[CommandResult]
    auto_clean_enabled: bool
    cleaned_paths: list[str]


@dataclass
class CoverageSummary:
    # 覆盖率摘要，用于特定目标类。

    target_class: str
    total_executable_lines: int
    covered_lines: int
    line_coverage_percent: float
    total_conditions: int
    covered_conditions: int
    condition_coverage_percent: float
    uncovered_lines: list[int]


@dataclass
class Defects4jRunResult:
    # 端到端运行生成测试的结果，包括状态、文件路径、覆盖率结果和清理信息。

    status: str
    test_file_path: str
    test_class: str
    coverage_command_result: CommandResult
    failing_tests_content: str
    coverage_summary: CoverageSummary | None
    temp_result_dir: str
    report_json_path: str
    auto_clean_enabled: bool
    cleaned_paths: list[str]


ARTIFACT_PATHS = [
    ".classes_instrumented",
    ".classes_testgen",
    ".test_suite",
    "all_tests",
    "cobertura.ser",
    "coverage.xml",
    "failing_tests",
    "summary.csv",
    "target",
]

MUTABLE_FILE_PATHS = [
    "defects4j.build.properties",
]


def get_testgen_root() -> str:
    # 返回 TestGen 项目的根目录绝对路径，假设当前文件在 src/runners/ 下。
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def ensure_temp_root(temp_root: str | None = None) -> str:
    # 确保临时目录存在，优先使用传入的 temp_root，否则在项目根目录下创建 tmp/。
    root = temp_root or os.path.join(get_testgen_root(), "tmp")
    os.makedirs(root, exist_ok=True)
    return root


def create_run_temp_dir(temp_root: str | None = None) -> str:
    # 在临时目录下创建一个唯一的子目录用于当前运行，格式为 run_YYYYMMDDTHHMMSSZ[_N]。
    root = ensure_temp_root(temp_root)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = os.path.join(root, f"run_{run_id}")
    suffix = 1
    while os.path.exists(run_dir):
        suffix += 1
        run_dir = os.path.join(root, f"run_{run_id}_{suffix}")
    os.makedirs(run_dir, exist_ok=True)
    return run_dir


def snapshot_artifact_state(project_root: str) -> dict[str, bool]:
    # 快照工件路径存在状态，用于在运行命令前检查。
    state: dict[str, bool] = {}
    for rel_path in ARTIFACT_PATHS:
        abs_path = os.path.join(project_root, rel_path)
        state[rel_path] = os.path.exists(abs_path)
    return state


def snapshot_file_contents(project_root: str, rel_paths: list[str]) -> dict[str, str | None]:
    # 快照指定文件的内容，如果文件不存在则记录为 None。
    snapshot: dict[str, str | None] = {}
    for rel_path in rel_paths:
        abs_path = os.path.join(project_root, rel_path)
        if os.path.isfile(abs_path):
            with open(abs_path, "r", encoding="utf-8", errors="ignore") as file_obj:
                snapshot[rel_path] = file_obj.read()
        else:
            snapshot[rel_path] = None
    return snapshot


def restore_file_contents(project_root: str, snapshot: dict[str, str | None]) -> list[str]:
    # 根据快照恢复文件内容，如果快照为 None 则删除文件。
    restored: list[str] = []
    for rel_path, content in snapshot.items():
        abs_path = os.path.join(project_root, rel_path)
        if content is None:
            if os.path.exists(abs_path):
                remove_path(abs_path)
                restored.append(abs_path)
        else:
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as file_obj:
                file_obj.write(content)
            restored.append(abs_path)
    return restored


def remove_path(path: str) -> None:
    # 删除指定路径，无论是文件还是目录，如果路径不存在则不执行任何操作。
    if not os.path.exists(path):
        return
    if os.path.isdir(path):
        shutil.rmtree(path)
    else:
        os.remove(path)


def restore_or_remove_generated_test(test_file_path: str, previous_content: str | None) -> None:
    # 如果之前存在测试文件内容，则恢复它；否则删除生成的测试文件。
    if previous_content is None:
        remove_path(test_file_path)
        return
    with open(test_file_path, "w", encoding="utf-8") as file_obj:
        file_obj.write(previous_content)


def cleanup_generated_run(
    project_root: str,
    artifact_state: dict[str, bool],
    test_file_path: str,
    previous_test_content: str | None,
    file_content_snapshot: dict[str, str | None] | None = None,
) -> list[str]:
    # 清理生成测试运行的产物：恢复或删除测试文件，删除新产生的工件，并根据快照恢复文件内容。
    cleaned: list[str] = []

    restore_or_remove_generated_test(test_file_path, previous_test_content)
    cleaned.append(test_file_path)

    for rel_path, existed_before in artifact_state.items():
        abs_path = os.path.join(project_root, rel_path)
        if not existed_before and os.path.exists(abs_path):
            remove_path(abs_path)
            cleaned.append(abs_path)

    if file_content_snapshot:
        cleaned.extend(restore_file_contents(project_root, file_content_snapshot))

    return cleaned


def extract_java_code_block(llm_output_text: str) -> str:
    # 从 LLM 输出中提取 Java 代码块，优先返回包含 "class " 的块，如果没有则返回第一个代码块，如果没有代码块则返回原文本。
    blocks = re.findall(r"```(?:java)?\s*(.*?)```", llm_output_text, flags=re.DOTALL | re.IGNORECASE)
    if not blocks:
        return llm_output_text.strip()

    for block in blocks:
        if "class " in block:
            return block.strip()
    return blocks[0].strip()


def extract_package_name(java_code: str) -> str:
    # 从 Java 代码中提取 package 声明，如果没有则返回空字符串。
    match = re.search(r"\bpackage\s+([A-Za-z_][\w\.]*)\s*;", java_code)
    return match.group(1) if match else ""


def extract_target_class_fqn(target_file: str) -> str:
    # 从目标 Java 文件中提取完全限定类名（FQN），通过解析 package 声明和 public class 名称，如果没有 package 则返回类名。
    with open(target_file, "r", encoding="utf-8", errors="ignore") as file_obj:
        text = file_obj.read()
    package_name = extract_package_name(text)
    class_name = extract_public_class_name(text) if "public class" in text else os.path.splitext(os.path.basename(target_file))[0]
    return f"{package_name}.{class_name}" if package_name else class_name


def extract_public_class_name(java_code: str) -> str:
    # 从 Java 代码中提取 public class 的名称，如果没有找到则抛出异常。
    match = re.search(r"\bpublic\s+class\s+([A-Za-z_][\w]*)\b", java_code)
    if not match:
        raise ValueError("无法从生成代码中提取 public class 名称")
    return match.group(1)


def extract_test_method_names(java_code: str) -> list[str]:
    # 从 Java 代码中提取使用 @Test 注解的方法名称，支持带参数的注解和可选的 public 修饰符。
    methods = re.findall(
        r"@Test\s*(?:\([^)]*\)\s*)?(?:public\s+)?void\s+([A-Za-z_][\w]*)\s*\(",
        java_code,
        flags=re.MULTILINE,
    )
    return methods


def infer_package_from_target_file(target_file: str) -> str:
    # 从目标 Java 文件中推断包名，通过解析 package 声明，如果没有则返回空字符串。
    with open(target_file, "r", encoding="utf-8", errors="ignore") as file_obj:
        text = file_obj.read()
    return extract_package_name(text)


def ensure_package_declaration(java_code: str, package_name: str) -> str:
    # 确保生成的 Java 代码包含正确的 package 声明，如果已经存在则不修改，否则添加到代码顶部。
    if not package_name:
        return java_code
    if extract_package_name(java_code):
        return java_code
    return f"package {package_name};\n\n{java_code.lstrip()}"


def resolve_test_file_path(project_root: str, package_name: str, class_name: str) -> str:
    # 根据包名和类名解析生成测试文件的路径，通常位于 src/test/ 下对应的包目录中，如果没有包则直接放在 src/test/。
    if package_name:
        package_path = package_name.replace(".", os.sep)
        return os.path.join(project_root, "src", "test", package_path, f"{class_name}.java")
    return os.path.join(project_root, "src", "test", f"{class_name}.java")


def write_generated_test_file(project_root: str, java_code: str) -> tuple[str, str, str, str | None]:
    # 将生成的 Java 代码写入项目中适当的位置，返回测试文件路径、包名、类名和之前的文件内容（如果存在）。
    package_name = extract_package_name(java_code)
    class_name = extract_public_class_name(java_code)
    test_file_path = resolve_test_file_path(project_root, package_name, class_name)

    previous_content: str | None = None
    if os.path.exists(test_file_path):
        with open(test_file_path, "r", encoding="utf-8", errors="ignore") as file_obj:
            previous_content = file_obj.read()

    os.makedirs(os.path.dirname(test_file_path), exist_ok=True)
    with open(test_file_path, "w", encoding="utf-8") as file_obj:
        file_obj.write(java_code.rstrip() + "\n")

    return test_file_path, package_name, class_name, previous_content


def run_command(command: list[str], cwd: str) -> CommandResult:
    # 在指定目录下运行命令并捕获结果，返回 CommandResult 对象。
    proc = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    return CommandResult(
        command=command,
        exit_code=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


def parse_coverage_summary(coverage_xml_path: str, target_class_fqn: str) -> CoverageSummary | None:
    # 从 Cobertura 生成的 coverage.xml 中解析指定目标类的覆盖率摘要，如果文件不存在或类未找到则返回 None。
    if not os.path.isfile(coverage_xml_path):
        return None

    import xml.etree.ElementTree as ET

    root = ET.parse(coverage_xml_path).getroot()
    target_cls = None
    for cls_node in root.findall('.//class'):
        if cls_node.get('name') == target_class_fqn:
            target_cls = cls_node
            break
    if target_cls is None:
        return None

    executable_lines: set[int] = set()
    covered_lines: set[int] = set()
    total_conditions = 0
    covered_conditions = 0

    for line in target_cls.findall('.//line'):
        num = int(line.get('number', '0'))
        hits = int(line.get('hits', '0'))
        executable_lines.add(num)
        if hits > 0:
            covered_lines.add(num)

        cond_cov = line.get('condition-coverage')
        if cond_cov and '(' in cond_cov and '/' in cond_cov and ')' in cond_cov:
            # format example: 50% (1/2)
            fraction = cond_cov.split('(')[-1].split(')')[0]
            covered_s, total_s = fraction.split('/')
            covered_conditions += int(covered_s)
            total_conditions += int(total_s)

    total_line_count = len(executable_lines)
    covered_line_count = len(covered_lines)
    line_cov_pct = (covered_line_count / total_line_count * 100.0) if total_line_count else 0.0
    cond_cov_pct = (covered_conditions / total_conditions * 100.0) if total_conditions else 0.0

    return CoverageSummary(
        target_class=target_class_fqn,
        total_executable_lines=total_line_count,
        covered_lines=covered_line_count,
        line_coverage_percent=round(line_cov_pct, 1),
        total_conditions=total_conditions,
        covered_conditions=covered_conditions,
        condition_coverage_percent=round(cond_cov_pct, 1),
        uncovered_lines=sorted(executable_lines - covered_lines),
    )


def _write_suite_archive_for_generated_test(run_dir: str, package_name: str, class_name: str, java_code: str) -> str:
    # 将生成的测试代码写入临时目录中的适当位置，并创建一个 tar.bz2 格式的归档，返回归档路径。
    suite_src_dir = os.path.join(run_dir, 'suite_src')
    if package_name:
        rel_dir = package_name.replace('.', os.sep)
    else:
        rel_dir = ''
    target_dir = os.path.join(suite_src_dir, rel_dir)
    os.makedirs(target_dir, exist_ok=True)

    source_file = os.path.join(target_dir, f"{class_name}.java")
    with open(source_file, 'w', encoding='utf-8') as file_obj:
        file_obj.write(java_code.rstrip() + '\n')

    archive_path = os.path.join(run_dir, 'generated_suite.tar.bz2')
    base_dir = os.path.join(run_dir, 'suite_src')
    subprocess.run(['tar', '-cjf', archive_path, '-C', base_dir, '.'], check=True)
    return archive_path


def _read_failing_tests(project_root: str) -> str:
    # 从项目根目录下的 failing_tests 文件中读取内容，如果文件不存在则返回空字符串。
    path = os.path.join(project_root, 'failing_tests')
    if not os.path.isfile(path):
        return ''
    with open(path, 'r', encoding='utf-8', errors='ignore') as file_obj:
        return file_obj.read().strip()


def _save_run_report(run_dir: str, report: dict[str, Any]) -> str:
    # 将运行结果报告保存为 JSON 文件，返回保存的文件路径。
    out_path = os.path.join(run_dir, 'defects4j_run_report.json')
    with open(out_path, 'w', encoding='utf-8') as file_obj:
        json.dump(report, file_obj, ensure_ascii=False, indent=2)
    return out_path


class Defects4jRunner:
    # Defects4J 运行器，负责将 LLM 输出的测试代码写入项目、运行覆盖率命令、解析结果并进行清理。

    def __init__(self, defects4j_bin: str, auto_clean: bool = True, temp_root: str | None = None):
        self.defects4j_bin = defects4j_bin
        self.auto_clean = auto_clean
        self.temp_root = temp_root

    def run(self, llm_output_text: str, target_file: str, project_root: str) -> Defects4jRunResult:
        """Write generated test, run Defects4J coverage, parse report, and cleanup."""
        run_dir = create_run_temp_dir(self.temp_root)

        java_code = extract_java_code_block(llm_output_text)
        target_package = infer_package_from_target_file(target_file)
        java_code = ensure_package_declaration(java_code, target_package)

        artifact_state = snapshot_artifact_state(project_root)
        file_content_snapshot = snapshot_file_contents(project_root, MUTABLE_FILE_PATHS)
        test_file_path, package_name, class_name, previous_test_content = write_generated_test_file(project_root, java_code)
        test_class = f"{package_name}.{class_name}" if package_name else class_name

        target_class_fqn = extract_target_class_fqn(target_file)
        instrument_file = os.path.join(run_dir, 'instrument_classes.txt')
        with open(instrument_file, 'w', encoding='utf-8') as file_obj:
            file_obj.write(target_class_fqn + '\n')

        cleaned_paths: list[str] = []
        coverage_result = CommandResult(command=[], exit_code=1, stdout='', stderr='coverage command not executed')
        coverage_summary: CoverageSummary | None = None
        failing_tests_content = ''

        try:
            suite_archive = _write_suite_archive_for_generated_test(run_dir, package_name, class_name, java_code)
            coverage_cmd = [
                self.defects4j_bin,
                'coverage',
                '-w',
                project_root,
                '-s',
                suite_archive,
                '-i',
                instrument_file,
            ]
            coverage_result = run_command(coverage_cmd, cwd=project_root)
            failing_tests_content = _read_failing_tests(project_root)

            coverage_xml_path = os.path.join(project_root, 'coverage.xml')
            if os.path.isfile(coverage_xml_path):
                shutil.copy2(coverage_xml_path, os.path.join(run_dir, 'coverage.xml'))

            coverage_summary = parse_coverage_summary(coverage_xml_path, target_class_fqn)
        finally:
            if self.auto_clean:
                cleaned_paths = cleanup_generated_run(
                    project_root=project_root,
                    artifact_state=artifact_state,
                    test_file_path=test_file_path,
                    previous_test_content=previous_test_content,
                    file_content_snapshot=file_content_snapshot,
                )

        status = 'success'
        if coverage_result.exit_code != 0:
            status = 'coverage_command_failed'
        elif failing_tests_content:
            status = 'test_execution_failed'
        elif coverage_summary is None:
            status = 'coverage_report_missing'

        report = {
            'status': status,
            'target_file': target_file,
            'target_class': target_class_fqn,
            'test_file_path': test_file_path,
            'test_class': test_class,
            'coverage_exit_code': coverage_result.exit_code,
            'failing_tests': failing_tests_content,
            'coverage_summary': (
                {
                    'total_executable_lines': coverage_summary.total_executable_lines,
                    'covered_lines': coverage_summary.covered_lines,
                    'line_coverage_percent': coverage_summary.line_coverage_percent,
                    'total_conditions': coverage_summary.total_conditions,
                    'covered_conditions': coverage_summary.covered_conditions,
                    'condition_coverage_percent': coverage_summary.condition_coverage_percent,
                    'uncovered_lines': coverage_summary.uncovered_lines,
                }
                if coverage_summary
                else None
            ),
            'auto_clean_enabled': self.auto_clean,
            'cleaned_paths': cleaned_paths,
            'stdout': coverage_result.stdout,
            'stderr': coverage_result.stderr,
        }
        report_json_path = _save_run_report(run_dir, report)

        return Defects4jRunResult(
            status=status,
            test_file_path=test_file_path,
            test_class=test_class,
            coverage_command_result=coverage_result,
            failing_tests_content=failing_tests_content,
            coverage_summary=coverage_summary,
            temp_result_dir=run_dir,
            report_json_path=report_json_path,
            auto_clean_enabled=self.auto_clean,
            cleaned_paths=cleaned_paths,
        )


def apply_and_run_generated_test(
    llm_output_text: str,
    target_file: str,
    project_root: str,
    defects4j_bin: str,
    auto_clean: bool = True,
) -> GeneratedTestRunResult:
    # 应用生成的测试代码，运行 Defects4J 的覆盖率命令，并返回一个包含执行结果和覆盖率摘要的 GeneratedTestRunResult 对象。
    java_code = extract_java_code_block(llm_output_text)
    target_package = infer_package_from_target_file(target_file)
    java_code = ensure_package_declaration(java_code, target_package)

    artifact_state = snapshot_artifact_state(project_root)
    file_content_snapshot = snapshot_file_contents(project_root, MUTABLE_FILE_PATHS)
    test_file_path, package_name, class_name, previous_test_content = write_generated_test_file(project_root, java_code)
    test_methods = extract_test_method_names(java_code)

    cleaned_paths: list[str] = []
    try:
        compile_result = run_command([defects4j_bin, "compile", "-w", project_root], cwd=project_root)

        full_class_name = f"{package_name}.{class_name}" if package_name else class_name
        test_results: list[CommandResult] = []

        if compile_result.exit_code == 0 and test_methods:
            for method_name in test_methods:
                test_cmd = [
                    defects4j_bin,
                    "test",
                    "-w",
                    project_root,
                    "-t",
                    f"{full_class_name}::{method_name}",
                ]
                test_results.append(run_command(test_cmd, cwd=project_root))
    finally:
        if auto_clean:
            cleaned_paths = cleanup_generated_run(
                project_root=project_root,
                artifact_state=artifact_state,
                test_file_path=test_file_path,
                previous_test_content=previous_test_content,
                file_content_snapshot=file_content_snapshot,
            )

    return GeneratedTestRunResult(
        test_file_path=test_file_path,
        package_name=package_name,
        class_name=class_name,
        test_methods=test_methods,
        compile_result=compile_result,
        test_results=test_results,
        auto_clean_enabled=auto_clean,
        cleaned_paths=cleaned_paths,
    )


def summarize_run_result(run_result: GeneratedTestRunResult) -> dict[str, Any]:
    # 将 GeneratedTestRunResult 对象转换为一个简化的字典摘要，包含测试文件路径、测试类、测试方法列表、编译结果和测试结果的退出码，以及清理信息。
    full_class_name = (
        f"{run_result.package_name}.{run_result.class_name}"
        if run_result.package_name
        else run_result.class_name
    )

    return {
        "test_file_path": run_result.test_file_path,
        "test_class": full_class_name,
        "test_methods": list(run_result.test_methods),
        "compile_exit_code": run_result.compile_result.exit_code,
        "test_exit_codes": [res.exit_code for res in run_result.test_results],
        "auto_clean_enabled": run_result.auto_clean_enabled,
        "cleaned_paths": list(run_result.cleaned_paths),
    }
