"""投递记录蓝图：列表、详情、增改、状态流转、删除。"""

from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from app.extensions import db
from app.forms.application_forms import ApplicationForm
from app.forms.misc_forms import InterviewForm
from app.models.company import Company
from app.models.job_type import JobType
from app.services import (
    application_service,
    company_service,
    job_type_service,
    resume_service,
)
from app.utils.constants import CHANNEL_LABELS, SORT_OPTIONS, STATUS_LABELS, STATUS_TRANSITIONS
from app.utils.decorators import filter_args
from app.utils.errors import BusinessError
from app.utils.pagination import Pagination

bp = Blueprint("applications", __name__, url_prefix="/applications")


def _fill_choices(form: ApplicationForm, user_id: int, *, keep_type_id: int | None = None):
    """下拉选项由当前用户的数据动态生成（这就是「自定义职位类型」的落点）。"""
    companies = (
        db.session.execute(
            select(Company).where(Company.user_id == user_id).order_by(Company.name)
        )
        .scalars()
        .all()
    )
    form.company_id.choices = [(0, "— 请选择企业 —")] + [(c.id, c.name) for c in companies]

    types = job_type_service.active_types(user_id)
    choices = [(t.id, t.name) for t in types]
    # 编辑时若原类型已被停用，仍要出现在选项里，否则保存会静默把分类清空
    if keep_type_id and all(t.id != keep_type_id for t in types):
        legacy = db.session.get(JobType, keep_type_id)
        if legacy is not None and legacy.user_id == user_id:
            choices.append((legacy.id, f"{legacy.name}（已停用）"))
    form.job_type_id.choices = [(0, "未分类")] + choices

    resumes = resume_service.list_resumes(user_id)
    form.resume_id.choices = [(0, "不绑定简历")] + [
        (r.id, f"{r.original_name}{'（默认）' if r.is_default else ''}") for r in resumes
    ]
    return companies, types, resumes


@bp.get("")
@login_required
def index():
    page = request.args.get("page", 1, type=int)
    filters = {
        "status": request.args.get("status") or None,
        "has_interview": request.args.get("has_interview") or None,
        "job_type_id": request.args.get("job_type_id", type=int) or None,
        "channel": request.args.get("channel") or None,
        "company_id": request.args.get("company_id", type=int) or None,
        "date_from": request.args.get("date_from") or None,
        "date_to": request.args.get("date_to") or None,
        "q": (request.args.get("q") or "").strip() or None,
        "sort": request.args.get("sort") or "applied_desc",
    }
    pagination = application_service.list_applications(current_user.id, page=page, **filters)
    counts = application_service.status_counts(current_user.id)

    return render_template(
        "applications/list.html",
        pagination=Pagination.from_flask(pagination, filter_args()),
        counts=counts,
        total=sum(counts.values()),
        types=job_type_service.active_types(current_user.id),
        channels=CHANNEL_LABELS,
        sort_options=SORT_OPTIONS,
        filters=filters,
    )


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    form = ApplicationForm()
    companies, _types, resumes = _fill_choices(form, current_user.id)

    if request.method == "GET":
        preset_company = request.args.get("company_id", type=int)
        if preset_company:
            form.company_id.data = preset_company
        default_resume = resume_service.default_resume(current_user.id)
        if default_resume and not form.resume_id.data:
            form.resume_id.data = default_resume.id

    if not companies:
        flash("先添加一家企业，才能记录投递", "warning")
        return redirect(url_for("companies.create"))

    if form.validate_on_submit():
        try:
            app_obj = application_service.create(current_user.id, form.to_payload())
        except BusinessError as exc:
            flash(exc.message, "danger")
        else:
            flash(f"已记录投递：{app_obj.position_name}", "success")
            return redirect(url_for("applications.detail", app_id=app_obj.id))

    return render_template(
        "applications/form.html", form=form, application=None, has_resume=bool(resumes)
    )


@bp.get("/<int:app_id>")
@login_required
def detail(app_id: int):
    app_obj = application_service.get_or_404(current_user.id, app_id)
    return render_template(
        "applications/detail.html",
        application=app_obj,
        interview_form=InterviewForm(),
        next_statuses=[
            (status, STATUS_LABELS[status])
            for status in STATUS_TRANSITIONS.get(app_obj.status, ())
        ],
    )


@bp.route("/<int:app_id>/edit", methods=["GET", "POST"])
@login_required
def edit(app_id: int):
    app_obj = application_service.get_or_404(current_user.id, app_id)
    form = ApplicationForm(obj=app_obj)
    _fill_choices(form, current_user.id, keep_type_id=app_obj.job_type_id)

    if request.method == "GET":
        form.job_type_id.data = app_obj.job_type_id or 0
        form.resume_id.data = app_obj.resume_id or 0

    if form.validate_on_submit():
        try:
            application_service.update(app_obj, form.to_payload())
        except BusinessError as exc:
            flash(exc.message, "danger")
        else:
            flash("投递记录已更新", "success")
            return redirect(url_for("applications.detail", app_id=app_obj.id))

    return render_template(
        "applications/form.html", form=form, application=app_obj, has_resume=True
    )


@bp.post("/<int:app_id>/status")
@login_required
def change_status(app_id: int):
    app_obj = application_service.get_or_404(current_user.id, app_id)
    target = request.form.get("status", "")
    if target not in STATUS_LABELS:
        abort(400, description="非法的目标状态")

    try:
        application_service.transition(app_obj, target)
    except BusinessError as exc:
        flash(exc.message, "danger")
    else:
        flash(f"状态已更新为「{STATUS_LABELS[target]}」", "success")

    return redirect(request.referrer or url_for("applications.detail", app_id=app_id))


@bp.post("/<int:app_id>/delete")
@login_required
def delete(app_id: int):
    app_obj = application_service.get_or_404(current_user.id, app_id)
    position = app_obj.position_name
    application_service.delete(app_obj)
    flash(f"已删除投递「{position}」（简历文件未被删除）", "success")
    return redirect(url_for("applications.index"))
