"""面试记录：投递记录的子资源。

刻意做成独立表而不是在 applications 上放 ``interview_at`` 字段：
一次投递有多轮面试（一面/二面/HR 面），且每轮有独立时间、结果、复盘。
「是否有面试」由本表的存在性派生（见 Application.has_interview）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, CheckConstraint, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TimestampMixin, fk_type, pk_type


class Interview(db.Model, TimestampMixin):
    __tablename__ = "interviews"
    __table_args__ = (
        # 同一投递的同一轮次只允许一条（如需「同轮多场技术面」可去掉此约束）
        UniqueConstraint("application_id", "round", name="uq_interviews_application_round"),
        Index("idx_interview_user_time", "user_id", "scheduled_at"),
        Index("idx_interview_user_result", "user_id", "result"),
        CheckConstraint("round IN ('first','second','third','hr','other')", name="round_valid"),
        CheckConstraint("result IN ('pending','passed','failed')", name="result_valid"),
    )

    id: Mapped[int] = mapped_column(pk_type(), primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        fk_type(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="冗余用户字段，统计可直连过滤",
    )
    application_id: Mapped[int] = mapped_column(
        fk_type(), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    round: Mapped[str] = mapped_column(String(20), nullable=False, default="first", comment="面试轮次")
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="面试时间")
    result: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", comment="结果")
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True, comment="面经/复盘")

    user: Mapped["User"] = relationship(back_populates="interviews")  # noqa: F821
    application: Mapped["Application"] = relationship(back_populates="interviews")  # noqa: F821

    @property
    def round_label(self) -> str:
        from app.utils.constants import round_label

        return round_label(self.round)

    @property
    def result_label(self) -> str:
        from app.utils.constants import result_label

        return result_label(self.result)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Interview {self.id} {self.round} {self.result}>"
