"""投递记录测试：状态机、max_stage 单调性、筛选、分页、N+1。"""

from __future__ import annotations

import pytest
from sqlalchemy import event

from app.extensions import db
from app.services import application_service
from app.utils.errors import BusinessError, NotFoundError, ValidationError
from tests.factories import make_application, make_company, make_interview, make_job_type


@pytest.fixture()
def company(app, user):
    return make_company(user.id, "测试科技")


class TestStateMachine:
    @pytest.mark.parametrize(
        ("start", "target"),
        [
            ("applied", "viewed"),
            ("applied", "interviewing"),
            ("viewed", "interviewing"),
            ("viewed", "offer"),
            ("interviewing", "offer"),
            ("interviewing", "rejected"),
            ("offer", "withdrawn"),
            ("rejected", "withdrawn"),
        ],
    )
    def test_legal_transitions(self, app, user, company, start, target):
        app_obj = make_application(user.id, company.id, status=start, max_stage=max(1, _stage(start)))
        application_service.transition(app_obj, target)
        assert app_obj.status == target

    @pytest.mark.parametrize(
        ("start", "target"),
        [
            ("offer", "applied"),
            ("withdrawn", "viewed"),
            ("rejected", "interviewing"),
            ("applied", "offer"),
        ],
    )
    def test_illegal_transitions_rejected(self, app, user, company, start, target):
        app_obj = make_application(user.id, company.id, status=start, max_stage=1)
        with pytest.raises(BusinessError):
            application_service.transition(app_obj, target)
        assert app_obj.status == start  # 状态未被静默修改

    def test_max_stage_never_regresses(self, app, user, company):
        """拿到 Offer 后被拒，历史最高阶段仍应保留 4，否则漏斗会算错。"""
        app_obj = make_application(user.id, company.id, status="offer", max_stage=4)
        application_service.transition(app_obj, "withdrawn")
        assert app_obj.max_stage == 4

    def test_first_viewed_and_response_days(self, app, user, company):
        app_obj = make_application(user.id, company.id, status="applied", days_ago=3)
        application_service.transition(app_obj, "viewed")
        assert app_obj.first_viewed_at is not None
        assert app_obj.response_days == 3


class TestCreateUpdate:
    def test_create_sets_stage_from_status(self, app, user, company):
        app_obj = application_service.create(
            user.id,
            {
                "company_id": company.id,
                "position_name": "Java 后端",
                "channel": "boss",
                "status": "interviewing",
                "applied_at": None,
            },
        )
        assert app_obj.max_stage == 3
        assert app_obj.first_viewed_at is not None

    def test_salary_order_validated(self, app, user, company):
        with pytest.raises(ValidationError):
            application_service.create(
                user.id,
                {
                    "company_id": company.id,
                    "position_name": "倒挂薪资",
                    "salary_min": 30,
                    "salary_max": 10,
                },
            )

    def test_inactive_job_type_rejected_on_create(self, app, user, company):
        item = make_job_type(user.id, "已停用类型", is_active=False)
        with pytest.raises(ValidationError):
            application_service.create(
                user.id,
                {"company_id": company.id, "position_name": "职位", "job_type_id": item.id},
            )

    def test_other_users_company_rejected(self, app, other_user, company):
        with pytest.raises(ValidationError):
            application_service.create(
                other_user.id, {"company_id": company.id, "position_name": "越权"}
            )

    def test_invalid_channel_rejected(self, app, user, company):
        with pytest.raises(ValidationError):
            application_service.create(
                user.id,
                {"company_id": company.id, "position_name": "职位", "channel": "unknown"},
            )


class TestQuery:
    def test_status_and_interview_filters(self, app, user, company):
        a = make_application(user.id, company.id, position="有面试", status="interviewing", max_stage=3)
        make_application(user.id, company.id, position="无面试", status="applied")
        make_interview(user.id, a.id)

        assert application_service.list_applications(user.id, status="interviewing").total == 1
        assert application_service.list_applications(user.id, has_interview="yes").total == 1
        assert application_service.list_applications(user.id, has_interview="no").total == 1

    def test_keyword_searches_position_and_company(self, app, user, company):
        other = make_company(user.id, "字节跳动")
        make_application(user.id, company.id, position="推荐算法")
        make_application(user.id, other.id, position="后端开发")

        assert application_service.list_applications(user.id, q="推荐").total == 1
        assert application_service.list_applications(user.id, q="字节").total == 1

    def test_date_range_filter_is_inclusive(self, app, user, company):
        make_application(user.id, company.id, days_ago=0)
        make_application(user.id, company.id, days_ago=10, position="十天前")

        from app.utils.dtime import today_local

        today = today_local().isoformat()
        assert application_service.list_applications(user.id, date_from=today, date_to=today).total == 1

    def test_pagination(self, app, user, company):
        for i in range(12):
            make_application(user.id, company.id, position=f"职位{i}")
        page1 = application_service.list_applications(user.id, page=1, per_page=5)
        assert len(page1.items) == 5 and page1.total == 12
        page3 = application_service.list_applications(user.id, page=3, per_page=5)
        assert len(page3.items) == 2

    def test_status_counts(self, app, user, company):
        make_application(user.id, company.id, status="applied")
        make_application(user.id, company.id, status="offer", max_stage=4)
        counts = application_service.status_counts(user.id)
        assert counts["applied"] == 1
        assert counts["offer"] == 1

    def test_list_query_count_is_constant(self, app, user, company):
        """列表页 SQL 条数不应随行数增长（N+1 回归测试）。"""
        for i in range(8):
            make_application(user.id, company.id, position=f"职位{i}")

        statements: list[str] = []

        def _count(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        engine = db.engine
        event.listen(engine, "before_cursor_execute", _count)
        try:
            result = application_service.list_applications(user.id, page=1, per_page=8)
            assert len(result.items) == 8
        finally:
            event.remove(engine, "before_cursor_execute", _count)

        # 主查询 + count；joinedload 的多对一关联不额外发 SQL
        assert len(statements) <= 3, statements


class TestIsolation:
    def test_other_user_cannot_read(self, app, user, other_user, company):
        mine = make_application(user.id, company.id)
        with pytest.raises(NotFoundError):
            application_service.get_or_404(other_user.id, mine.id)

    def test_list_only_returns_own_records(self, app, user, other_user, company):
        make_application(user.id, company.id, position="我的")
        theirs_company = make_company(other_user.id, "别人的公司")
        make_application(other_user.id, theirs_company.id, position="别人的")

        page = application_service.list_applications(user.id)
        assert page.total == 1
        assert page.items[0].position_name == "我的"


class TestRoutes:
    def test_list_and_detail_render(self, auth_client, user, company):
        app_obj = make_application(user.id, company.id)

        assert auth_client.get("/applications").status_code == 200
        detail = auth_client.get(f"/applications/{app_obj.id}")
        assert detail.status_code == 200
        assert app_obj.position_name.encode() in detail.data

    def test_status_change_via_route(self, auth_client, user, company):
        app_obj = make_application(user.id, company.id, status="applied")
        response = auth_client.post(
            f"/applications/{app_obj.id}/status", data={"status": "viewed"}, follow_redirects=True
        )
        assert response.status_code == 200
        db.session.refresh(app_obj)
        assert app_obj.status == "viewed"

    def test_illegal_status_change_flashes_error(self, auth_client, user, company):
        app_obj = make_application(user.id, company.id, status="applied")
        response = auth_client.post(
            f"/applications/{app_obj.id}/status", data={"status": "offer"}, follow_redirects=True
        )
        assert "不能从".encode() in response.data

    def test_new_page_redirects_when_no_company(self, auth_client, user):
        response = auth_client.get("/applications/new", follow_redirects=False)
        assert response.status_code == 302
        assert "/companies/new" in response.headers["Location"]

    def test_delete_route(self, auth_client, user, company):
        app_obj = make_application(user.id, company.id)
        auth_client.post(f"/applications/{app_obj.id}/delete", follow_redirects=True)
        assert application_service.status_counts(user.id) == {}


def _stage(status: str) -> int:
    return {"applied": 1, "viewed": 2, "interviewing": 3, "offer": 4}.get(status, 1)
