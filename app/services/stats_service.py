"""统计服务：6 张图 + 指标卡 + 明细汇总。

设计原则
--------
1. **一条 SQL 出多个指标**：``SUM(CASE WHEN ...)`` 条件聚合，把首页 6 项指标压成 1 次查询。
2. **漏斗靠 max_stage**：``SUM(max_stage >= N)`` 天然是「到达过第 N 层的数量」，
   不受终态（rejected/withdrawn）影响 —— 这正是引入阶段字段的原因。
3. **缺省日期补 0 在 Python 做**：SQL 只返回有数据的日期，连续日期序列由 Python 生成，
   否则折线图会「跳日」看起来像断线。
4. **跨库安全**：只用 ``COUNT/SUM/AVG/DATE/LEFT JOIN`` 这类 MySQL 与 SQLite 都支持的语法，
   日期相减已在写入时落库为 ``response_days``，避免 ``TIMESTAMPDIFF`` 的方言差异。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import joinedload, selectinload

from app.extensions import db
from app.models.application import Application
from app.models.company import Company
from app.models.interview import Interview
from app.models.job_type import JobType
from app.models.resume import Resume
from app.utils.constants import (
    CHANNEL_LABELS,
    RESULT_COLORS,
    RESULT_FAILED,
    RESULT_LABELS,
    RESULT_PASSED,
    RESULT_PENDING,
    ROUND_LABELS,
    ROUND_ORDER,
    STAGE_APPLIED,
    STAGE_INTERVIEWED,
    STAGE_OFFERED,
    STAGE_VIEWED,
    STATUS_COLORS,
    STATUS_LABELS,
    STATUS_ORDER,
    UNCATEGORIZED_COLOR,
    UNCATEGORIZED_LABEL,
)
from app.utils.dtime import date_range, now_local

ONE_DAY = timedelta(days=1)


def _bounds(start: date, end: date) -> tuple[datetime, datetime]:
    """半开区间 [start 00:00, end+1 00:00)，含首含尾且不受时分秒影响。"""
    return datetime.combine(start, time.min), datetime.combine(end + ONE_DAY, time.min)


def _ratio(numerator: float, denominator: float) -> float:
    return round(numerator / denominator * 100, 1) if denominator else 0.0


def _pct(numerator: float, denominator: float) -> str:
    return f"{_ratio(numerator, denominator):.1f}%"


# ------------------------------------------------------------------ 指标卡
def _kpi_row(user_id: int, start: date, end: date) -> dict:
    start_dt, end_dt = _bounds(start, end)
    last7 = now_local() - timedelta(days=7)

    stmt = select(
        func.count(Application.id),
        func.sum(case((Application.max_stage >= STAGE_VIEWED, 1), else_=0)),
        func.sum(case((Application.max_stage >= STAGE_INTERVIEWED, 1), else_=0)),
        func.sum(case((Application.max_stage >= STAGE_OFFERED, 1), else_=0)),
        func.sum(case((Application.status == "rejected", 1), else_=0)),
        func.sum(case((Application.status == "withdrawn", 1), else_=0)),
        func.avg(Application.response_days),
        func.sum(case((Application.applied_at >= last7, 1), else_=0)),
    ).where(
        Application.user_id == user_id,
        Application.applied_at >= start_dt,
        Application.applied_at < end_dt,
    )

    row = db.session.execute(stmt).one()
    total = int(row[0] or 0)
    return {
        "total": total,
        "viewed": int(row[1] or 0),
        "interviewed": int(row[2] or 0),
        "offered": int(row[3] or 0),
        "rejected": int(row[4] or 0),
        "withdrawn": int(row[5] or 0),
        "avg_response_days": round(float(row[6]), 1) if row[6] is not None else 0.0,
        "last7": int(row[7] or 0),
    }


def kpi(user_id: int, start: date, end: date) -> dict:
    raw = _kpi_row(user_id, start, end)
    return {
        **raw,
        "interview_rate": _ratio(raw["interviewed"], raw["total"]),
        "offer_rate": _ratio(raw["offered"], raw["total"]),
        "pending": raw["total"] - raw["rejected"] - raw["withdrawn"],
        "avg_response_days": raw["avg_response_days"],
    }


# ------------------------------------------------------------------ 图 1 状态分布
def chart_status(user_id: int, start: date, end: date) -> dict:
    start_dt, end_dt = _bounds(start, end)
    stmt = (
        select(Application.status, func.count(Application.id))
        .where(
            Application.user_id == user_id,
            Application.applied_at >= start_dt,
            Application.applied_at < end_dt,
        )
        .group_by(Application.status)
    )
    counted = {row[0]: int(row[1]) for row in db.session.execute(stmt)}

    data = [
        {
            "name": STATUS_LABELS[status],
            "value": counted.get(status, 0),
            "itemStyle": {"color": STATUS_COLORS[status]},
        }
        for status in STATUS_ORDER
    ]
    return {"title": "投递状态分布", "total": sum(item["value"] for item in data), "data": data}


# ------------------------------------------------------------------ 图 2 投递趋势
def chart_trend(user_id: int, start: date, end: date) -> dict:
    """跨度 > 62 天自动按周聚合，避免 365 个点挤成一条线。"""
    start_dt, end_dt = _bounds(start, end)
    days = (end - start).days + 1
    by_week = days > 62

    day_col = func.date(Application.applied_at)
    stmt = (
        select(day_col, func.count(Application.id))
        .where(
            Application.user_id == user_id,
            Application.applied_at >= start_dt,
            Application.applied_at < end_dt,
        )
        .group_by(day_col)
        .order_by(day_col)
    )
    rows = db.session.execute(stmt).all()

    # 不同方言返回 date 或 str，统一成 date
    counted: dict[date, int] = {}
    for value, count in rows:
        if isinstance(value, datetime):
            key = value.date()
        elif isinstance(value, date):
            key = value
        else:
            key = date.fromisoformat(str(value)[:10])
        counted[key] = counted.get(key, 0) + int(count)

    if by_week:
        labels: list[str] = []
        values: list[int] = []
        cursor = start
        while cursor <= end:
            week_end = min(cursor + timedelta(days=6), end)
            total = sum(counted.get(cursor + timedelta(days=i), 0) for i in range((week_end - cursor).days + 1))
            labels.append(f"{cursor:%m-%d}~{week_end:%m-%d}")
            values.append(total)
            cursor = week_end + ONE_DAY
        granularity = "week"
    else:
        labels = [f"{d:%m-%d}" for d in date_range(start, end)]
        values = [counted.get(d, 0) for d in date_range(start, end)]
        granularity = "day"

    return {
        "title": "投递趋势",
        "granularity": granularity,
        "labels": labels,
        "values": values,
        "total": sum(values),
        "peak": max(values) if values else 0,
    }


# ------------------------------------------------------------------ 图 3 职位类型
def chart_job_type(user_id: int, start: date, end: date) -> dict:
    """LEFT JOIN 的时间条件必须写在 ON 里：写进 WHERE 会把外连接退化成内连接，
    零投递的职位类型会直接从图里消失。
    """
    start_dt, end_dt = _bounds(start, end)

    stmt = (
        select(
            JobType.id,
            JobType.name,
            JobType.color,
            func.count(Application.id).label("cnt"),
        )
        .outerjoin(
            Application,
            and_(
                Application.job_type_id == JobType.id,
                Application.user_id == user_id,
                Application.applied_at >= start_dt,
                Application.applied_at < end_dt,
            ),
        )
        .where(JobType.user_id == user_id)
        .group_by(JobType.id, JobType.name, JobType.color, JobType.sort_order)
        .order_by(func.count(Application.id).desc(), JobType.sort_order)
        .limit(10)
    )

    items = [
        {"name": row[1], "value": int(row[3]), "itemStyle": {"color": row[2]}}
        for row in db.session.execute(stmt)
    ]

    # 「未分类」不在 job_types 表里，单独补一条，否则各分类之和会小于总投递数
    uncategorized = db.session.execute(
        select(func.count(Application.id)).where(
            Application.user_id == user_id,
            Application.job_type_id.is_(None),
            Application.applied_at >= start_dt,
            Application.applied_at < end_dt,
        )
    ).scalar_one()
    if uncategorized:
        items.append(
            {
                "name": UNCATEGORIZED_LABEL,
                "value": int(uncategorized),
                "itemStyle": {"color": UNCATEGORIZED_COLOR},
            }
        )

    return {"title": "职位类型分布", "data": items}


# ------------------------------------------------------------------ 图 4 转化漏斗
def chart_funnel(user_id: int, start: date, end: date) -> dict:
    raw = _kpi_row(user_id, start, end)
    layers = [
        (STAGE_APPLIED, "投递", raw["total"]),
        (STAGE_VIEWED, "被查看", raw["viewed"]),
        (STAGE_INTERVIEWED, "进面试", raw["interviewed"]),
        (STAGE_OFFERED, "拿 Offer", raw["offered"]),
    ]

    data = []
    for index, (_stage, name, value) in enumerate(layers):
        prev = layers[index - 1][2] if index > 0 else value
        data.append(
            {
                "name": name,
                "value": value,
                "stepRate": _pct(value, prev) if index > 0 else "100.0%",
                "overallRate": _pct(value, raw["total"]),
            }
        )
    return {"title": "投递转化漏斗", "data": data}


# ------------------------------------------------------------------ 图 5 渠道效果
def chart_channel(user_id: int, start: date, end: date) -> dict:
    """四段按 max_stage 互斥切分，直接堆叠即为总量，前端不用做减法。"""
    start_dt, end_dt = _bounds(start, end)
    stmt = (
        select(
            Application.channel,
            func.sum(case((Application.max_stage == STAGE_APPLIED, 1), else_=0)).label("applied"),
            func.sum(case((Application.max_stage == STAGE_VIEWED, 1), else_=0)).label("viewed"),
            func.sum(case((Application.max_stage == STAGE_INTERVIEWED, 1), else_=0)).label("interviewed"),
            func.sum(case((Application.max_stage == STAGE_OFFERED, 1), else_=0)).label("offered"),
            func.count(Application.id).label("total"),
        )
        .where(
            Application.user_id == user_id,
            Application.applied_at >= start_dt,
            Application.applied_at < end_dt,
        )
        .group_by(Application.channel)
        .order_by(func.count(Application.id).desc())
    )

    rows = list(db.session.execute(stmt))
    categories = [CHANNEL_LABELS.get(row[0], row[0]) for row in rows]
    series = [
        {"name": "仅投递", "key": "applied", "color": "#5B8FF9", "data": [int(r[1] or 0) for r in rows]},
        {"name": "被查看", "key": "viewed", "color": "#5AD8A6", "data": [int(r[2] or 0) for r in rows]},
        {"name": "进面试", "key": "interviewed", "color": "#F6BD16", "data": [int(r[3] or 0) for r in rows]},
        {"name": "拿 Offer", "key": "offered", "color": "#FF4D4F", "data": [int(r[4] or 0) for r in rows]},
    ]
    samples = {CHANNEL_LABELS.get(r[0], r[0]): int(r[5]) for r in rows}
    return {"title": "投递渠道效果", "categories": categories, "series": series, "samples": samples}


# ------------------------------------------------------------------ 图 6 面试轮次
def chart_round(user_id: int, start: date, end: date) -> dict:
    start_dt, end_dt = _bounds(start, end)
    stmt = (
        select(Interview.round, Interview.result, func.count(Interview.id))
        .join(Application, Application.id == Interview.application_id)
        .where(
            Interview.user_id == user_id,
            Application.applied_at >= start_dt,
            Application.applied_at < end_dt,
        )
        .group_by(Interview.round, Interview.result)
    )

    table: dict[str, dict[str, int]] = {}
    for round_name, result, count in db.session.execute(stmt):
        bucket = table.setdefault(round_name, {RESULT_PENDING: 0, RESULT_PASSED: 0, RESULT_FAILED: 0})
        bucket[result] = int(count)

    rounds = [r for r in ROUND_ORDER if r in table] or []
    categories = [ROUND_LABELS[r] for r in rounds]

    def series_of(result: str) -> list[int]:
        return [table.get(r, {}).get(result, 0) for r in rounds]

    passes = [
        {
            "round": ROUND_LABELS[r],
            "total": sum(table[r].values()),
            "pass_rate": _ratio(
                table[r].get(RESULT_PASSED, 0),
                table[r].get(RESULT_PASSED, 0) + table[r].get(RESULT_FAILED, 0),
            ),
        }
        for r in rounds
    ]

    return {
        "title": "面试轮次与结果",
        "categories": categories,
        "series": [
            {"name": RESULT_LABELS[RESULT_PASSED], "color": RESULT_COLORS[RESULT_PASSED], "data": series_of(RESULT_PASSED)},
            {"name": RESULT_LABELS[RESULT_PENDING], "color": RESULT_COLORS[RESULT_PENDING], "data": series_of(RESULT_PENDING)},
            {"name": RESULT_LABELS[RESULT_FAILED], "color": RESULT_COLORS[RESULT_FAILED], "data": series_of(RESULT_FAILED)},
        ],
        "passRates": passes,
    }


# ------------------------------------------------------------------ 汇总
def build_stats(user_id: int, start: date, end: date) -> dict:
    """一次性组装统计页需要的全部数据（6 图 + 指标卡），供 /stats/data 直接返回。"""
    return {
        "range": {"start": start.isoformat(), "end": end.isoformat(), "days": (end - start).days + 1},
        "kpi": kpi(user_id, start, end),
        "charts": {
            "status": chart_status(user_id, start, end),
            "trend": chart_trend(user_id, start, end),
            "jobType": chart_job_type(user_id, start, end),
            "funnel": chart_funnel(user_id, start, end),
            "channel": chart_channel(user_id, start, end),
            "round": chart_round(user_id, start, end),
        },
    }


def detail_rows(user_id: int, start: date, end: date, *, limit: int | None = None, offset: int = 0):
    """明细汇总：一次 JOIN 预加载，面试统计在 Python 聚合（每页最多 20 行，代价可忽略）。"""
    start_dt, end_dt = _bounds(start, end)
    stmt = (
        select(Application)
        .where(
            Application.user_id == user_id,
            Application.applied_at >= start_dt,
            Application.applied_at < end_dt,
        )
        .options(
            joinedload(Application.company),
            joinedload(Application.job_type),
            joinedload(Application.resume),
            selectinload(Application.interviews),
        )
        .order_by(Application.applied_at.desc(), Application.id.desc())
    )
    if limit is not None:
        stmt = stmt.limit(limit).offset(offset)

    rows = db.session.execute(stmt).unique().scalars().all()
    result = []
    for app in rows:
        interviews = list(app.interviews)
        passed = sum(1 for i in interviews if i.result == RESULT_PASSED)
        pending = sum(1 for i in interviews if i.result == RESULT_PENDING)
        result.append(
            {
                "obj": app,
                "company": app.company.name if app.company else "—",
                "position": app.position_name,
                "job_type": app.job_type.name if app.job_type else UNCATEGORIZED_LABEL,
                "job_type_color": app.job_type.color if app.job_type else UNCATEGORIZED_COLOR,
                "channel": CHANNEL_LABELS.get(app.channel, app.channel),
                "status": STATUS_LABELS.get(app.status, app.status),
                "status_color": STATUS_COLORS.get(app.status, "#909399"),
                "applied_at": app.applied_at,
                "stage": app.max_stage,
                "response_days": app.response_days,
                "interview_cnt": len(interviews),
                "passed_cnt": passed,
                "pending_cnt": pending,
                "resume": app.resume.original_name if app.resume else "—",
            }
        )
    return result


def detail_page(user_id: int, start: date, end: date, *, page: int = 1, per_page: int = 20):
    """明细分页：先 count 再取当页，避免一次拉全表。"""
    start_dt, end_dt = _bounds(start, end)
    total = db.session.execute(
        select(func.count(Application.id)).where(
            Application.user_id == user_id,
            Application.applied_at >= start_dt,
            Application.applied_at < end_dt,
        )
    ).scalar_one()

    rows = detail_rows(user_id, start, end, limit=per_page, offset=(max(page, 1) - 1) * per_page)
    pages = (total + per_page - 1) // per_page if total else 0
    return {"rows": rows, "total": int(total), "page": max(page, 1), "per_page": per_page, "pages": pages}


# ------------------------------------------------------------------ 看板
def dashboard(user_id: int) -> dict:
    """首页看板：近 30 天指标 + 7 天趋势 + 状态分布 + 最近投递。"""
    end = now_local().date()
    start = end - timedelta(days=29)
    return {
        "kpi": kpi(user_id, start, end),
        "trend": chart_trend(user_id, end - timedelta(days=6), end),
        "status": chart_status(user_id, start, end),
        "funnel": chart_funnel(user_id, start, end),
        "range": {"start": start.isoformat(), "end": end.isoformat()},
    }
