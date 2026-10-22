"""用户模型。"""

from __future__ import annotations

from datetime import datetime

from flask_login import UserMixin
from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models.base import TimestampMixin, pk_type


class User(db.Model, TimestampMixin, UserMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(pk_type(), primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, comment="登录名")
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, comment="邮箱")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, comment="scrypt 哈希")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最近登录")

    companies: Mapped[list["Company"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    job_types: Mapped[list["JobType"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    resumes: Mapped[list["Resume"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    applications: Mapped[list["Application"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    interviews: Mapped[list["Interview"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )

    # ---------- 密码 ----------
    def set_password(self, raw: str) -> None:
        """werkzeug 默认 scrypt，自带随机盐，不可逆。"""
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw: str) -> bool:
        if not self.password_hash or not raw:
            return False
        return check_password_hash(self.password_hash, raw)

    @property
    def initial(self) -> str:
        """头像占位字母。"""
        return (self.username or "?")[0].upper()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.id} {self.username}>"
