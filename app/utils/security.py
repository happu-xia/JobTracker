"""文件安全：魔数校验、安全路径拼接、中文文件名下载。

为什么自己做魔数校验而不用 python-magic：
Windows 上 python-magic 依赖 libmagic DLL，装不上就直接拖垮演示；
而简历只允许 PDF/DOC/DOCX 三种，签名检查足够且零依赖。
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from urllib.parse import quote

from .constants import OLE2_MAGIC, PDF_MAGIC, ZIP_MAGIC

READ_SIZE = 8192


def read_head(stream: io.BufferedIOBase, size: int = 8) -> bytes:
    """读取文件头若干字节并复位指针。"""
    pos = stream.tell()
    head = stream.read(size)
    stream.seek(pos)
    return head or b""


def is_pdf(stream: io.BufferedIOBase) -> bool:
    return read_head(stream, len(PDF_MAGIC)) == PDF_MAGIC


def is_ole2_doc(stream: io.BufferedIOBase) -> bool:
    """老版 .doc 是 OLE2 复合文档。"""
    return read_head(stream, len(OLE2_MAGIC)) == OLE2_MAGIC


def is_docx(stream: io.BufferedIOBase) -> bool:
    """docx 是 zip 容器，且内部必须有 word/document.xml。

    只判断 PK 头不够：任何 zip 都能通过。必须进容器看目录。
    """
    head = read_head(stream, 4)
    if head != ZIP_MAGIC:
        return False

    pos = stream.tell()
    try:
        stream.seek(0)
        raw = stream.read()
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = set(zf.namelist())
    except (zipfile.BadZipFile, OSError, ValueError):
        return False
    finally:
        stream.seek(pos)

    return "word/document.xml" in names


SIGNATURE_CHECKERS = {
    "pdf": is_pdf,
    "doc": is_ole2_doc,
    "docx": is_docx,
}


def verify_signature(stream: io.BufferedIOBase, ext: str) -> bool:
    """校验文件真实类型是否与扩展名匹配。"""
    checker = SIGNATURE_CHECKERS.get(ext.lower())
    if checker is None:
        return False
    return checker(stream)


def safe_join(root: Path, rel_path: str) -> Path:
    """把相对路径拼到根目录下，并断言结果没有逃逸出根目录。

    三重防护的第二重：即便 rel_path 被污染成 ``../../windows/system32``，
    这里也会直接抛 ValueError，而不是真去读系统文件。
    """
    root_resolved = root.resolve()
    candidate = (root_resolved / rel_path).resolve()
    if not candidate.is_relative_to(root_resolved):
        raise ValueError("非法的文件路径")
    return candidate


def content_disposition(filename: str) -> str:
    """生成兼容中文文件名的 Content-Disposition（RFC 5987）。

    Werkzeug 的 send_file 对非 ASCII 文件名会做处理，但老版本/老浏览器表现不一，
    这里显式给出 filename + filename* 双保险。
    """
    fallback = filename.encode("ascii", "ignore").decode("ascii") or "resume"
    fallback = fallback.replace('"', "").replace("\\", "")
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename)}"


def human_size(num_bytes: int | None) -> str:
    """模板过滤器：字节数转可读大小。"""
    if not num_bytes:
        return "0 B"
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"
