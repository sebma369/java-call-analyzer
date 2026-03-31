# TestGen Context Snapshot (Current State)

本文件是面向后续开发的精简上下文，只保留当前结构与职责，不记录历史改造过程。

## 1) 项目目标（当前）

给定目标 Java 文件，执行以下流水线：

1. 静态分析（调用链 + 执行路径）
2. 组装结构化 Prompt（文本 + JSON 载荷）
3. 调用 LLM 生成测试代码
4. 将生成测试应用到 Defects4J 项目并执行 coverage
5. 解析覆盖率并输出报告
6. 自动清理并尽量恢复工作区

## 2) 关键目录

- `src/`：核心实现
- `tests/`：单元测试
- `scripts/`：便捷启动脚本
- `tmp/`：运行期临时产物（Prompt、LLM 输出、每次执行报告）

## 3) 代码入口与执行流

### 3.1 入口

- `src/__main__.py`
  - 作用：`python -m src` 时调用 `src.cli.main()`。
- `scripts/run.py`
  - 作用：脚本入口，手工补充 `sys.path` 后调用 `src.cli.main()`。
- `src/cli.py`
  - 作用：统一 CLI 编排，支持模式：
    - `call-chain`
    - `execution-path`
    - `structured-prompt`
    - `llm-generate`

### 3.2 主流程（llm-generate）

`src/cli.py` 中顺序：

1. `build_structured_prompt(...)` 生成结构化上下文
2. `call_llm_with_prompt(...)` 调用模型生成测试
3. `save_llm_output_text(...)` 保存 LLM 返回
4. 若开启 `--apply-generated-test`：
   - `Defects4jRunner.run(...)` 提取/写入测试
   - 调用 `defects4j coverage`
   - 解析 `coverage.xml`
   - 保存 `tmp/run_*/defects4j_run_report.json`
   - `auto_clean` 时回滚/清理产物

## 4) src 文件级说明（逐文件）

### `src/__init__.py`
- 内容：包版本声明（`__version__ = "0.1.0"`）。
- 作用：标记包与基础元信息。

### `src/__main__.py`
- 内容：导入并执行 `main()`。
- 作用：模块化运行入口。

### `src/utils.py`
- 内容：通用文件与 Java AST 辅助函数：
  - `get_project_root`
  - `find_java_files`
  - `get_package`
  - `type_name`
  - `full_class_name`
- 作用：被分析模块复用的基础工具。

### `src/cli.py`
- 内容：参数解析、模式分发、打印结果、串联分析/Prompt/LLM/Runner。
- 作用：整个项目的统一命令入口与调度层。

### `src/analysis/__init__.py`
- 内容：分析子包标记文件。
- 作用：组织分析相关模块。

### `src/analysis/java_parser.py`
- 内容：基于 `javalang` 扫描仓库 Java 文件，抽取：
  - 方法定义（`method_defs`）
  - 调用者映射（`callers`）
  - 被调用者映射（`callees`）
  - 目标文件方法（`collect_target_methods`）
- 作用：调用链分析与 Prompt 构建的数据来源。

### `src/analysis/call_chain.py`
- 内容：`build_call_chains(...)`，对目标方法做向上/向下 BFS。
- 作用：生成“谁调用我 / 我调用谁”的链路集合。

### `src/analysis/execution_paths.py`
- 内容：
  - `CFGBuilder`：把方法体近似建成控制流图（NetworkX）
  - `analyze_execution_paths(...)`：枚举 entry 到 exit 的简单路径
- 作用：给 Prompt 提供路径覆盖视角。

### `src/prompting/__init__.py`
- 内容：Prompt 子包标记文件。
- 作用：组织 Prompt 相关模块。

### `src/prompting/structured_prompt.py`
- 内容：
  - 数据结构：`PromptSourceInfo`、`PromptBuildResult`
  - 构建器：`StructuredPromptBuilder`
  - 便捷函数：`build_structured_prompt`
  - 轮次编排：`compose_round_prompt`
  - 文件输出：`save_prompt_text/json` 与默认路径函数
- 作用：把分析结果变成可读文本 Prompt 与可机读 JSON Payload。

### `src/integration/__init__.py`
- 内容：集成层子包标记文件。
- 作用：组织第三方接口集成代码。

### `src/integration/openai_client.py`
- 内容：
  - 配置结构：`LLMConfig`
  - 请求构造：`build_chat_payload`
  - 响应提取：`extract_response_text`
  - 调用入口：`call_llm_with_prompt`
  - 输出落盘：`save_llm_output_text`
- 作用：统一 LLM API 访问层。
- 备注：当前文件包含默认 endpoint/api_key/model 常量，后续建议改为环境变量注入。

### `src/runners/__init__.py`
- 内容：Runner 子包标记文件。
- 作用：组织执行器模块。

### `src/runners/defects4j_runner.py`
- 内容：
  - 代码提取/解析：`extract_java_code_block`、`extract_package_name`、`extract_public_class_name`
  - 文件写入：`write_generated_test_file`、`resolve_test_file_path`
  - 命令执行：`run_command`
  - 覆盖率解析：`parse_coverage_summary`
  - 产物快照与恢复：`snapshot_artifact_state`、`snapshot_file_contents`、`cleanup_generated_run`
  - 主执行器：`Defects4jRunner.run`
  - 兼容接口：`apply_and_run_generated_test`、`summarize_run_result`
- 作用：Defects4J 一次性执行（写测试 -> coverage -> 解析 -> 报告 -> 清理）。

## 5) tests 文件级说明（逐文件）

### `tests/__init__.py`
- 内容：测试包标记。
- 作用：组织测试模块。

### `tests/test_analyzer.py`
- 覆盖：`java_parser`、`call_chain`、`execution_paths`。
- 作用：验证静态分析核心行为。

### `tests/test_prompt_builder.py`
- 覆盖：`structured_prompt` 数据结构、构建、round payload、txt/json 落盘。
- 作用：验证 Prompt 产物结构和输出路径策略（`tmp/prompts`）。

### `tests/test_llm_client.py`
- 覆盖：payload 形状、响应提取、调用流程（monkeypatch）、输出落盘。
- 作用：验证 LLM 集成层行为。

### `tests/test_test_generation_runner.py`
- 覆盖：测试代码块提取、包名/类名/测试方法提取、写入路径、清理恢复逻辑。
- 作用：验证执行器辅助函数和恢复机制。

### `tests/test_data/A.java`
- 作用：调用链测试输入样例。

### `tests/test_data/B.java`
- 作用：调用链 + Prompt 测试输入样例。

### `tests/test_data/ExecutionPathTest.java`
- 作用：执行路径分析测试输入样例。

## 6) scripts 文件级说明

### `scripts/run.py`
- 内容：可直接执行的 Python 启动脚本。
- 作用：简化本地手动调用。

## 7) 临时产物与报告约定

- Prompt 文本：`tmp/prompts/*_structured_prompt_*.txt`
- Prompt JSON：`tmp/prompts/*_structured_prompt_*.json`
- LLM 输出：`tmp/prompts/*_llm_output_*.txt`
- Defects4J 单次运行目录：`tmp/run_*/`
  - `defects4j_run_report.json`
  - 复制出的 `coverage.xml`（若存在）

## 8) 外部依赖与运行条件

- Python：3.10+
- 依赖库：`javalang`、`networkx`、`openai`、`pytest`
- 外部工具：Defects4J（默认路径由 CLI 参数 `--defects4j-bin` 控制）

## 9) 已知边界（当前）

- `execution_paths.py` 为 AST 级近似 CFG，不等价于 Java 字节码真实执行路径。
- 调用关系解析是静态近似（按名称匹配），无法完整解决动态分派等语义。
- 某些 Defects4J 项目可能出现测试运行依赖缺失（例如 hamcrest），表现为测试执行失败但流程本身仍完成并产出报告。

