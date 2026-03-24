#!/usr/bin/env python3
"""
Java Call Analyzer - 运行脚本

直接运行此脚本启动 Java 调用链分析工具。

用法:
    python scripts/run.py /path/to/repo /path/to/target/File.java
"""

import sys
import os

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from java_call_analyzer.cli import main

if __name__ == "__main__":
    main()