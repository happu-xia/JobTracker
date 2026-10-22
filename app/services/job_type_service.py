"""自定义职位类型服务。

用户可自由增删改自己的分类维度（颜色直接决定图表配色），
删除前必须做引用检查：被投递记录引用时只允许「停用」，不允许删除。
"""

from __future__ import annotations

import re

from sqlalchemy import func, select

from app.extensions import db
from app.models.application import Application
from app.models.job_type import JobType
from app.utils.errors import ConflictError, NotFoundError, ValidationError

COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")
DEFAULT_COLOR = "#0d6efd"


def _clean(data: dict) -> dict:
    name = (data.get("name") or "").strip()
    if not name:
        raise ValidationError("类型名称不能为空")
    if len(name) > 50:
        raise ValidationError("类型名称不能超过 50 个字符")

    color = (data.get("color") or DEFAULT_COLOR).strip()
    if not COLOR_PATTERN.match(color):
        raise ValidationError("颜色必须是 #RRGGBB 格式的十六进制值")

    try:
        sort_order = int(data.get("sort_order") or 0)
    except (TypeError, ValueError):
        raise ValidationError("排序必须是整数") from None
    if sort_order < 0:
        raise ValidationError("排序不能为负数")

    is_active = data.get("is_active")
    return {
        "name": name,
        "color": color.lower(),
        "sort_order": sort_order,
        "is_active": True if is_active is None else bool(is_active),
    }


def usage_counts(user_id: int) -> dict[int, int]:
    stmt = (
        select(Application.job_type_id, func.count(Application.id))
        .where(Application.user_id == user_id, Application.job_type_id.is_not(None))
        .group_by(Application.job_type_id)
    )
    return {row[0]: row[1] for row in db.session.execute(stmt)}


def list_with_usage(user_id: int) -> list[tuple[JobType, int]]:
    """一次查询拿类型，一次查询拿引用数，共 2 条 SQL（不做 per-row count）。"""
    types = (
        db.session.execute(
            select(JobType)
            .where(JobType.user_id == user_id)
            .order_by(JobType.sort_order, JobType.id)
        )
        .scalars()
        .all()
    )
    usage = usage_counts(user_id)
    return [(item, usage.get(item.id, 0)) for item in types]


def active_types(user_id: int) -> list[JobType]:
    return (
        db.session.execute(
            select(JobType)
            .where(JobType.user_id == user_id, JobType.is_active.is_(True))
            .order_by(JobType.sort_order, JobType.id)
        )
        .scalars()
        .all()
    )


def get_or_404(user_id: int, type_id: int) -> JobType:
    item = db.session.execute(
        select(JobType).where(JobType.id == type_id, JobType.user_id == user_id)
    ).scalar_one_or_none()
    if item is None:
        raise NotFoundError("职位类型不存在，或你没有权限访问")
    return item


def _ensure_unique_name(user_id: int, name: str, *, exclude_id: int | None = None) -> None:
    stmt = select(JobType.id).where(JobType.user_id == user_id, JobType.name == name)
    if exclude_id is not None:
        stmt = stmt.where(JobType.id != exclude_id)
    if db.session.execute(stmt).first() is not None:
        raise ConflictError(f"已存在同名职位类型「{name}」")


def _next_sort_order(user_id: int) -> int:
    current = db.session.execute(
        select(func.max(JobType.sort_order)).where(JobType.user_id == user_id)
    ).scalar()
    return 0 if current is None else int(current) + 10


def create(user_id: int, data: dict) -> JobType:
    payload = _clean(data)
    _ensure_unique_name(user_id, payload["name"])
    if not payload["sort_order"]:
        payload["sort_order"] = _next_sort_order(user_id)

    item = JobType(user_id=user_id, **payload)
    db.session.add(item)
    db.session.commit()
    return item


def update(item: JobType, data: dict) -> JobType:
    payload = _clean(data)
    _ensure_unique_name(item.user_id, payload["name"], exclude_id=item.id)
    for key, value in payload.items():
        setattr(item, key, value)
    db.session.commit()
    return item


def toggle(item: JobType) -> JobType:
    item.is_active = not item.is_active
    db.session.commit()
    return item


def move(item: JobType, direction: int) -> JobType:
    """与相邻类型交换 sort_order（比拖拽实现简单，但功能等价且可键盘操作）。"""
    if direction not in (-1, 1):
        raise ValidationError("移动方向不合法")

    siblings = (
        db.session.execute(
            select(JobType)
            .where(JobType.user_id == item.user_id)
            .order_by(JobType.sort_order, JobType.id)
        )
        .scalars()
        .all()
    )
    index = next((i for i, obj in enumerate(siblings) if obj.id == item.id), None)
    if index is None:
        raise NotFoundError("职位类型不存在")
    target_index = index + direction
    if target_index < 0 or target_index >= len(siblings):
        return item

    # 先把 sort_order 归一化为 0,10,20...，再交换相邻两项，
    # 避免历史数据里 sort_order 重复/稀疏导致「换了等于没换」
    for order, obj in enumerate(siblings):
        obj.sort_order = order * 10
    left, right = siblings[index], siblings[target_index]
    left.sort_order, right.sort_order = right.sort_order, left.sort_order

    db.session.commit()
    return item


def delete(item: JobType) -> None:
    used = db.session.execute(
        select(func.count(Application.id)).where(Application.job_type_id == item.id)
    ).scalar_one()
    if used:
        raise ConflictError(
            f"该类型已被 {used} 条投递记录引用，无法删除。可以改成「停用」，历史记录仍能正常显示"
        )
    db.session.delete(item)
    db.session.commit()
