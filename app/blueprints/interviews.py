"""面试蓝图：作为投递记录的子资源挂在 /applications/<id>/interviews 下。"""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.forms.misc_forms import InterviewForm
from app.services import application_service, interview_service
from app.utils.errors import BusinessError

bp = Blueprint("interviews", __name__, url_prefix="/applications/<int:app_id>/interviews")


def _back(app_id: int):
    return redirect(url_for("applications.detail", app_id=app_id))


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create(app_id: int):
    app_obj = application_service.get_or_404(current_user.id, app_id)
    form = InterviewForm()

    if form.validate_on_submit():
        try:
            interview_service.create(app_obj, form.to_payload())
        except BusinessError as exc:
            flash(exc.message, "danger")
        else:
            flash("面试记录已添加，投递状态已同步为「面试中」", "success")
            return _back(app_id)

    return render_template(
        "interviews/form.html", form=form, application=app_obj, interview=None
    )


@bp.route("/<int:interview_id>/edit", methods=["GET", "POST"])
@login_required
def edit(app_id: int, interview_id: int):
    app_obj = application_service.get_or_404(current_user.id, app_id)
    interview = interview_service.get_or_404(current_user.id, interview_id)
    form = InterviewForm(obj=interview)

    if form.validate_on_submit():
        try:
            interview_service.update(interview, form.to_payload())
        except BusinessError as exc:
            flash(exc.message, "danger")
        else:
            flash("面试记录已更新", "success")
            return _back(app_id)

    return render_template(
        "interviews/form.html", form=form, application=app_obj, interview=interview
    )


@bp.post("/<int:interview_id>/delete")
@login_required
def delete(app_id: int, interview_id: int):
    interview = interview_service.get_or_404(current_user.id, interview_id)
    interview_service.delete(interview)
    flash("面试记录已删除", "success")
    return _back(app_id)


@bp.post("/<int:interview_id>/result")
@login_required
def update_result(app_id: int, interview_id: int):
    """详情页的「一键标记结果」，避免为了改一个字段进编辑页。"""
    interview = interview_service.get_or_404(current_user.id, interview_id)
    result = request.form.get("result", "")
    try:
        interview_service.update(
            interview,
            {
                "round": interview.round,
                "scheduled_at": interview.scheduled_at,
                "result": result,
                "feedback": interview.feedback,
            },
        )
    except BusinessError as exc:
        flash(exc.message, "danger")
    else:
        flash("面试结果已更新", "success")
    return _back(app_id)
