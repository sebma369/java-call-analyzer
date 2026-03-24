# Java Call Analyzer

一个用于静态分析 Java 方法调用链的工具。

## 项目结构

```
TestGen/
├── java_call_analyzer/      # 主包目录
│   ├── __init__.py          # 包初始化
│   ├── __main__.py          # 模块入口
│   ├── analyzer.py          # 调用链分析逻辑
│   ├── cli.py               # 命令行接口
│   ├── parser.py            # Java 代码解析
│   └── utils.py             # 工具函数
├── scripts/                 # 脚本目录
│   └── run.py               # 运行脚本
├── tests/                   # 测试文件
│   ├── __init__.py
│   ├── test_analyzer.py
│   └── test_data/
│       ├── A.java
│       └── B.java
├── environment.yml          # Conda 环境配置
├── .gitignore               # Git 忽略文件
├── README.md                # 项目文档
└── .git/                    # Git 仓库
```

## 快速开始

### 1. 创建环境

```bash
conda env create -f environment.yml
conda activate testgen
```

### 2. 运行分析

```bash
# 使用运行脚本（推荐）
python scripts/run.py /path/to/repo /path/to/target/File.java

# 或者作为模块运行
python -m java_call_analyzer.cli /path/to/repo /path/to/target/File.java

# 示例
python scripts/run.py tests/test_data tests/test_data/B.java
```

## 输出

工具为目标文件中的每个方法输出：

- ↑ 向上调用链（谁调用了我）
- ↓ 向下调用链（我调用了谁）

## 运行测试

```bash
python -m pytest tests/
```

## 开发

### 代码格式化

```bash
pip install black isort
black java_call_analyzer/ tests/ scripts/
isort java_call_analyzer/ tests/ scripts/
```

### 代码检查

```bash
pip install flake8
flake8 java_call_analyzer/ tests/ scripts/
```

```python
from java_call_analyzer.parser import collect_methods_and_calls, collect_target_methods
from java_call_analyzer.analyzer import build_call_chains

# 解析仓库
method_defs, callers, callees = collect_methods_and_calls(repo_root)

# 收集目标方法
target_methods = collect_target_methods(target_file)

# 构建调用链
up_chains, down_chains = build_call_chains(target_methods, callers, callees)
```

## 输出

工具为目标文件中的每个方法输出：

- ↑ 向上调用链（谁调用了我）
- ↓ 向下调用链（我调用了谁）

## 运行测试

```bash
pytest
```

## 开发

### 代码格式化

```bash
black src/ tests/
isort src/ tests/
```

### 代码检查

```bash
flake8 src/ tests/
```
