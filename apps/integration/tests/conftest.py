"""pytest 配置：把 ``app/`` 加入导入路径，使 ``shopstore_integration`` 可被测试导入。"""

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
