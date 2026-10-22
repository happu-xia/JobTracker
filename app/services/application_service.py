"""投递记录服务：状态机、阶段维护、多条件筛选。

这里是整个项目的业务核心，视图层调用它时不该再出现任何 if/else 业务判断。
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload, selectinload

from app.extensions import db
from app.models.application import Application
from app.models.company import Company
from app.models.interview import Interview
from app.models.job_type import JobType
from app.models.resume import Resume
from app.utils.constants import (
    CHANNEL_LABELS,
    STAGE_BY_STATUS,
    STATUS_TRANSITIONS,
    STATUS_APPLIED,
)
from app.utils.dtime import now_local, parse_date
from app.utils.errors import BusinessError, NotFoundError, ValidationError
from app.utils.url import InvalidUrlError, normalize_url


# ---------------------------------------------------------------- 校验与清洗
def _clean(user_id: int, data: dict, *, require_active_type: bool = False) -> dict:
    position = (data.get("position_name") or "").strip()
    if not position:
        raise ValidationError("职位名称不能为空")
    if len(position) > 120:
        raise ValidationError("职位名称不能超过 120 个字符")

    company_id = data.get("company_id")
    if not company_id:
        raise ValidationError("请选择所属企业")
    company = db.session.execute(
        select(Company).where(Company.id == company_id, Company.user_id == user_id)
    ).scalar_one_or_none()
    if company is None:
        raise ValidationError("所选企业不存在")

    channel = (data.get("channel") or "other").strip()
    if channel not in CHANNEL_LABELS:
        raise ValidationError("投递渠道不合法")

    status = (data.get("status") or STATUS_APPLIED).strip()
    if status not in STAGE_BY_STATUS and status not in ("rejected", "withdrawn"):
        raise ValidationError("投递状态不合法")

    job_type_id = data.get("job_type_id") or None
    if job_type_id:
        type_stmt = select(JobType).where(JobType.id == job_type_id, JobType.user_id == user_id)
        if require_active_type:
            type_stmt = type_stmt.where(JobType.is_active.is_(True))
        if db.session.execute(type_stmt).scalar_one_or_none() is None:
            raise ValidationError("所选职位类型不存在或已停用")
        job_type_id = int(job_type_id)

    resume_id = data.get("resume_id") or None
    if resume_id:
        resume = db.session.execute(
            select(Resume).where(Resume.id == resume_id, Resume.user_id == user_id)
        ).scalar_one_or_none()
        if resume is None:
            raise ValidationError("所选简历不存在")
        resume_id = int(resume_id)

    salary_min = data.get("salary_min")
    salary_max = data.get("salary_max")
    salary_min = int(salary_min) if salary_min not in (None, "") else None
    salary_max = int(salary_max) if salary_max not in (None, "") else None
    if salary_min is not None and salary_max is not None and salary_min > salary_max:
        raise ValidationError("薪资下限不能大于上限")
    if salary_min is not None and not (0 <= salary_min <= 1000):
        raise ValidationError("薪资请填写 0-1000 之间的数字（单位：K/月）")

    applied_at = data.get("applied_at") or now_local()
    if isinstance(applied_at, str):
        try:
            applied_at = datetime.fromisoformat(applied_at)
        except ValueError:
            raise ValidationError("投递时间格式不正确") from None
    applied_at = applied_at.replace(tzinfo=None)

    try:
        jd_url = normalize_url(data.get("jd_url"), max_length=500)
    except InvalidUrlError as exc:
        raise ValidationError(str(exc), field="jd_url") from exc

    notes = (data.get("notes") or "").strip() or None

    return {
        "company_id": int(company_id),
        "job_type_id": job_type_id,
        "resume_id": resume_id,
        "position_name": position,
        "channel": channel,
        "status": status,
        "applied_at": applied_at,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "jd_url": jd_url,
        "notes": notes,
    }


# ---------------------------------------------------------------- 阶段维护
def sync_stage(app: Application, new_status: str, *, when: datetime | None = None) -> None:
    """状态变化时同步 max_stage 与响应耗时。

    规则：max_stage 只增不减；rejected/withdrawn 是终态，不推进也不回退。
    这样「投递 → 查看 → 面试 → Offer」的漏斗在任意状态组合下都准确。
    """
    app.status = new_status
    stage = STAGE_BY_STATUS.get(new_status)
    if stage is not None:
        app.max_stage = max(app.max_stage or 1, stage)
        if stage >= 2 and app.first_viewed_at is None:
            app.first_viewed_at = when or now_local()
            delta = (app.first_viewed_at.date() - app.applied_at.date()).days
            app.response_days = max(delta, 0)


def transition(app: Application, new_status: str) -> Application:
    """按状态机流转，非法流转直接拒绝（而不是静默改库）。"""
    allowed = STATUS_TRANSITIONS.get(app.status, ())
    if new_status not in allowed:
        from app.utils.constants import status_label

        raise BusinessError(
            f"不能从「{status_label(app.status)}」直接变更为「{status_label(new_status)}」"
        )
    sync_stage(app, new_status)
    db.session.commit()
    return app


# ---------------------------------------------------------------- CRUD
def create(user_id: int, data: dict) -> Application:
    payload = _clean(user_id, data, require_active_type=True)
    status = payload.pop("status")
    app = Application(user_id=user_id, **payload)
    sync_stage(app, status)
    db.session.add(app)
    db.session.commit()
    return app


def update(app: Application, data: dict) -> Application:
    payload = _clean(app.user_id, data)
    status = payload.pop("status")
    for key, value in payload.items():
        setattr(app, key, value)
    sync_stage(app, status)
    db.session.commit()
    return app


def delete(app: Application) -> None:
    """删除投递：关联面试记录级联删除；简历文件不会被删（多对一解耦）。"""
    db.session.delete(app)
    db.session.commit()


def get_or_404(user_id: int, app_id: int) -> Application:
    stmt = (
        select(Application)
        .where(Application.id == app_id, Application.user_id == user_id)
        .options(
            joinedload(Application.company),
            joinedload(Application.job_type),
            joinedload(Application.resume),
            selectinload(Application.interviews),
        )
    )
    app = db.session.execute(stmt).unique().scalar_one_or_none()
    if app is None:
        raise NotFoundError("投递记录不存在，或你没有权限访问")
    return app


# ---------------------------------------------------------------- 查询
SORT_MAP = {
    "applied_desc": (Application.applied_at.desc(), Application.id.desc()),
    "applied_asc": (Application.applied_at.asc(), Application.id.asc()),
    "updated_desc": (Application.updated_at.desc(), Application.id.desc()),
    "company_asc": (Company.name.asc(), Application.id.desc()),
    "status_asc": (Application.status.asc(), Application.applied_at.desc()),
}


def list_applications(
    user_id: int,
    *,
    status: str | None = None,
    has_interview: str | None = None,
    job_type_id: int | None = None,
    channel: str | None = None,
    company_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    q: str | None = None,
    sort: str = "applied_desc",
    page: int = 1,
    per_page: int = 20,
):
    """列表页查询：7 个可组合筛选条件 + 排序 + 分页。

    性能要点：
    - 多对一关联用 joinedload（一次 JOIN 拿全，不做 1+N 次按行查询）；
    - 面试集合不在列表页加载，只用到 has_interview 派生列；
    - 所有条件都以 user_id 开头，命中复合索引。
    """
    stmt = (
        select(Application)
        .join(Company, Company.id == Application.company_id)
        .where(Application.user_id == user_id)
        .options(
            joinedload(Application.company),
            joinedload(Application.job_type),
            joinedload(Application.resume),
        )
    )

    if status:
        stmt = stmt.where(Application.status == status)
    if has_interview in ("yes", "no"):
        want = has_interview == "yes"
        stmt = stmt.where(Application.has_interview.is_(want))
    if job_type_id:
        stmt = stmt.where(Application.job_type_id == job_type_id)
    if channel:
        stmt = stmt.where(Application.channel == channel)
    if company_id:
        stmt = stmt.where(Application.company_id == company_id)
    if date_from and parse_date(date_from):
        stmt = stmt.where(Application.applied_at >= datetime.combine(parse_date(date_from), time.min))
    if date_to and parse_date(date_to):
        stmt = stmt.where(
            Application.applied_at < datetime.combine(parse_date(date_to), time.min) + timedelta(days=1)
        )
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Application.position_name.like(like), Company.name.like(like)))

    stmt = stmt.order_by(*SORT_MAP.get(sort, SORT_MAP["applied_desc"]))
    return db.paginate(stmt, page=max(page, 1), per_page=per_page, error_out=False)


def status_counts(user_id: int) -> dict[str, int]:
    """状态页签上的计数，一次 GROUP BY 拿全。"""
    stmt = (
        select(Application.status, func.count(Application.id))
        .where(Application.user_id == user_id)
        .group_by(Application.status)
    )
    return {row[0]: row[1] for row in db.session.execute(stmt)}


def recent(user_id: int, limit: int = 5) -> list[Application]:
    stmt = (
        select(Application)
        .where(Application.user_id == user_id)
        .options(joinedload(Application.company), joinedload(Application.job_type))
        .order_by(Application.applied_at.desc(), Application.id.desc())
        .limit(limit)
    )
    return db.session.execute(stmt).unique().scalars().all()


def upcoming_interviews(user_id: int, limit: int = 5) -> list[Interview]:
    """近期面试提醒（看板用）。"""
    stmt = (
        select(Interview)
        .join(Application, Application.id == Interview.application_id)
        .where(
            Interview.user_id == user_id,
            Interview.scheduled_at >= now_local(),
            Interview.result == "pending",
        )
        .options(joinedload(Interview.application).joinedload(Application.company))
        .order_by(Interview.scheduled_at.asc())
        .limit(limit)
    )
    return db.session.execute(stmt).unique().scalars().all()
