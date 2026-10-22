"""自定义职位类型：用户自己维护的分类维度，颜色会直接用于图表配色。"""

from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TimestampMixin, fk_type, pk_type


class JobType(db.Model, TimestampMixin):
    __tablename__ = "job_types"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_job_types_user_name"),
        Index("idx_jobtype_user_active_sort", "user_id", "is_active", "sort_order", "id"),
        CheckConstraint("sort_order >= 0", name="sort_order_non_negative"),
    )

    id: Mapped[int] = mapped_column(pk_type(), primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        fk_type(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False, comment="类型名称，如「后端开发」")
    color: Mapped[str] = mapped_column(
        String(7), nullable=False, default="#0d6efd", comment="十六进制色值，用于图表"
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="升序排列")
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="停用后新投递不可选，历史记录照常展示"
    )

    user: Mapped["User"] = relationship(back_populates="job_types")  # noqa: F821
    applications: Mapped[list["Application"]] = relationship(  # noqa: F821
        back_populates="job_type", passive_deletes=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<JobType {self.id} {self.name}>"
