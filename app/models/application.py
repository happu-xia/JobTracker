"""投递记录（核心表）。

两个关键设计：
1. ``max_stage`` —— 单调递增的「历史最高阶段」。状态可能走到 rejected/withdrawn 这类终态，
   单看 status 无法还原它到底走到哪一步，漏斗统计会系统性偏低；有了 max_stage，
   四层漏斗可以用一条 ``SUM(CASE WHEN max_stage >= N)`` 查出来。
2. ``has_interview`` —— 用 EXISTS 相关子查询下沉成可筛选的派生列，
   列表页按「有/无面试」过滤时不需要 N+1 追加查询。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    select,
)
from sqlalchemy.orm import Mapped, column_property, mapped_column, relationship

from app.extensions import db
from app.models.base import TimestampMixin, fk_type, pk_type, small_uint
from app.models.interview import Interview

STATUS_VALUES = ("applied", "viewed", "interviewing", "offer", "rejected", "withdrawn")
CHANNEL_VALUES = (
    "website",
    "referral",
    "campus",
    "boss",
    "liepin",
    "lagou",
    "zhilian",
    "other",
)


class Application(db.Model, TimestampMixin):
    __tablename__ = "applications"
    __table_args__ = (
        # 所有高频过滤组合都以 user_id 打头，保证隔离查询走索引
        Index("idx_app_user_applied", "user_id", "applied_at"),
        Index("idx_app_user_status", "user_id", "status"),
        Index("idx_app_user_stage", "user_id", "max_stage"),
        Index("idx_app_user_company", "user_id", "company_id"),
        Index("idx_app_user_jobtype", "user_id", "job_type_id"),
        Index("idx_app_user_channel", "user_id", "channel"),
        Index("idx_app_resume", "resume_id"),
        CheckConstraint(
            "status IN ('applied','viewed','interviewing','offer','rejected','withdrawn')",
            name="status_valid",
        ),
        CheckConstraint(
            "channel IN ('website','referral','campus','boss','liepin','lagou','zhilian','other')",
            name="channel_valid",
        ),
        CheckConstraint("max_stage BETWEEN 1 AND 4", name="stage_range"),
        CheckConstraint(
            "salary_min IS NULL OR salary_max IS NULL OR salary_min <= salary_max",
            name="salary_order",
        ),
    )

    id: Mapped[int] = mapped_column(pk_type(), primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        fk_type(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[int] = mapped_column(
        fk_type(), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    job_type_id: Mapped[int | None] = mapped_column(
        fk_type(), ForeignKey("job_types.id", ondelete="SET NULL"), nullable=True
    )
    resume_id: Mapped[int | None] = mapped_column(
        fk_type(), ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True
    )
    position_name: Mapped[str] = mapped_column(String(120), nullable=False, comment="职位名称")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="applied", comment="当前状态"
    )
    channel: Mapped[str] = mapped_column(
        String(20), nullable=False, default="other", comment="投递渠道"
    )
    applied_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="投递时间")
    salary_min: Mapped[int | None] = mapped_column(small_uint(), nullable=True, comment="月薪下限(K)")
    salary_max: Mapped[int | None] = mapped_column(small_uint(), nullable=True, comment="月薪上限(K)")
    jd_url: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="JD 链接")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
    max_stage: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, comment="历史最高阶段 1投递 2查看 3面试 4Offer"
    )
    first_viewed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="首次进入已查看的时间"
    )
    response_days: Mapped[int | None] = mapped_column(
        small_uint(), nullable=True, comment="企业响应耗时(天)，冗余落库便于跨库 AVG"
    )

    # ---------- 关系 ----------
    user: Mapped["User"] = relationship(back_populates="applications")  # noqa: F821
    company: Mapped["Company"] = relationship(back_populates="applications")  # noqa: F821
    job_type: Mapped["JobType | None"] = relationship(back_populates="applications")  # noqa: F821
    resume: Mapped["Resume | None"] = relationship(back_populates="applications")  # noqa: F821
    interviews: Mapped[list[Interview]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Interview.scheduled_at",
    )

    # ---------- 派生列 ----------
    has_interview = column_property(
        select(Interview.id)
        .where(Interview.application_id == id)
        .correlate_except(Interview)
        .exists()
    )

    # ---------- 展示辅助 ----------
    @property
    def salary_label(self) -> str:
        if self.salary_min is None and self.salary_max is None:
            return "面议"
        low = f"{self.salary_min}K" if self.salary_min is not None else "?"
        high = f"{self.salary_max}K" if self.salary_max is not None else "?"
        return f"{low} - {high}"

    @property
    def stage_label(self) -> str:
        from app.utils.constants import STAGE_LABELS

        return STAGE_LABELS.get(self.max_stage, "—")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Application {self.id} {self.position_name} {self.status}>"
