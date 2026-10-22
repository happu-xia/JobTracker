"""扩展单例与应用级声明基类。

把 db / migrate / login_manager / csrf 放在这里（而不是 app/__init__.py），
是为了让 models、services、blueprints 都能安全地 ``from app.extensions import db``，
彻底避免「应用工厂 ↔ 模型」的循环导入。
"""

from __future__ import annotations

from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# 统一约束命名：否则 Alembic autogenerate 会因匿名约束名反复生成 drop/create
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


db = SQLAlchemy(model_class=Base)
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()

login_manager.login_view = "auth.login"
login_manager.login_message = "请先登录后再操作"
login_manager.login_message_category = "warning"
login_manager.session_protection = "basic"


@login_manager.user_loader
def load_user(user_id: str):  # pragma: no cover - 由 Flask-Login 调用
    from app.models.user import User

    return db.session.get(User, int(user_id)) if user_id and user_id.isdigit() else None
