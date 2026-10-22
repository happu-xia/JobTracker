"""认证相关表单。"""

from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length


class LoginForm(FlaskForm):
    account = StringField(
        "用户名 / 邮箱",
        validators=[DataRequired(message="请输入用户名或邮箱"), Length(max=120)],
        render_kw={"placeholder": "用户名或邮箱", "autofocus": True, "autocomplete": "username"},
    )
    password = PasswordField(
        "密码",
        validators=[DataRequired(message="请输入密码"), Length(max=128)],
        render_kw={"placeholder": "密码", "autocomplete": "current-password"},
    )
    remember = BooleanField("7 天内免登录")
    submit = SubmitField("登录")


class RegisterForm(FlaskForm):
    username = StringField(
        "用户名",
        validators=[DataRequired(message="请输入用户名"), Length(min=2, max=50, message="用户名长度 2-50 位")],
        render_kw={"placeholder": "2-50 位，登录时使用", "autofocus": True},
    )
    email = StringField(
        "邮箱",
        validators=[DataRequired(message="请输入邮箱"), Email(message="邮箱格式不正确"), Length(max=120)],
        render_kw={"placeholder": "you@example.com"},
    )
    password = PasswordField(
        "密码",
        validators=[DataRequired(message="请输入密码"), Length(min=6, max=128, message="密码至少 6 位")],
        render_kw={"placeholder": "至少 6 位"},
    )
    password2 = PasswordField(
        "确认密码",
        validators=[DataRequired(message="请再次输入密码"), EqualTo("password", message="两次输入的密码不一致")],
        render_kw={"placeholder": "再次输入密码"},
    )
    submit = SubmitField("注册并开始记录")


class ChangePasswordForm(FlaskForm):
    old_password = PasswordField("原密码", validators=[DataRequired(message="请输入原密码")])
    new_password = PasswordField(
        "新密码",
        validators=[DataRequired(message="请输入新密码"), Length(min=6, max=128, message="新密码至少 6 位")],
    )
    new_password2 = PasswordField(
        "确认新密码",
        validators=[DataRequired(message="请再次输入新密码"), EqualTo("new_password", message="两次输入不一致")],
    )
    submit = SubmitField("保存新密码")
