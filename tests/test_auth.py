"""认证模块测试：注册、哈希、登录、改密、访问控制。"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.extensions import db
from app.models.job_type import JobType
from app.services import auth_service
from app.utils.errors import BusinessError, ConflictError, ValidationError


class TestRegister:
    def test_creates_user_with_scrypt_hash(self, app):
        user = auth_service.register("alice", "Alice@Example.com", "secret123")
        assert user.id is not None
        assert user.password_hash.startswith("scrypt:")  # 加盐哈希，不可逆
        assert "secret123" not in user.password_hash
        assert user.email == "alice@example.com"  # 邮箱统一小写

    def test_seeds_default_job_types(self, app):
        user = auth_service.register("bob", "bob@example.com", "secret123")
        types = db.session.execute(select(JobType).where(JobType.user_id == user.id)).scalars().all()
        assert len(types) == 5
        assert {t.name for t in types} == {
            "后端开发",
            "前端开发",
            "算法/数据",
            "产品/运营",
            "测试/运维",
        }

    def test_duplicate_username_or_email_rejected(self, app):
        auth_service.register("carol", "carol@example.com", "secret123")
        with pytest.raises(ConflictError):
            auth_service.register("carol", "another@example.com", "secret123")
        with pytest.raises(ConflictError):
            auth_service.register("carol2", "carol@example.com", "secret123")

    def test_short_password_rejected(self, app):
        with pytest.raises(ValidationError):
            auth_service.register("dave", "dave@example.com", "123")


class TestAuthenticate:
    def test_login_by_username_and_email(self, app, user):
        assert auth_service.authenticate("tester", "secret123").id == user.id
        assert auth_service.authenticate("tester@example.com", "secret123").id == user.id
        assert auth_service.authenticate("TESTER", "secret123").id == user.id

    def test_wrong_password_message_is_generic(self, app, user):
        with pytest.raises(BusinessError) as wrong_password:
            auth_service.authenticate("tester", "wrong")
        with pytest.raises(BusinessError) as no_user:
            auth_service.authenticate("nobody", "secret123")
        # 用户不存在与密码错误返回同一提示，避免账号枚举
        assert wrong_password.value.message == no_user.value.message == "账号或密码错误"

    def test_last_login_recorded(self, app, user):
        auth_service.authenticate("tester", "secret123")
        db.session.refresh(user)
        assert user.last_login_at is not None


class TestChangePassword:
    def test_change_and_verify(self, app, user):
        auth_service.change_password(user, "secret123", "newsecret")
        assert user.check_password("newsecret") is True
        assert user.check_password("secret123") is False

    def test_wrong_old_password(self, app, user):
        with pytest.raises(BusinessError):
            auth_service.change_password(user, "bad", "newsecret")

    def test_same_password_rejected(self, app, user):
        with pytest.raises(BusinessError):
            auth_service.change_password(user, "secret123", "secret123")


class TestRoutes:
    def test_protected_route_redirects_to_login(self, client):
        response = client.get("/applications", follow_redirects=False)
        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_login_page_renders(self, client):
        assert client.get("/auth/login").status_code == 200
        assert client.get("/auth/register").status_code == 200

    def test_login_then_reach_dashboard(self, client, user):
        response = client.post(
            "/auth/login",
            data={"account": "tester", "password": "secret123"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "看板".encode() in response.data

    def test_logout_clears_session(self, auth_client):
        assert auth_client.get("/").status_code == 200
        auth_client.post("/auth/logout", follow_redirects=True)
        assert auth_client.get("/", follow_redirects=False).status_code == 302

    def test_open_redirect_blocked(self, client, user):
        """next 参数只允许站内路径，防止被用作开放重定向。"""
        response = client.post(
            "/auth/login?next=https://evil.example.com/steal",
            data={"account": "tester", "password": "secret123"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/")
