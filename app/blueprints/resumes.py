"""简历蓝图：上传、列表、预览、下载、设默认、删除。"""

from __future__ import annotations

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required

from app.forms.misc_forms import ResumeUploadForm
from app.services import resume_service
from app.utils.errors import BusinessError
from app.utils.security import content_disposition

bp = Blueprint("resumes", __name__, url_prefix="/resumes")


@bp.get("")
@login_required
def index():
    items = resume_service.list_resumes(current_user.id)
    return render_template(
        "resumes/list.html",
        items=items,
        has_default=any(item.is_default for item in items),
        max_mb=current_app.config["MAX_UPLOAD_MB"],
    )


@bp.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    form = ResumeUploadForm()
    if form.validate_on_submit():
        try:
            resume = resume_service.upload(
                current_user, form.file.data, set_default=form.as_default
            )
        except BusinessError as exc:
            flash(exc.message, "danger")
        else:
            flash(f"已上传「{resume.original_name}」", "success")
            return redirect(url_for("resumes.index"))

    return render_template(
        "resumes/upload.html",
        form=form,
        max_mb=current_app.config["MAX_UPLOAD_MB"],
        items_count=len(resume_service.list_resumes(current_user.id)),
    )


@bp.get("/<int:resume_id>/preview")
@login_required
def preview(resume_id: int):
    resume = resume_service.get_or_404(current_user.id, resume_id)
    if resume.ext != "pdf":
        # 浏览器不能内联渲染 doc/docx，给出信息卡而不是 404
        return render_template("resumes/preview.html", resume=resume, inline=False)

    stream = resume_service.open_stream(resume)
    response = Response(stream.read(), mimetype="application/pdf")
    stream.close()
    # inline 让浏览器内置阅读器打开；sandbox 头防止 PDF 里的脚本影响本站
    response.headers["Content-Disposition"] = f"inline; filename=\"{resume.stored_name}\""
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@bp.get("/<int:resume_id>/download")
@login_required
def download(resume_id: int):
    resume = resume_service.get_or_404(current_user.id, resume_id)
    stream = resume_service.open_stream(resume)
    response = send_file(
        stream,
        mimetype=resume.mime,
        as_attachment=True,
        download_name=resume.original_name,
    )
    response.headers["Content-Disposition"] = content_disposition(resume.original_name)
    return response


@bp.post("/<int:resume_id>/default")
@login_required
def set_default(resume_id: int):
    resume = resume_service.get_or_404(current_user.id, resume_id)
    resume_service.set_default(resume)
    flash(f"已将「{resume.original_name}」设为默认简历", "success")
    return redirect(url_for("resumes.index"))


@bp.post("/<int:resume_id>/delete")
@login_required
def delete(resume_id: int):
    resume = resume_service.get_or_404(current_user.id, resume_id)
    name = resume.original_name
    resume_service.delete(resume)
    flash(f"已删除简历「{name}」，相关投递记录显示为「未绑定简历」", "success")
    return redirect(url_for("resumes.index"))
