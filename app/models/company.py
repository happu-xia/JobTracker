"""企业模型：官网链接是本表的核心字段之一。"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TimestampMixin, fk_type, pk_type


class Company(db.Model, TimestampMixin):
    __tablename__ = "companies"
    __table_args__ = (
        # 同一用户不允许重复录入同一家企业（排序规则 ci，故大小写不敏感）
        UniqueConstraint("user_id", "name", name="uq_companies_user_name"),
        Index("idx_company_user_created", "user_id", "created_at"),
        Index("idx_company_user_city", "user_id", "city"),
    )

    id: Mapped[int] = mapped_column(pk_type(), primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        fk_type(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="企业名称")
    website: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="官网（规范化后的 https URL）")
    industry: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="行业")
    scale: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="人员规模枚举")
    city: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="城市")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")

    user: Mapped["User"] = relationship(back_populates="companies")  # noqa: F821
    applications: Mapped[list["Application"]] = relationship(  # noqa: F821
        back_populates="company",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Company {self.id} {self.name}>"
