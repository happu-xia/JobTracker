"""测试数据工厂：让用例只描述「业务意图」，不关心字段填充。"""

from __future__ import annotations

import io
import itertools
from datetime import timedelta

from app.extensions import db
from app.models.application import Application
from app.models.company import Company
from app.models.interview import Interview
from app.models.job_type import JobType
from app.models.resume import Resume
from app.services.file_storage import LocalFileStorage
from app.utils.dtime import now_local


def make_company(user_id: int, name: str = "测试科技", **kwargs) -> Company:
    company = Company(user_id=user_id, name=name, **kwargs)
    db.session.add(company)
    db.session.commit()
    return company


_job_type_seq = itertools.count(1)


def make_job_type(user_id: int, name: str | None = None, **kwargs) -> JobType:
    """注册流程会预置 5 个默认类型，故未指定名称时自动生成不冲突的名字。"""
    item = JobType(user_id=user_id, name=name or f"测试类型{next(_job_type_seq)}", **kwargs)
    db.session.add(item)
    db.session.commit()
    return item


def make_application(
    user_id: int,
    company_id: int,
    *,
    position: str = "Java 后端",
    status: str = "applied",
    max_stage: int = 1,
    days_ago: int = 0,
    job_type_id: int | None = None,
    **kwargs,
) -> Application:
    applied_at = (now_local() - timedelta(days=days_ago)).replace(microsecond=0)
    app_obj = Application(
        user_id=user_id,
        company_id=company_id,
        job_type_id=job_type_id,
        position_name=position,
        status=status,
        channel=kwargs.pop("channel", "boss"),
        applied_at=applied_at,
        max_stage=max_stage,
        **kwargs,
    )
    db.session.add(app_obj)
    db.session.commit()
    return app_obj


def make_interview(
    user_id: int,
    application_id: int,
    *,
    round_name: str = "first",
    result: str = "pending",
    days_ago: int = 1,
    feedback: str | None = None,
) -> Interview:
    item = Interview(
        user_id=user_id,
        application_id=application_id,
        round=round_name,
        scheduled_at=(now_local() - timedelta(days=days_ago)).replace(microsecond=0),
        result=result,
        feedback=feedback,
    )
    db.session.add(item)
    db.session.commit()
    return item


def make_resume(app, user_id: int, *, name: str = "简历.pdf", is_default: bool = True) -> Resume:
    """真实落盘一份最小 PDF，保证下载/预览路径可测。"""
    storage = LocalFileStorage(app.config["UPLOAD_ROOT"])
    meta = storage.save(io.BytesIO(b"%PDF-1.4\n%%EOF\n"), user_id, "pdf")
    resume = Resume(
        user_id=user_id,
        original_name=name,
        stored_name=meta["stored_name"],
        rel_path=meta["rel_path"],
        ext="pdf",
        mime="application/pdf",
        size_bytes=meta["size_bytes"],
        sha256=meta["sha256"],
        is_default=is_default,
    )
    db.session.add(resume)
    db.session.commit()
    return resume
