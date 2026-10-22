"""统计蓝图：页面 + JSON 数据接口 + 明细表 + CSV 导出。"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta

from flask import Blueprint, Response, current_app, jsonify, render_template, request
from flask_login import current_user, login_required

from app.services import stats_service
from app.utils.dtime import resolve_range

bp = Blueprint("stats", __name__, url_prefix="/stats")


def _range():
    return resolve_range(
        request.args.get("start"),
        request.args.get("end"),
        default_days=current_app.config["STATS_DEFAULT_RANGE_DAYS"],
        max_days=current_app.config["STATS_MAX_RANGE_DAYS"],
    )


@bp.get("")
@login_required
def index():
    start, end = _range()
    result = stats_service.build_stats(current_user.id, start, end)
    detail = stats_service.detail_page(
        current_user.id, start, end, page=request.args.get("page", 1, type=int)
    )
    days = result["range"]["days"]

    # 快捷区间链接在视图里算好，模板只负责渲染（避免在模板里做日期运算）
    quick_links = [
        {
            "label": f"近 {option} 天",
            "days": option,
            "start": (end - timedelta(days=option - 1)).isoformat(),
            "end": end.isoformat(),
        }
        for option in (7, 30, 90)
    ]

    return render_template(
        "stats/index.html",
        result=result,
        kpi=result["kpi"],
        charts=result["charts"],
        detail=detail,
        start=start,
        end=end,
        days=days,
        quick_links=quick_links,
    )


@bp.get("/data")
@login_required
def data():
    """6 图 + 指标卡一次返回，前端只负责渲染。

    单独出 JSON 接口的意义：日后要做前后端分离或接入移动端，不用重写统计逻辑。
    """
    start, end = _range()
    return jsonify({"ok": True, **stats_service.build_stats(current_user.id, start, end)})


@bp.get("/export")
@login_required
def export_csv():
    """导出明细 CSV。

    带 UTF-8 BOM，否则 Excel 打开中文会乱码 —— 这是实际交付里最常被忽略的一步。
    """
    start, end = _range()
    rows = stats_service.detail_rows(current_user.id, start, end, limit=5000)

    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "企业",
            "职位",
            "职位类型",
            "渠道",
            "状态",
            "投递时间",
            "最高阶段",
            "响应天数",
            "面试场次",
            "面试通过",
            "待定",
            "使用简历",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row["company"],
                row["position"],
                row["job_type"],
                row["channel"],
                row["status"],
                row["applied_at"].strftime("%Y-%m-%d %H:%M"),
                row["stage"],
                row["response_days"] if row["response_days"] is not None else "",
                row["interview_cnt"],
                row["passed_cnt"],
                row["pending_cnt"],
                row["resume"],
            ]
        )

    filename = f"jobtracker_{start:%Y%m%d}_{end:%Y%m%d}.csv"
    return Response(
        buffer.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "X-Generated-At": datetime.now().isoformat(timespec="seconds"),
        },
    )
