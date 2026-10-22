"""本地磁盘文件存储适配器。

职责边界：只管「字节怎么安全落盘/读回」，不关心业务（谁能上传、多大、什么类型）。
这样以后要换成 OSS/S3，只需再写一个同接口的类，Service 层代码不动。
"""

from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from pathlib import Path
from typing import BinaryIO

from app.utils.security import safe_join

CHUNK_SIZE = 64 * 1024


class LocalFileStorage:
    """按 ``<root>/<user_id>/<stored_name>`` 组织文件。"""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    # ---------- 目录 ----------
    def ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def user_dir(self, user_id: int) -> Path:
        path = self.root / str(user_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    # ---------- 写 ----------
    def save(self, stream: BinaryIO, user_id: int, ext: str) -> dict:
        """流式写入（分块读，避免一次性把文件读进内存）。

        先写 ``.part`` 临时文件再 os.replace 原子改名：
        中途异常不会留下一个「看起来正常但内容残缺」的简历文件。
        """
        self.ensure_root()
        target_dir = self.user_dir(user_id)
        stored_name = f"{uuid.uuid4().hex}.{ext}"
        target = target_dir / stored_name
        tmp = target.with_suffix(target.suffix + ".part")

        digest = hashlib.sha256()
        size = 0
        stream.seek(0)
        try:
            with open(tmp, "wb") as fh:
                while True:
                    chunk = stream.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    size += len(chunk)
                    digest.update(chunk)
                    fh.write(chunk)
            os.replace(tmp, target)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

        return {
            "stored_name": stored_name,
            "rel_path": f"{user_id}/{stored_name}",
            "size_bytes": size,
            "sha256": digest.hexdigest(),
        }

    # ---------- 读 ----------
    def path_of(self, rel_path: str) -> Path:
        """相对路径 → 绝对路径，并强制校验没有逃逸出根目录。"""
        return safe_join(self.root, rel_path)

    def open(self, rel_path: str) -> BinaryIO:
        return open(self.path_of(rel_path), "rb")

    def exists(self, rel_path: str) -> bool:
        try:
            return self.path_of(rel_path).is_file()
        except ValueError:
            return False

    # ---------- 删 ----------
    def delete(self, rel_path: str) -> bool:
        try:
            target = self.path_of(rel_path)
        except ValueError:
            return False
        try:
            target.unlink()
            return True
        except FileNotFoundError:
            return False
        except OSError:
            return False

    def remove_user_dir(self, user_id: int) -> None:
        shutil.rmtree(self.root / str(user_id), ignore_errors=True)
