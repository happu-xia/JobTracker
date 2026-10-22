"""权限与查询辅助。

数据隔离不能靠「每个查询记得加 user_id」这种自觉，而要收敛成唯一入口：
本模块的 ``owned_or_404`` 是所有单条读写操作的必经之路。
"""

from __future__ import annotations

from typing import TypeVar

from flask import request
from flask_login import current_user
from sqlalchemy import select

from app.extensions import db
from app.utils.errors import NotFoundError

T = TypeVar("T")


def owned_or_404(model: type[T], obj_id: int, *, user_field: str = "user_id", pk: str = "id") -> T:
    """按 id + 当前用户取对象；不存在或不属于当前用户统一抛 404。

    选择 404 而不是 403：403 会泄露「该 id 存在但不属于你」这一信息，
    攻击者可据此枚举他人数据规模。
    """
    stmt = select(model).where(
        getattr(model, pk) == obj_id,
        getattr(model, user_field) == current_user.id,
    )
    obj = db.session.execute(stmt).scalar_one_or_none()
    if obj is None:
        raise NotFoundError("记录不存在，或你没有权限访问")
    return obj


def paginate(stmt, *, per_page: int | None = None):
    """统一分页入口：非法 page 不报错，回落到第 1 页。"""
    from flask import current_app

    page = request.args.get("page", 1, type=int) or 1
    per_page = per_page or current_app.config["ITEMS_PER_PAGE"]
    page = max(page, 1)
    return db.paginate(stmt, page=page, per_page=per_page, error_out=False)


def filter_args(*, drop: tuple[str, ...] = ("page",)) -> dict[str, str]:
    """收集当前查询参数（供分页链接保留筛选条件）。"""
    return {k: v for k, v in request.args.items() if k not in drop and v != ""}
