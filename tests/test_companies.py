"""企业库测试：官网链接规范化、唯一约束、删除保护、数据隔离。"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.extensions import db
from app.models.company import Company
from app.services import application_service, company_service
from app.utils.errors import ConflictError, NotFoundError, ValidationError
from tests.factories import make_application, make_company


class TestCreate:
    def test_website_gets_scheme(self, app, user):
        company = company_service.create(user.id, {"name": "腾讯", "website": "www.tencent.com"})
        assert company.website == "https://www.tencent.com"

    def test_javascript_url_rejected(self, app, user):
        with pytest.raises(ValidationError):
            company_service.create(user.id, {"name": "坏公司", "website": "javascript:alert(1)"})

    def test_blank_website_becomes_none(self, app, user):
        company = company_service.create(user.id, {"name": "无官网公司", "website": "   "})
        assert company.website is None

    def test_empty_name_rejected(self, app, user):
        with pytest.raises(ValidationError):
            company_service.create(user.id, {"name": "  "})

    def test_duplicate_name_rejected(self, app, user):
        company_service.create(user.id, {"name": "重名公司"})
        with pytest.raises(ConflictError):
            company_service.create(user.id, {"name": "重名公司"})

    def test_same_name_allowed_for_different_users(self, app, user, other_user):
        company_service.create(user.id, {"name": "同名公司"})
        other = company_service.create(other_user.id, {"name": "同名公司"})
        assert other.id is not None


class TestRead:
    def test_search_and_city_filter(self, app, user):
        make_company(user.id, "深圳腾讯", city="深圳")
        make_company(user.id, "武汉斗鱼", city="武汉")

        page = company_service.list_companies(user.id, q="腾讯")
        assert page.total == 1

        page = company_service.list_companies(user.id, city="武汉")
        assert page.total == 1
        assert page.items[0].name == "武汉斗鱼"

    def test_city_options_distinct(self, app, user):
        make_company(user.id, "A", city="深圳")
        make_company(user.id, "B", city="深圳")
        make_company(user.id, "C", city="武汉")
        options = company_service.city_options(user.id)
        # 去重生效；顺序取决于数据库排序规则（中英文混排时不要断言具体次序）
        assert sorted(options) == sorted(["深圳", "武汉"])
        assert len(options) == 2

    def test_isolation_between_users(self, app, user, other_user):
        mine = make_company(user.id, "我的公司")
        with pytest.raises(NotFoundError):
            company_service.get_or_404(other_user.id, mine.id)


class TestUpdate:
    def test_update_normalizes_url(self, app, user):
        company = make_company(user.id, "待改公司")
        updated = company_service.update(company, {"name": "待改公司", "website": "example.com/jd"})
        assert updated.website == "https://example.com/jd"

    def test_rename_to_existing_name_rejected(self, app, user):
        make_company(user.id, "公司A")
        b = make_company(user.id, "公司B")
        with pytest.raises(ConflictError):
            company_service.update(b, {"name": "公司A"})

    def test_update_self_name_allowed(self, app, user):
        a = make_company(user.id, "公司A")
        updated = company_service.update(a, {"name": "公司A", "city": "武汉"})
        assert updated.city == "武汉"


class TestDelete:
    def test_delete_without_applications(self, app, user):
        company = make_company(user.id, "干净公司")
        assert company_service.delete(company) == 0
        assert db.session.execute(select(Company)).first() is None

    def test_delete_blocked_when_referenced(self, app, user):
        company = make_company(user.id, "有投递公司")
        make_application(user.id, company.id, position="后端")
        with pytest.raises(ConflictError) as exc:
            company_service.delete(company)
        assert "1 条投递记录" in exc.value.message

    def test_force_delete_cascades_applications(self, app, user):
        company = make_company(user.id, "级联公司")
        make_application(user.id, company.id)
        make_application(user.id, company.id, position="前端")

        removed = company_service.delete(company, force=True)
        assert removed == 2
        # 级联删除生效（依赖 SQLite 外键 PRAGMA）
        assert application_service.status_counts(user.id) == {}


class TestRoutes:
    def test_create_via_form(self, auth_client, user):
        response = auth_client.post(
            "/companies/new",
            data={"name": "表单公司", "website": "www.form.com", "city": "武汉"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        company = db.session.execute(select(Company)).scalars().first()
        assert company.website == "https://www.form.com"

    def test_detail_page_shows_website(self, auth_client, user):
        company = make_company(user.id, "详情公司", website="https://detail.com")
        response = auth_client.get(f"/companies/{company.id}")
        assert response.status_code == 200
        assert b"detail.com" in response.data

    def test_cannot_open_other_users_company(self, auth_client, other_user):
        theirs = make_company(other_user.id, "别人的公司")
        response = auth_client.get(f"/companies/{theirs.id}")
        assert response.status_code == 404
