"""架构边界测试：Core 不直接依赖 Woo / Odoo Adapter 细节。"""

from __future__ import annotations

from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"


def test_core_does_not_import_woo_or_odoo_adapter() -> None:
    """扫描 app 包源码，禁止任何 `import` / `from ... import` 引用 woo / odoo。

    Woo / Odoo 的投影与调用由 Integration 层（ISSUE-0107 等）负责；
    Core 只发布领域事件（outbox），不 import Adapter 细节。
    """
    offenders: list[str] = []
    for path in APP_DIR.rglob("*.py"):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if not (stripped.startswith("import ") or stripped.startswith("from ")):
                continue
            if "woo" in stripped.lower() or "odoo" in stripped.lower():
                offenders.append(f"{path.name}:{lineno}: {stripped}")

    assert offenders == [], f"Core 不应 import Woo/Odoo Adapter 细节：{offenders}"


def test_outbox_model_registered_in_metadata() -> None:
    from app.db import Base

    assert "domain_events" in Base.metadata.tables
