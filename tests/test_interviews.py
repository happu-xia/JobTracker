"""面试记录测试：轮次唯一、自动推进状态、级联删除、时间线排序。"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.extensions import db
from app.models.interview import Interview
from app.services import application_service, interview_service
from app.utils.errors import ConflictError, NotFoundError, ValidationError
from app.utils.dtime import now_local
from tests.factories import make_application, make_company, make_interview


@pytest.fixture()
def application(app, user):
    company = make_company(user.id, "面试测试公司")
    return make_application(user.id, company.id, status="applied", max_stage=1)


class TestCreate:
    def test_auto_advances_application(self, app, user, application):
        interview_service.create(
            application,
            {"round": "first", "scheduled_at": now_local(), "result": "pending"},
        )
        assert application.status == "interviewing"
        assert application.max_stage == 3
        assert application.first_viewed_at is not None

    def test_does_not_downgrade_offer(self, app, user):
        """已经拿到 Offer 的记录，补录面试不应把状态改回「面试中」。"""
        company = make_company(user.id, "Offer 公司")
        app_obj = make_application(user.id, company.id, status="offer", max_stage=4)
        interview_service.create(
            app_obj, {"round": "hr", "scheduled_at": now_local(), "result": "passed"}
        )
        assert app_obj.status == "offer"
        assert app_obj.max_stage == 4

    def test_duplicate_round_rejected(self, app, user, application):
        interview_service.create(
            application, {"round": "first", "scheduled_at": now_local(), "result": "pending"}
        )
        with pytest.raises(ConflictError) as exc:
            interview_service.create(
                application, {"round": "first", "scheduled_at": now_local(), "result": "passed"}
            )
        assert "一面" in exc.value.message

    def test_invalid_round_rejected(self, app, user, application):
        with pytest.raises(ValidationError):
            interview_service.create(
                application, {"round": "eighth", "scheduled_at": now_local()}
            )

    def test_invalid_result_rejected(self, app, user, application):
        with pytest.raises(ValidationError):
            interview_service.create(
                application, {"round": "first", "scheduled_at": now_local(), "result": "maybe"}
            )

    def test_missing_scheduled_at_rejected(self, app, user, application):
        with pytest.raises(ValidationError):
            interview_service.create(application, {"round": "first", "scheduled_at": ""})


class TestUpdate:
    def test_update_result_and_feedback(self, app, user, application):
        item = make_interview(user.id, application.id, round_name="first", result="pending")
        updated = interview_service.update(
            item,
            {
                "round": "first",
                "scheduled_at": item.scheduled_at,
                "result": "passed",
                "feedback": "问了索引与事务",
            },
        )
        assert updated.result == "passed"
        assert updated.feedback == "问了索引与事务"

    def test_change_round_conflicts_with_existing(self, app, user, application):
        make_interview(user.id, application.id, round_name="second")
        first = make_interview(user.id, application.id, round_name="first")

        with pytest.raises(ConflictError):
            interview_service.update(
                first,
                {"round": "second", "scheduled_at": first.scheduled_at, "result": "pending"},
            )


class TestDelete:
    def test_delete_interview_keeps_stage(self, app, user, application):
        item = make_interview(user.id, application.id, round_name="first")
        interview_service.delete(item)
        # 历史最高阶段是既成事实，不因删除面试记录而回退
        assert application.max_stage >= 1
        assert db.session.execute(select(func.count(Interview.id))).scalar_one() == 0

    def test_delete_application_cascades_interviews(self, app, user, application):
        make_interview(user.id, application.id, round_name="first")
        make_interview(user.id, application.id, round_name="second")

        application_service.delete(application)
        remaining = db.session.execute(select(func.count(Interview.id))).scalar_one()
        assert remaining == 0  # 依赖数据库 ON DELETE CASCADE


class TestTimeline:
    def test_timeline_ordered_by_time(self, auth_client, user, application):
        make_interview(user.id, application.id, round_name="second", days_ago=1)
        make_interview(user.id, application.id, round_name="first", days_ago=5)

        response = auth_client.get(f"/applications/{application.id}")
        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert html.index("一面") < html.index("二面")


class TestIsolation:
    def test_other_user_cannot_read(self, app, user, other_user, application):
        item = make_interview(user.id, application.id)
        with pytest.raises(NotFoundError):
            interview_service.get_or_404(other_user.id, item.id)


class TestRoutes:
    def test_add_interview_via_form(self, auth_client, user, application):
        response = auth_client.post(
            f"/applications/{application.id}/interviews/new",
            data={
                "round": "first",
                "scheduled_at": now_local().strftime("%Y-%m-%dT%H:%M"),
                "result": "pending",
                "feedback": "线上笔试",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        db.session.refresh(application)
        assert application.status == "interviewing"

    def test_update_result_via_route(self, auth_client, user, application):
        item = make_interview(user.id, application.id, round_name="first")
        auth_client.post(
            f"/applications/{application.id}/interviews/{item.id}/result",
            data={"result": "passed"},
            follow_redirects=True,
        )
        db.session.refresh(item)
        assert item.result == "passed"
