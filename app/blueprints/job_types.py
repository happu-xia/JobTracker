"""职位类型蓝图：用户自定义维护。"""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.forms.misc_forms import JobTypeForm
from app.services import job_type_service
from app.utils.errors import BusinessError

bp = Blueprint("job_types", __name__, url_prefix="/job-types")


@bp.get("")
@login_required
def index():
    items = job_type_service.list_with_usage(current_user.id)
    return render_template(
        "job_types/list.html",
        items=items,
        active_count=sum(1 for item, _ in items if item.is_active),
    )


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    form = JobTypeForm()
    if form.validate_on_submit():
        try:
            job_type_service.create(current_user.id, form.data)
        except BusinessError as exc:
            flash(exc.message, "danger")
        else:
            flash("职位类型已添加", "success")
            return redirect(url_for("job_types.index"))
    return render_template("job_types/form.html", form=form, item=None)


@bp.route("/<int:type_id>/edit", methods=["GET", "POST"])
@login_required
def edit(type_id: int):
    item = job_type_service.get_or_404(current_user.id, type_id)
    form = JobTypeForm(obj=item)
    if form.validate_on_submit():
        try:
            job_type_service.update(item, form.data)
        except BusinessError as exc:
            flash(exc.message, "danger")
        else:
            flash("职位类型已更新", "success")
            return redirect(url_for("job_types.index"))
    return render_template("job_types/form.html", form=form, item=item)


@bp.post("/<int:type_id>/toggle")
@login_required
def toggle(type_id: int):
    item = job_type_service.get_or_404(current_user.id, type_id)
    job_type_service.toggle(item)
    flash(f"「{item.name}」已{'启用' if item.is_active else '停用'}", "success")
    return redirect(url_for("job_types.index"))


@bp.post("/<int:type_id>/move")
@login_required
def move(type_id: int):
    item = job_type_service.get_or_404(current_user.id, type_id)
    direction = request.form.get("direction", "up")
    job_type_service.move(item, -1 if direction == "up" else 1)
    return redirect(url_for("job_types.index"))


@bp.post("/<int:type_id>/delete")
@login_required
def delete(type_id: int):
    item = job_type_service.get_or_404(current_user.id, type_id)
    try:
        job_type_service.delete(item)
    except BusinessError as exc:
        flash(exc.message, "warning")
    else:
        flash("职位类型已删除", "success")
    return redirect(url_for("job_types.index"))
