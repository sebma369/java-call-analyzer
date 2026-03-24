# Java Call Analyzer

一个用于静态分析 Java 方法调用链的工具。

## 项目结构

```
TestGen/
├── src/
│   └── java_call_analyzer/
│       ├── __init__.py
│       ├── utils.py          # 工具函数
│       ├── parser.py         # Java 代码解析
│       ├── analyzer.py       # 调用链分析
│       └── cli.py            # 命令行接口
├── tests/
│   ├── __init__.py
│   ├── test_data/
│   │   ├── A.java
│   │   └── B.java
│   └── test_analyzer.py
├── pyproject.toml            # 项目配置
├── environment.yml           # Conda 环境
└── README.md
```

## 安装

### 使用 Conda 环境

```bash
conda env create -f environment.yml
conda activate testgen
```

### 安装包

```bash
pip install -e .
```

## 使用

### 命令行

```bash
java-call-analyzer /path/to/repo /path/to/target/File.java
```

### Python API

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
