"""pytest 根配置：将 src 目录加入模块搜索路径。

这样测试用例可直接 ``from github_service import ...``，
无需把 src 安装为包，也无需在每个测试里手动改 sys.path。
"""

import pathlib
import sys

# 把 <项目根>/src 插入到模块搜索路径最前面。
_SRC_DIR = pathlib.Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(_SRC_DIR))
