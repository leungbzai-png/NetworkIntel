"""测试共用：把 python/ 加入 sys.path（供无 pytest 的手动运行器或独立导入使用）。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYDIR = os.path.join(ROOT, "python")
if PYDIR not in sys.path:
    sys.path.insert(0, PYDIR)
