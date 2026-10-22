"""职位类型测试：自定义维护、停用语义、被引用禁删、排序。"""

from __future__ import annotations

import pytest

from app.services import job_type_service
from app.utils.errors import ConflictError, NotFoundError, ValidationError
from tests.factories import make_application, make_company, make_job_type


class TestCreate:
    def test_auto_sort_order(self, app, user):
        """新建类型排在既有类型之后，且步长为 10（注册时已预置 5 个默认类型）。"""
        first = job_type_service.create(user.id, {"name": "自动排序甲", "color": "#112233"})
        second = job_type_service.create(user.id, {"name": "自动排序乙", "color": "#445566"})
        assert second.sort_order - first.sort_order == 10

        pairs = job_type_service.list_with_usage(user.id)
        orders = [item.sort_order for item, _ in pairs]
        assert orders == sorted(orders)  # 排序稳定不插队
        assert pairs[-1][0].id == second.id

    @pytest.mark.parametrize("color", ["red", "#12345", "#GGGGGG", "112233"])
    def test_invalid_color_rejected(self, app, user, color):
        with pytest.raises(ValidationError):
            job_type_service.create(user.id, {"name": "非法颜色", "color": color})

    def test_color_lowercased(self, app, user):
        item = job_type_service.create(user.id, {"name": "大写颜色", "color": "#AABBCC"})
        assert item.color == "#aabbcc"

    def test_duplicate_name_rejected(self, app, user):
        job_type_service.create(user.id, {"name": "算法/"})
        with pytest.raises(ConflictError):
            job_type_service.create(user.id, {"name": "算法/"})

    def test_negative_sort_order_rejected(self, app, user):
        with pytest.raises(ValidationError):
            job_type_service.create(user.id, {"name": "负数排序", "sort_order": -1})


class TestToggle:
    def test_inactive_not_offered_for_new_application(self, app, user):
        item = job_type_service.create(user.id, {"name": "将停用"})
        job_type_service.toggle(item)
        assert item.is_active is False
        assert all(t.id != item.id for t in job_type_service.active_types(user.id))

    def test_toggle_back(self, app, user):
        item = job_type_service.create(user.id, {"name": "来回切换"})
        job_type_service.toggle(item)
        job_type_service.toggle(item)
        assert item.is_active is True


class TestMove:
    def test_move_up_swaps_neighbour(self, app, user):
        a = job_type_service.create(user.id, {"name": "A"})
        b = job_type_service.create(user.id, {"name": "B"})
        # 新建的 A、B 位于末尾，上移 B 应与 A 交换位置
        assert [item.name for item, _ in job_type_service.list_with_usage(user.id)][-2:] == ["A", "B"]

        job_type_service.move(b, -1)

        ordered = [item.name for item, _ in job_type_service.list_with_usage(user.id)]
        assert ordered[-2:] == ["B", "A"]

    def test_move_at_boundary_is_noop(self, app, user):
        item = job_type_service.create(user.id, {"name": "边界类型"})
        before = [(obj.id, obj.sort_order) for obj, _ in job_type_service.list_with_usage(user.id)]

        job_type_service.move(item, 1)  # 已在最后，继续下移应原样返回

        after = [(obj.id, obj.sort_order) for obj, _ in job_type_service.list_with_usage(user.id)]
        assert after == before


class TestDelete:
    def test_delete_when_unused(self, app, user):
        item = job_type_service.create(user.id, {"name": "没人用的类型"})
        removed_id = item.id
        job_type_service.delete(item)
        assert all(obj.id != removed_id for obj, _ in job_type_service.list_with_usage(user.id))

    def test_delete_blocked_when_referenced(self, app, user):
        item = job_type_service.create(user.id, {"name": "被引用类型"})
        company = make_company(user.id, "某公司")
        make_application(user.id, company.id, job_type_id=item.id)

        with pytest.raises(ConflictError) as exc:
            job_type_service.delete(item)
        assert "1 条投递记录引用" in exc.value.message

    def test_usage_count_reported(self, app, user):
        item = job_type_service.create(user.id, {"name": "统计引用"})
        company = make_company(user.id, "某公司")
        make_application(user.id, company.id, job_type_id=item.id)
        make_application(user.id, company.id, position="另一个", job_type_id=item.id)

        pairs = dict((obj.name, count) for obj, count in job_type_service.list_with_usage(user.id))
        assert pairs["统计引用"] == 2


class TestIsolation:
    def test_other_user_cannot_touch_mine(self, app, user, other_user):
        mine = make_job_type(user.id, "我的类型")
        with pytest.raises(NotFoundError):
            job_type_service.get_or_404(other_user.id, mine.id)


class TestRoutes:
    def test_list_page_renders(self, auth_client, user):
        make_job_type(user.id, "自建后端开发")
        response = auth_client.get("/job-types")
        assert response.status_code == 200
        assert "自建后端开发".encode() in response.data

    def test_delete_referenced_shows_warning(self, auth_client, user):
        item = make_job_type(user.id, "被引用")
        company = make_company(user.id, "某公司")
        make_application(user.id, company.id, job_type_id=item.id)

        response = auth_client.post(f"/job-types/{item.id}/delete", follow_redirects=True)
        assert response.status_code == 200
        assert "无法删除".encode() in response.data
