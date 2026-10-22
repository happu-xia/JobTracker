"""时间工具：统一使用「目标时区的 naive datetime」入库。

为什么不用 UTC：
- 本项目是单机单时区（Asia/Shanghai）的求职记录，用户看到的「今天投递」必须等于本地自然日；
- DATETIME 存储 naive 本地时间，``DATE(applied_at)`` 分组即自然日，不依赖 MySQL 的时区表
  （Windows 上 CONVERT_TZ 常因未导入 tzinfo 而返回 NULL）。

代价：不支持多时区用户。这是有意取舍，README 中已说明。
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

DEFAULT_TZ = "Asia/Shanghai"
# Windows 版 Python 不自带 IANA 时区库，未安装 tzdata 时 ZoneInfo 会抛异常；
# 兜底成固定 UTC+8（中国无夏令时，等价）
_FALLBACK_TZ = timezone(timedelta(hours=8))


@lru_cache(maxsize=4)
def get_tz(name: str | None = None):
    try:
        return ZoneInfo(name or os.getenv("APP_TIMEZONE") or DEFAULT_TZ)
    except Exception:  # 时区名非法 / 缺 tzdata 时绝不让程序起不来
        return _FALLBACK_TZ


def now_local() -> datetime:
    """当前本地时间（naive，秒级精度）。

    直接读环境变量而非 current_app，保证模型默认值在无应用上下文时也可用。
    """
    return datetime.now(get_tz()).replace(tzinfo=None, microsecond=0)


def today_local() -> date:
    return now_local().date()


def to_naive(dt: datetime | None) -> datetime | None:
    """把带时区的 datetime 转成本地 naive。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(get_tz()).replace(tzinfo=None)


def parse_date(value: str | None, default: date | None = None) -> date | None:
    """解析 ``YYYY-MM-DD``；非法值返回 default 而不抛异常（筛选条件容错）。"""
    if not value:
        return default
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        return default


def resolve_range(
    start_str: str | None,
    end_str: str | None,
    *,
    default_days: int = 30,
    max_days: int = 365,
) -> tuple[date, date]:
    """解析统计口径的日期区间，异常输入统一回退到默认区间。

    规则：
    - 缺省 end → 今天；缺省 start → end - (default_days - 1)，保证「近 30 天」含今天共 30 天；
    - start > end 或跨度超 max_days → 回退默认区间（防止一条 URL 拉爆全表）。
    """
    end = parse_date(end_str, today_local())
    start = parse_date(start_str, end - timedelta(days=default_days - 1))

    if start > end or (end - start).days + 1 > max_days:
        end = today_local()
        start = end - timedelta(days=default_days - 1)
    return start, end


def date_range(start: date, end: date) -> list[date]:
    """生成闭区间内的连续日期序列（用于把 SQL 缺省日期补 0）。"""
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def month_range(start: date, end: date) -> list[str]:
    """生成 ``YYYY-MM`` 月份序列。"""
    result: list[str] = []
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        result.append(cursor.strftime("%Y-%m"))
        cursor = date(cursor.year + (cursor.month // 12), (cursor.month % 12) + 1, 1)
    return result


def days_between(start: datetime | None, end: datetime | None) -> int | None:
    """两个 naive datetime 相差的自然日数，任一为空返回 None。"""
    if start is None or end is None:
        return None
    delta = end.date() - start.date()
    return max(delta.days, 0)


def humanize_dt(dt: datetime | None) -> str:
    """模板过滤器：把时间渲染成「今天 14:30 / 3天前 / 2026-03-01」。"""
    if dt is None:
        return "—"
    now = now_local()
    diff = (now.date() - dt.date()).days
    if diff == 0:
        return f"今天 {dt:%H:%M}"
    if diff == 1:
        return f"昨天 {dt:%H:%M}"
    if 1 < diff <= 30:
        return f"{diff} 天前"
    return f"{dt:%Y-%m-%d}"
