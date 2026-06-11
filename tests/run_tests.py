"""
最小测试运行器（无需 pytest）。
用法：  python tests/run_tests.py
发现 tests/test_*.py 中的 test_* 函数并执行；任一失败退出码非零。
若已安装 pytest，推荐直接 `python -m pytest`。
"""
import importlib
import os
import sys
import traceback

# 控制台可能是非 UTF-8（如 cp932/cp936）；安全输出，避免 UnicodeEncodeError
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "python"))
sys.path.insert(0, HERE)  # 使 `import _bootstrap` 可用


def main() -> int:
    files = sorted(f for f in os.listdir(HERE)
                   if f.startswith("test_") and f.endswith(".py"))
    total = passed = failed = 0
    failures = []
    for fn in files:
        mod = importlib.import_module(fn[:-3])
        for name in sorted(dir(mod)):
            if not name.startswith("test_"):
                continue
            obj = getattr(mod, name)
            if not callable(obj):
                continue
            total += 1
            try:
                obj()
                passed += 1
                print(f"  PASS {fn}::{name}")
            except Exception as e:
                failed += 1
                failures.append((fn, name, traceback.format_exc()))
                print(f"  FAIL {fn}::{name}: {e}")

    print(f"\n{passed}/{total} passed, {failed} failed")
    for fn, name, tb in failures:
        print(f"\n--- {fn}::{name} ---\n{tb}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
