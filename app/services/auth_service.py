"""认证服务：注册、登录、改密。

所有校验失败都抛 BusinessError 子类，由统一异常处理器转成 flash 或 4xx JSON，
视图层不需要写任何 try/except。
"""

from __future__ import annotations

from sqlalchemy import func, or_, select

from app.extensions import db
from app.models.job_type import JobType
from app.models.user import User
from app.utils.dtime import now_local
from app.utils.errors import ConflictError, ValidationError, BusinessError

# 新用户注册时自动建好的职位分类，避免「先建类型才能投递」的空转
DEFAULT_JOB_TYPES = [
    ("后端开发", "#5B8FF9"),
    ("前端开发", "#5AD8A6"),
    ("算法/数据", "#F6BD16"),
    ("产品/运营", "#FF9D4D"),
    ("测试/运维", "#9270CA"),
]

MIN_PASSWORD_LENGTH = 6


def _normalize_username(username: str) -> str:
    return (username or "").strip()


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def register(username: str, email: str, password: str, *, seed_job_types: bool = True) -> User:
    """注册新用户。

    唯一性校验必须在应用层先做一次（给出中文提示），
    数据库唯一索引作为并发下的最后一道防线。
    """
    username = _normalize_username(username)
    email = _normalize_email(email)

    if not username or not email:
        raise ValidationError("用户名和邮箱不能为空")
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise ValidationError(f"密码长度至少 {MIN_PASSWORD_LENGTH} 位")

    exists_stmt = select(User).where(or_(User.username == username, User.email == email))
    if db.session.execute(exists_stmt).scalars().first() is not None:
        raise ConflictError("用户名或邮箱已被注册")

    user = User(username=username, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()  # 拿到 user.id

    if seed_job_types:
        for index, (name, color) in enumerate(DEFAULT_JOB_TYPES):
            db.session.add(
                JobType(user_id=user.id, name=name, color=color, sort_order=index * 10, is_active=True)
            )

    db.session.commit()
    return user


def authenticate(account: str, password: str) -> User:
    """支持用户名或邮箱登录。"""
    account = (account or "").strip()
    if not account or not password:
        raise BusinessError("请输入账号和密码")

    stmt = select(User).where(
        or_(func.lower(User.username) == account.lower(), User.email == account.lower())
    )
    user = db.session.execute(stmt).scalars().first()

    # 用户不存在与密码错误返回同一句提示，避免账号枚举
    if user is None or not user.check_password(password):
        raise BusinessError("账号或密码错误")

    user.last_login_at = now_local()
    db.session.commit()
    return user


def change_password(user: User, old_password: str, new_password: str) -> None:
    if not user.check_password(old_password):
        raise BusinessError("原密码不正确")
    if len(new_password or "") < MIN_PASSWORD_LENGTH:
        raise ValidationError(f"新密码长度至少 {MIN_PASSWORD_LENGTH} 位")
    if old_password == new_password:
        raise BusinessError("新密码不能与原密码相同")

    user.set_password(new_password)
    db.session.commit()
