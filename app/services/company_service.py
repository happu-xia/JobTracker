"""企业库服务：CRUD、搜索、城市筛选、删除前引用检查。"""

from __future__ import annotations

from sqlalchemy import func, or_, select

from app.extensions import db
from app.models.application import Application
from app.models.company import Company
from app.utils.errors import ConflictError, ValidationError
from app.utils.url import InvalidUrlError, normalize_url


def _clean(data: dict) -> dict:
    """统一清洗入参：字符串去空格、空串转 None、URL 规范化。"""
    name = (data.get("name") or "").strip()
    if not name:
        raise ValidationError("企业名称不能为空")
    if len(name) > 100:
        raise ValidationError("企业名称不能超过 100 个字符")

    try:
        website = normalize_url(data.get("website"))
    except InvalidUrlError as exc:
        raise ValidationError(str(exc), field="website") from exc

    def blank_to_none(key: str) -> str | None:
        value = (data.get(key) or "").strip()
        return value or None

    return {
        "name": name,
        "website": website,
        "industry": blank_to_none("industry"),
        "scale": blank_to_none("scale"),
        "city": blank_to_none("city"),
        "notes": blank_to_none("notes"),
    }


def application_counts(user_id: int, company_ids: list[int]) -> dict[int, int]:
    """批量取「每家企业关联的投递数」，避免逐个 company.applications 触发 N+1。"""
    if not company_ids:
        return {}
    stmt = (
        select(Application.company_id, func.count(Application.id))
        .where(Application.user_id == user_id, Application.company_id.in_(company_ids))
        .group_by(Application.company_id)
    )
    return {row[0]: row[1] for row in db.session.execute(stmt)}


def list_companies(
    user_id: int,
    *,
    q: str | None = None,
    city: str | None = None,
    page: int = 1,
    per_page: int = 20,
):
    stmt = select(Company).where(Company.user_id == user_id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Company.name.like(like), Company.industry.like(like)))
    if city:
        stmt = stmt.where(Company.city == city)
    stmt = stmt.order_by(Company.created_at.desc(), Company.id.desc())

    return db.paginate(stmt, page=max(page, 1), per_page=per_page, error_out=False)


def city_options(user_id: int) -> list[str]:
    stmt = (
        select(Company.city)
        .where(Company.user_id == user_id, Company.city.is_not(None), Company.city != "")
        .distinct()
        .order_by(Company.city)
    )
    return [row[0] for row in db.session.execute(stmt)]


def get_or_404(user_id: int, company_id: int) -> Company:
    stmt = select(Company).where(Company.id == company_id, Company.user_id == user_id)
    company = db.session.execute(stmt).scalar_one_or_none()
    if company is None:
        from app.utils.errors import NotFoundError

        raise NotFoundError("企业不存在，或你没有权限访问")
    return company


def _ensure_unique_name(user_id: int, name: str, *, exclude_id: int | None = None) -> None:
    stmt = select(Company.id).where(Company.user_id == user_id, Company.name == name)
    if exclude_id is not None:
        stmt = stmt.where(Company.id != exclude_id)
    if db.session.execute(stmt).first() is not None:
        raise ConflictError(f"已存在同名企业「{name}」，如需区分请在名称中加上城市或部门")


def create(user_id: int, data: dict) -> Company:
    payload = _clean(data)
    _ensure_unique_name(user_id, payload["name"])
    company = Company(user_id=user_id, **payload)
    db.session.add(company)
    db.session.commit()
    return company


def update(company: Company, data: dict) -> Company:
    payload = _clean(data)
    _ensure_unique_name(company.user_id, payload["name"], exclude_id=company.id)
    for key, value in payload.items():
        setattr(company, key, value)
    db.session.commit()
    return company


def delete(company: Company, *, force: bool = False) -> int:
    """删除企业。

    关联投递会被数据库级联删除，因此默认拒绝，必须显式 ``force`` 二次确认，
    避免「删一家公司顺手带走 30 条投递记录」这种不可逆事故。
    """
    count = db.session.execute(
        select(func.count(Application.id)).where(
            Application.company_id == company.id, Application.user_id == company.user_id
        )
    ).scalar_one()

    if count and not force:
        raise ConflictError(
            f"该企业下有 {count} 条投递记录，删除会一并删除。确认无误请勾选「同时删除关联投递」后重试"
        )

    db.session.delete(company)
    db.session.commit()
    return count
