"""首页看板 + 健康检查之外的入口页。"""

from __future__ import annotations

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from app.services import application_service, job_type_service, resume_service, stats_service

bp = Blueprint("main", __name__)


@bp.get("/")
@login_required
def index():
    """看板：近 30 天指标卡 + 近 7 天趋势 + 状态分布 + 近期面试 + 最近投递。"""
    data = stats_service.dashboard(current_user.id)
    return render_template(
        "dashboard/index.html",
        data=data,
        kpi=data["kpi"],
        upcoming=application_service.upcoming_interviews(current_user.id, limit=4),
        recent=application_service.recent(current_user.id, limit=6),
        has_resume=resume_service.default_resume(current_user.id) is not None,
        job_type_count=len(job_type_service.active_types(current_user.id)),
    )
