"""简历服务：上传编排、默认简历互斥、删除。

五层校验都收在这里，视图层只负责把文件交给它：
1. 扩展名白名单；2. 文件头魔数；3. 大小双端限制；
4. UUID 重命名 + 相对路径入库；5. 落盘前路径逃逸校验（file_storage 内）。
"""

from __future__ import annotations

from pathlib import Path

from flask import current_app
from sqlalchemy import select

from app.extensions import db
from app.models.resume import Resume
from app.services.file_storage import LocalFileStorage
from app.utils.constants import ALLOWED_EXTENSIONS, MIME_BY_EXT
from app.utils.errors import BusinessError, ConflictError, NotFoundError, ValidationError
from app.utils.security import verify_signature


def get_storage() -> LocalFileStorage:
    return LocalFileStorage(current_app.config["UPLOAD_ROOT"])


def list_resumes(user_id: int) -> list[Resume]:
    stmt = (
        select(Resume)
        .where(Resume.user_id == user_id)
        .order_by(Resume.is_default.desc(), Resume.created_at.desc())
    )
    return db.session.execute(stmt).scalars().all()


def default_resume(user_id: int) -> Resume | None:
    stmt = select(Resume).where(Resume.user_id == user_id, Resume.is_default.is_(True))
    return db.session.execute(stmt).scalars().first()


def get_or_404(user_id: int, resume_id: int) -> Resume:
    item = db.session.execute(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == user_id)
    ).scalar_one_or_none()
    if item is None:
        raise NotFoundError("简历不存在，或你没有权限访问")
    return item


def _ext_of(filename: str) -> str:
    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            f"仅支持 {' / '.join(ALLOWED_EXTENSIONS).upper()} 格式的简历，当前文件为「{suffix or '无扩展名'}」"
        )
    return suffix


def upload(user, file, *, set_default: bool = False) -> Resume:
    """处理一次简历上传。``file`` 是 werkzeug 的 FileStorage。"""
    if file is None or not file.filename:
        raise ValidationError("请选择要上传的文件")

    filename = file.filename
    ext = _ext_of(filename)

    # 第 2 层：魔数校验（客户端 Content-Type 可任意伪造，必须看真实文件头）
    if not verify_signature(file.stream, ext):
        raise ValidationError(
            f"文件内容与扩展名不匹配，疑似被改名的非 {ext.upper()} 文件，已拒绝上传"
        )

    # 第 3 层：大小限制（MAX_CONTENT_LENGTH 是第一道，这里再校验真实字节数）
    max_bytes = current_app.config["MAX_UPLOAD_MB"] * 1024 * 1024
    stream = file.stream
    stream.seek(0, 2)
    real_size = stream.tell()
    stream.seek(0)
    if real_size == 0:
        raise ValidationError("文件内容为空，请重新选择")
    if real_size > max_bytes:
        raise ValidationError(
            f"文件大小 {real_size / 1024 / 1024:.1f}MB 超出上限 {current_app.config['MAX_UPLOAD_MB']}MB"
        )

    # 第 4 层：UUID 重命名 + 相对路径入库
    storage = get_storage()
    meta = storage.save(stream, user.id, ext)

    # 同一用户重复上传同一份文件：删掉刚落盘的新文件，避免磁盘里堆垃圾
    duplicate = db.session.execute(
        select(Resume).where(Resume.user_id == user.id, Resume.sha256 == meta["sha256"])
    ).scalar_one_or_none()
    if duplicate is not None:
        storage.delete(meta["rel_path"])
        raise ConflictError(f"该文件与已有简历「{duplicate.original_name}」内容完全相同，无需重复上传")

    has_default = default_resume(user.id) is not None
    record = Resume(
        user_id=user.id,
        original_name=filename[:255],
        stored_name=meta["stored_name"],
        rel_path=meta["rel_path"],
        ext=ext,
        mime=MIME_BY_EXT[ext],
        size_bytes=meta["size_bytes"],
        sha256=meta["sha256"],
        is_default=(set_default or not has_default),  # 第一份自动成为默认简历
    )
    db.session.add(record)
    db.session.commit()
    return record


def set_default(resume: Resume) -> Resume:
    """默认简历唯一性：单事务内先清零再置 1。

    MySQL 没有部分唯一索引、SQLite 更不支持，因此用事务 + 应用层约束换取可测试性；
    单用户场景下并发窗口可忽略（README 已写明取舍）。
    """
    db.session.execute(
        Resume.__table__.update().where(Resume.user_id == resume.user_id).values(is_default=False)
    )
    resume.is_default = True
    db.session.commit()
    return resume


def delete(resume: Resume) -> None:
    """删除记录 + 磁盘文件。关联投递记录的 resume_id 由 DB 置 NULL。"""
    rel_path = resume.rel_path
    db.session.delete(resume)
    db.session.commit()
    get_storage().delete(rel_path)


def open_stream(resume: Resume):
    storage = get_storage()
    if not storage.exists(resume.rel_path):
        raise BusinessError("简历文件已丢失，请重新上传", status_code=404)
    return storage.open(resume.rel_path)
