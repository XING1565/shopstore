"""请求身份（principal）与鉴权依赖。

阶段 1 无独立 IAM / OAuth，采用轻量 header 身份模型，供 Woo 桥接插件（以买家
身份）与运营后台（operator）调用；后续可替换为 JWT / OIDC 而无需改动领域层。

Header 约定：

- ``X-Actor-Role``：``operator``（运营）或 ``retailer``（买家）；缺省为匿名。
- ``X-Retailer-Id``：当 role=retailer 时的买家主键（UUID v4）。
- ``X-Operator-Name``：可选，运营动作的审计人姓名。

鉴权语义（PRD §7）：

- 未认证买家（pending / rejected / suspended）不可见完整批发价与 MOQ，不能下单。
- 认证买家（approved）可见批发价 / MOQ、可下单。
- 运营（operator）可审核买家、维护商品、查看全部。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.db import get_session
from app.errors import AppError
from app.models import Retailer
from app.models.enums import RetailerStatus

__all__ = [
    "Principal",
    "SessionDep",
    "PrincipalDep",
    "get_principal",
    "load_retailer",
    "require_operator",
    "require_approved_retailer",
    "can_view_pricing",
]


class Principal:
    """一次请求的调用方身份。"""

    def __init__(
        self,
        role: str,
        *,
        retailer_id: str | None = None,
        operator_name: str | None = None,
    ) -> None:
        self.role = role  # "operator" | "retailer" | "anonymous"
        self.retailer_id = retailer_id
        self.operator_name = operator_name

    @property
    def is_operator(self) -> bool:
        return self.role == "operator"

    @property
    def is_retailer(self) -> bool:
        return self.role == "retailer"

    @property
    def is_anonymous(self) -> bool:
        return self.role == "anonymous"


def get_principal(
    x_actor_role: Annotated[str | None, Header(convert_underscores=True)] = None,
    x_retailer_id: Annotated[str | None, Header(convert_underscores=True)] = None,
    x_operator_name: Annotated[str | None, Header(convert_underscores=True)] = None,
) -> Principal:
    role = (x_actor_role or "").strip().lower()
    if role == "retailer":
        if not x_retailer_id:
            raise AppError(401, "unauthorized", "买家身份缺失：需提供 X-Retailer-Id")
        return Principal("retailer", retailer_id=x_retailer_id)
    if role == "operator":
        return Principal("operator", operator_name=x_operator_name)
    return Principal("anonymous")


SessionDep = Annotated[Session, Depends(get_session)]
PrincipalDep = Annotated[Principal, Depends(get_principal)]


def load_retailer(session: Session, principal: Principal) -> Retailer:
    """按 ``X-Retailer-Id`` 加载买家；不存在则 401。"""
    retailer = session.get(Retailer, principal.retailer_id)
    if retailer is None:
        raise AppError(401, "unauthorized", "买家身份无效或不存在")
    return retailer


def require_operator(principal: Principal) -> None:
    """仅运营可执行。"""
    if not principal.is_operator:
        raise AppError(403, "forbidden", "仅运营可执行此操作")


def require_approved_retailer(session: Session, principal: Principal) -> Retailer:
    """下单要求：已认证（approved）买家。"""
    if not principal.is_retailer:
        raise AppError(403, "forbidden", "仅买家可下单")
    retailer = load_retailer(session, principal)
    if retailer.status is not RetailerStatus.approved:
        raise AppError(
            403,
            "forbidden",
            "买家未通过认证，不能下单",
        )
    return retailer


def can_view_pricing(session: Session, principal: Principal) -> bool:
    """是否可查看批发价 / MOQ：运营或已认证（approved）买家。"""
    if principal.is_operator:
        return True
    if principal.is_retailer:
        retailer = session.get(Retailer, principal.retailer_id)
        return retailer is not None and retailer.status is RetailerStatus.approved
    return False
