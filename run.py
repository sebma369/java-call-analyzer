#!/usr/bin/env python3
"""
Java Call Analyzer - 运行脚本

直接运行此脚本启动 Java 调用链分析工具。

用法:
    python run.py /path/to/repo /path/to/target/File.java
"""

import sys
import os

# 添加当前目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cli import main

if __name__ == "__main__":
    main()