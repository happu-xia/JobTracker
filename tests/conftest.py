"""pytest 公共夹具。

三个关键点：
1. 测试库用 SQLite 内存库（``sqlite://``），与 MySQL 共用同一套 ORM 模型；
2. **必须打开 SQLite 外键约束**，否则级联删除测试会「假通过」；
3. 上传目录指向 tmp_path，测试不污染真实的 D:\\JobTrackerData。
"""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app import create_app
from app.extensions import db as _db
from app.models.user import User


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    """SQLite 默认关闭外键，不打开的话 ON DELETE CASCADE 根本不生效。"""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


@pytest.fixture()
def app(tmp_path):
    application = create_app("testing")
    upload_root = tmp_path / "uploads"
    upload_root.mkdir(parents=True, exist_ok=True)
    application.config.update(
        UPLOAD_ROOT=upload_root,
        MAX_UPLOAD_MB=5,
        ITEMS_PER_PAGE=5,
    )

    with application.app_context():
        _db.create_all()
        yield application
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def user(app):
    """默认测试用户（直接建，不走注册流程以缩短用例耗时）。"""
    from app.services import auth_service

    return auth_service.register("tester", "tester@example.com", "secret123")


@pytest.fixture()
def other_user(app):
    from app.services import auth_service

    return auth_service.register("other", "other@example.com", "secret123")


@pytest.fixture()
def auth_client(client, user):
    """已登录的客户端：直接调用登录接口，走真实的会话建立路径。"""
    response = client.post(
        "/auth/login",
        data={"account": user.username, "password": "secret123"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    return client


@pytest.fixture()
def make_pdf_bytes():
    def _factory(text: str = "JobTracker Test Resume") -> bytes:
        # 只需要满足魔数校验，内容不必是结构完整的 PDF
        return b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n% " + text.encode() + b"\n%%EOF"

    return _factory


@pytest.fixture()
def db_session(app):
    return _db.session


@pytest.fixture(autouse=True)
def _clean_session(app):
    """每个用例结束后清掉会话，避免残留对象影响下一个用例。"""
    yield
    _db.session.remove()


def login(client, username="tester", password="secret123"):
    return client.post(
        "/auth/login", data={"account": username, "password": password}, follow_redirects=False
    )


__all__ = ["app", "client", "user", "auth_client", "login", "User"]
