# TestGen

用于 Java 测试生成与分析的工具链：静态分析 -> 结构化 Prompt -> LLM 生成 -> Defects4J 执行与覆盖率报告。

## 目录结构

```text
TestGen/
├── src/
│   ├── analysis/                # 静态分析层
│   │   ├── call_chain.py
│   │   ├── execution_paths.py
│   │   └── java_parser.py
│   ├── prompting/               # Prompt 组装层
│   │   └── structured_prompt.py
│   ├── integration/             # 外部服务集成层
│   │   └── openai_client.py
│   ├── runners/                 # 执行器层
│   │   └── defects4j_runner.py
│   ├── cli.py
│   ├── utils.py
│   └── (兼容包装模块)
├── tests/
├── scripts/
└── tmp/                         # 统一临时产物目录
		├── prompts/
		└── run_*/
```

说明：历史模块名（如 `parser.py`、`analyzer.py`）保留为兼容包装，内部转发到新结构，便于平滑迁移。

## 核心功能

1. `call-chain`：方法调用链分析（向上/向下）。
2. `execution-path`：方法执行路径分析（CFG）。
3. `structured-prompt`：构建结构化 Prompt（文本 + JSON）。
4. `llm-generate`：调用 LLM 生成测试代码。
5. `--apply-generated-test`：使用 `Defects4jRunner` 一次性执行生成测试并输出覆盖率摘要。

## 临时文件策略

所有临时输出统一写入 `tmp/`：

1. Prompt 与 LLM 输出：`tmp/prompts/`
2. 每轮执行报告：`tmp/run_<timestamp>/`
3. Defects4J 执行后的清理与还原默认开启，便于下一轮复用。

## 快速开始

```bash
conda env create -f environment.yml
conda activate testgen
python -m pytest tests/ -q
```

## 常用命令

调用链分析：

```bash
python -m src.cli --mode call-chain --repo tests/test_data tests/test_data/B.java
```

结构化 Prompt：

```bash
python -m src.cli --mode structured-prompt --repo tests/test_data tests/test_data/B.java
```

LLM 生成并在 Defects4J 执行：

```bash
python -m src.cli \
	--mode llm-generate \
	--repo /usr/src/defects4j/Cli-1b \
	--apply-generated-test \
	--test-project-root /usr/src/defects4j/Cli-1b \
	/usr/src/defects4j/Cli-1b/src/java/org/apache/commons/cli/GnuParser.java
```
