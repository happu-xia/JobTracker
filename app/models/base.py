"""模型公共基元：主键类型、时间戳 Mixin、按量级选窄类型。

跨库兼容要点：
- MySQL 用 ``BIGINT UNSIGNED`` 做主键；但 SQLite 的 AUTOINCREMENT 要求列类型严格为
  ``INTEGER``（BIGINT PRIMARY KEY 不是 rowid 别名，插入会因主键为 NULL 失败）。
  因此用 ``with_variant`` 在 sqlite 方言下退化为 Integer，让同一套模型在测试库也能跑。
- 时间戳同时给 DB 侧默认值（见迁移脚本）与 ORM 侧默认值：MySQL 支持
  ON UPDATE CURRENT_TIMESTAMP，SQLite 不支持，两边以 ORM 为准才能行为一致。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, SmallInteger
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.utils.dtime import now_local


def pk_type():
    """主键/外键类型（每次调用返回新实例，避免类型对象共享）。"""
    return (
        BigInteger()
        .with_variant(mysql.BIGINT(unsigned=True), "mysql")
        .with_variant(Integer(), "sqlite")
    )


def fk_type():
    """外键类型，必须与 pk_type 完全一致，否则 MySQL 报 errno 3780。"""
    return pk_type()


def small_uint():
    """薪资等小整数字段，按量级选窄类型（SMALLINT 足够表示 0~65535K/月）。"""
    return SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql")


class TimestampMixin:
    """创建/更新时间。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_local, nullable=False, comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_local, onupdate=now_local, nullable=False, comment="更新时间"
    )
