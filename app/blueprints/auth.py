"""认证蓝图：注册 / 登录 / 登出 / 改密。"""

from __future__ import annotations

from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.forms.auth_forms import ChangePasswordForm, LoginForm, RegisterForm
from app.services import auth_service
from app.utils.errors import BusinessError

bp = Blueprint("auth", __name__, url_prefix="/auth")


def _safe_next(target: str | None) -> str:
    """防开放重定向：只允许站内相对路径。"""
    if not target:
        return url_for("main.index")
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc or not target.startswith("/"):
        return url_for("main.index")
    return target


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = LoginForm()
    if form.validate_on_submit():
        try:
            user = auth_service.authenticate(form.account.data, form.password.data)
        except BusinessError as exc:
            flash(exc.message, "danger")
        else:
            login_user(user, remember=form.remember.data)
            flash(f"欢迎回来，{user.username}", "success")
            return redirect(_safe_next(request.args.get("next")))

    return render_template("auth/login.html", form=form)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = RegisterForm()
    if form.validate_on_submit():
        try:
            user = auth_service.register(
                form.username.data, form.email.data, form.password.data
            )
        except BusinessError as exc:
            flash(exc.message, "danger")
        else:
            login_user(user)
            flash("注册成功，已为你预置 5 个常用职位类型，可以开始记录投递了", "success")
            return redirect(url_for("main.index"))

    return render_template("auth/register.html", form=form)


@bp.post("/logout")
@login_required
def logout():
    logout_user()
    flash("已退出登录", "info")
    return redirect(url_for("auth.login"))


@bp.route("/password", methods=["GET", "POST"])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        try:
            auth_service.change_password(
                current_user, form.old_password.data, form.new_password.data
            )
        except BusinessError as exc:
            flash(exc.message, "danger")
        else:
            flash("密码已更新，请使用新密码登录", "success")
            logout_user()
            return redirect(url_for("auth.login"))

    return render_template("auth/password.html", form=form)
