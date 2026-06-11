"""pytest 配置：把 python/ 加入 sys.path，使测试可导入项目模块。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYDIR = os.path.join(ROOT, "python")
if PYDIR not in sys.path:
    sys.path.insert(0, PYDIR)
