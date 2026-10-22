"""统计模块测试：用已知数据集逐项对账，防止「图好看但数字错」。

对账口径：
- 数据集：3 条投递（已投递 / 面试中 / 已 Offer），其中「面试中」有 1 场通过的面试
- 期望：total=3，viewed(max_stage>=2)=2，interviewed=2，offered=1，
        状态分布 1/1/1，漏斗 3 → 2 → 2 → 1
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.services import stats_service
from app.utils.dtime import today_local
from tests.factories import make_application, make_company, make_interview, make_job_type


@pytest.fixture()
def dataset(app, user):
    company = make_company(user.id, "统计公司")
    backend = make_job_type(user.id, "后端开发岗", color="#5B8FF9")
    frontend = make_job_type(user.id, "前端开发岗", color="#5AD8A6")

    applied = make_application(
        user.id, company.id, position="纯投递", status="applied", max_stage=1,
        days_ago=2, job_type_id=backend.id, channel="boss",
    )
    interviewing = make_application(
        user.id, company.id, position="面试中", status="interviewing", max_stage=3,
        days_ago=5, job_type_id=backend.id, channel="boss",
    )
    make_application(
        user.id, company.id, position="已 Offer", status="offer", max_stage=4,
        days_ago=6, job_type_id=frontend.id, channel="referral",
    )
    make_interview(user.id, interviewing.id, round_name="first", result="passed", days_ago=3)
    return {"company": company, "applied": applied, "interviewing": interviewing}


def _range(days: int = 30):
    end = today_local()
    return end - timedelta(days=days - 1), end


class TestKpi:
    def test_counts(self, app, user, dataset):
        start, end = _range()
        kpi = stats_service.kpi(user.id, start, end)
        assert kpi["total"] == 3
        assert kpi["viewed"] == 2  # max_stage >= 2
        assert kpi["interviewed"] == 2
        assert kpi["offered"] == 1
        assert kpi["interview_rate"] == pytest.approx(66.7, abs=0.1)
        assert kpi["offer_rate"] == pytest.approx(33.3, abs=0.1)

    def test_empty_dataset_returns_zeros(self, app, user):
        start, end = _range()
        kpi = stats_service.kpi(user.id, start, end)
        assert kpi["total"] == 0
        assert kpi["interview_rate"] == 0
        assert kpi["offer_rate"] == 0
        assert kpi["avg_response_days"] == 0


class TestCharts:
    def test_status_distribution_fills_all_states(self, app, user, dataset):
        start, end = _range()
        chart = stats_service.chart_status(user.id, start, end)
        values = {item["name"]: item["value"] for item in chart["data"]}
        # 未出现的状态也要补 0，否则图例会缺项
        assert set(values) == {"已投递", "已查看", "面试中", "已 Offer", "已拒绝", "已放弃"}
        assert values["已投递"] == 1
        assert values["面试中"] == 1
        assert values["已 Offer"] == 1
        assert chart["total"] == 3

    def test_trend_has_continuous_dates(self, app, user, dataset):
        start, end = _range(7)
        chart = stats_service.chart_trend(user.id, start, end)
        assert len(chart["labels"]) == 7  # 无数据的日期补 0，不能跳日
        assert sum(chart["values"]) == 3
        assert chart["granularity"] == "day"

    def test_trend_switches_to_week_for_long_range(self, app, user, dataset):
        start, end = _range(120)
        chart = stats_service.chart_trend(user.id, start, end)
        assert chart["granularity"] == "week"

    def test_funnel_is_monotonic(self, app, user, dataset):
        start, end = _range()
        data = stats_service.chart_funnel(user.id, start, end)["data"]
        values = [item["value"] for item in data]
        assert values == [3, 2, 2, 1]
        assert values == sorted(values, reverse=True)
        assert data[0]["stepRate"] == "100.0%"
        assert data[1]["stepRate"] == "66.7%"

    def test_job_type_includes_zero_and_uncategorized(self, app, user, dataset):
        start, end = _range()
        items = {item["name"]: item["value"] for item in stats_service.chart_job_type(user.id, start, end)["data"]}
        assert items["后端开发岗"] == 2
        assert items["前端开发岗"] == 1

        # 新增一条未分类记录后，应出现「未分类」一栏
        company = dataset["company"]
        make_application(user.id, company.id, position="未分类职位")
        items = {
            item["name"]: item["value"]
            for item in stats_service.chart_job_type(user.id, start, end)["data"]
        }
        assert items["未分类"] == 1

    def test_channel_stacking_sums_to_total(self, app, user, dataset):
        start, end = _range()
        chart = stats_service.chart_channel(user.id, start, end)
        assert set(chart["categories"]) == {"BOSS直聘", "内推"}
        totalled = sum(sum(series["data"]) for series in chart["series"])
        assert totalled == 3

    def test_round_pass_rate(self, app, user, dataset):
        start, end = _range()
        chart = stats_service.chart_round(user.id, start, end)
        assert chart["categories"] == ["一面"]
        assert chart["passRates"][0]["pass_rate"] == 100.0


class TestDetailAndApi:
    def test_detail_rows_content(self, app, user, dataset):
        start, end = _range()
        page = stats_service.detail_page(user.id, start, end)
        assert page["total"] == 3
        first = page["rows"][0]
        assert {"company", "position", "status", "interview_cnt"} <= set(first)

    def test_detail_pagination(self, app, user, dataset):
        start, end = _range()
        page = stats_service.detail_page(user.id, start, end, page=1, per_page=2)
        assert len(page["rows"]) == 2
        assert page["pages"] == 2

    def test_stats_page_renders(self, auth_client, user, dataset):
        response = auth_client.get("/stats")
        assert response.status_code == 200
        assert "投递转化漏斗".encode() in response.data

    def test_stats_data_json(self, auth_client, user, dataset):
        payload = auth_client.get("/stats/data").get_json()
        assert payload["ok"] is True
        assert payload["kpi"]["total"] == 3
        assert set(payload["charts"]) == {"status", "trend", "jobType", "funnel", "channel", "round"}

    def test_csv_export_has_bom_and_rows(self, auth_client, user, dataset):
        response = auth_client.get("/stats/export")
        assert response.status_code == 200
        assert response.data.startswith("\ufeff".encode())  # Excel 打开中文不乱码
        assert "统计公司".encode() in response.data

    def test_invalid_range_falls_back(self, auth_client, user, dataset):
        # start > end 时应回退默认区间而不是报错
        response = auth_client.get("/stats?start=2026-12-31&end=2026-01-01")
        assert response.status_code == 200


class TestIsolation:
    def test_stats_only_count_own_data(self, app, user, other_user, dataset):
        other_company = make_company(other_user.id, "别人公司")
        make_application(other_user.id, other_company.id, status="offer", max_stage=4)

        start, end = _range()
        assert stats_service.kpi(user.id, start, end)["total"] == 3
        assert stats_service.kpi(other_user.id, start, end)["total"] == 1
