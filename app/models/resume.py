"""简历元数据模型。

文件本体在磁盘（``UPLOAD_ROOT/<user_id>/<uuid>.<ext>``），
数据库只保存相对路径与元信息，好处：
1. 迁移/备份数据库时不必搬几百 MB；2. 路径与主机解耦，换盘只改 UPLOAD_ROOT。
"""

from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TimestampMixin, fk_type, pk_type


class Resume(db.Model, TimestampMixin):
    __tablename__ = "resumes"
    __table_args__ = (
        UniqueConstraint("user_id", "stored_name", name="uq_resumes_user_stored_name"),
        Index("idx_resume_user_default", "user_id", "is_default", "created_at"),
        CheckConstraint("size_bytes > 0", name="size_positive"),
    )

    id: Mapped[int] = mapped_column(pk_type(), primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        fk_type(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_name: Mapped[str] = mapped_column(String(255), nullable=False, comment="用户上传时的文件名")
    stored_name: Mapped[str] = mapped_column(String(64), nullable=False, comment="uuid4().hex + 扩展名")
    rel_path: Mapped[str] = mapped_column(String(512), nullable=False, comment="相对 UPLOAD_ROOT 的路径")
    ext: Mapped[str] = mapped_column(String(10), nullable=False, comment="pdf/doc/docx，小写")
    mime: Mapped[str] = mapped_column(String(100), nullable=False, comment="服务端探测的 MIME")
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, comment="字节数")
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="内容指纹，用于重复上传提示")
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="默认简历（唯一性由 Service 层事务保证）",
    )

    user: Mapped["User"] = relationship(back_populates="resumes")  # noqa: F821
    applications: Mapped[list["Application"]] = relationship(  # noqa: F821
        back_populates="resume", passive_deletes=True
    )

    @property
    def size_label(self) -> str:
        from app.utils.security import human_size

        return human_size(self.size_bytes)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Resume {self.id} {self.original_name}>"
