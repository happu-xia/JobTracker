"""面试服务：登记轮次、更新结果、与投递状态联动。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.extensions import db
from app.models.application import Application
from app.models.interview import Interview
from app.utils.constants import RESULT_LABELS, ROUND_LABELS, STATUS_APPLIED, STATUS_VIEWED
from app.utils.dtime import now_local
from app.utils.errors import ConflictError, NotFoundError, ValidationError


def _parse_dt(value) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip())
        except ValueError:
            raise ValidationError("面试时间格式不正确") from None
    raise ValidationError("请填写面试时间")


def _clean(data: dict) -> dict:
    round_name = (data.get("round") or "first").strip()
    if round_name not in ROUND_LABELS:
        raise ValidationError("面试轮次不合法")

    result = (data.get("result") or "pending").strip()
    if result not in RESULT_LABELS:
        raise ValidationError("面试结果不合法")

    return {
        "round": round_name,
        "scheduled_at": _parse_dt(data.get("scheduled_at")),
        "result": result,
        "feedback": (data.get("feedback") or "").strip() or None,
    }


def get_or_404(user_id: int, interview_id: int) -> Interview:
    item = db.session.execute(
        select(Interview).where(Interview.id == interview_id, Interview.user_id == user_id)
    ).scalar_one_or_none()
    if item is None:
        raise NotFoundError("面试记录不存在，或你没有权限访问")
    return item


def _sync_application(app: Application) -> None:
    """有面试记录 ⇒ 至少走到「面试中」阶段。

    这一步保证 has_interview、max_stage、status 三者口径一致，
    否则会出现「有面试记录但漏斗里没算作面试」的对账问题。
    """
    app.max_stage = max(app.max_stage or 1, 3)
    if app.status in (STATUS_APPLIED, STATUS_VIEWED):
        app.status = "interviewing"
    if app.first_viewed_at is None:
        app.first_viewed_at = now_local()
        app.response_days = max((app.first_viewed_at.date() - app.applied_at.date()).days, 0)


def create(app: Application, data: dict) -> Interview:
    payload = _clean(data)

    dup = db.session.execute(
        select(Interview.id).where(
            Interview.application_id == app.id, Interview.round == payload["round"]
        )
    ).first()
    if dup is not None:
        raise ConflictError(
            f"该投递已经记录过「{ROUND_LABELS[payload['round']]}」，请直接编辑已有记录"
        )

    item = Interview(user_id=app.user_id, application_id=app.id, **payload)
    db.session.add(item)
    _sync_application(app)
    db.session.commit()
    return item


def update(item: Interview, data: dict) -> Interview:
    payload = _clean(data)

    if payload["round"] != item.round:
        dup = db.session.execute(
            select(Interview.id).where(
                Interview.application_id == item.application_id,
                Interview.round == payload["round"],
                Interview.id != item.id,
            )
        ).first()
        if dup is not None:
            raise ConflictError(f"该投递已经记录过「{ROUND_LABELS[payload['round']]}」")

    for key, value in payload.items():
        setattr(item, key, value)
    db.session.commit()
    return item


def delete(item: Interview) -> None:
    """删除面试记录不回退 max_stage —— 历史最高阶段是既成事实。"""
    db.session.delete(item)
    db.session.commit()
