"""企业库蓝图。"""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.forms.company_forms import CompanyForm
from app.services import application_service, company_service
from app.utils.decorators import filter_args
from app.utils.errors import BusinessError
from app.utils.pagination import Pagination

bp = Blueprint("companies", __name__, url_prefix="/companies")


@bp.get("")
@login_required
def index():
    q = request.args.get("q", "").strip()
    city = request.args.get("city", "").strip() or None
    page = request.args.get("page", 1, type=int)
    pagination = company_service.list_companies(
        current_user.id, q=q or None, city=city, page=page
    )
    counts = company_service.application_counts(
        current_user.id, [c.id for c in pagination.items]
    )
    return render_template(
        "companies/list.html",
        pagination=Pagination.from_flask(pagination, filter_args()),
        counts=counts,
        q=q,
        city=city or "",
        cities=company_service.city_options(current_user.id),
        total_all=sum(counts.values()),
    )


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    form = CompanyForm()
    if form.validate_on_submit():
        try:
            company = company_service.create(current_user.id, form.data)
        except BusinessError as exc:
            flash(exc.message, "danger")
        else:
            flash(f"已添加企业「{company.name}」", "success")
            return redirect(url_for("companies.detail", company_id=company.id))
    return render_template("companies/form.html", form=form, company=None)


@bp.get("/<int:company_id>")
@login_required
def detail(company_id: int):
    company = company_service.get_or_404(current_user.id, company_id)
    page = request.args.get("page", 1, type=int)
    pagination = application_service.list_applications(
        current_user.id, company_id=company_id, page=page
    )
    return render_template(
        "companies/detail.html",
        company=company,
        pagination=Pagination.from_flask(pagination, filter_args()),
        usage=company_service.application_counts(current_user.id, [company.id]).get(company.id, 0),
    )


@bp.route("/<int:company_id>/edit", methods=["GET", "POST"])
@login_required
def edit(company_id: int):
    company = company_service.get_or_404(current_user.id, company_id)
    form = CompanyForm(obj=company)
    if form.validate_on_submit():
        try:
            company_service.update(company, form.data)
        except BusinessError as exc:
            flash(exc.message, "danger")
        else:
            flash("企业信息已更新", "success")
            return redirect(url_for("companies.detail", company_id=company.id))
    return render_template("companies/form.html", form=form, company=company)


@bp.post("/<int:company_id>/delete")
@login_required
def delete(company_id: int):
    company = company_service.get_or_404(current_user.id, company_id)
    force = request.form.get("force") == "1"
    name = company.name
    try:
        removed = company_service.delete(company, force=force)
    except BusinessError as exc:
        flash(exc.message, "warning")
        return redirect(url_for("companies.detail", company_id=company_id))

    flash(
        f"已删除企业「{name}」" + (f"，同时删除 {removed} 条关联投递" if removed else ""),
        "success",
    )
    return redirect(url_for("companies.index"))
