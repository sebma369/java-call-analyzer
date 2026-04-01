#!/usr/bin/env python3
"""
Java TestGen - 运行脚本

直接运行此脚本启动 Java 测试生成工具。

"""

import sys
import os

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.cli import main

if __name__ == "__main__":
    main()