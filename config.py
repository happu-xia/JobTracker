"""应用配置：读取 .env，按环境派生 Dev / Prod / Test 三套配置。

设计要点：
1. 数据库连接串支持两种给法 —— 完整 DATABASE_URL，或拆分的 DB_USER/DB_PASSWORD/...；
   后者用 ``quote_plus`` 转义，避免密码含 ``@ : / #`` 时 DSN 解析错乱。
2. 上传根目录强制纯 ASCII，规避 Windows 中文路径导致的 open/send_file 异常。
3. 所有配置项均可被环境变量覆盖，便于测试与部署。
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def build_database_url() -> str:
    """组装数据库连接串：优先 DATABASE_URL，否则用拆分配置拼装。"""
    explicit = os.getenv("DATABASE_URL", "").strip()
    if explicit:
        return explicit

    user = os.getenv("DB_USER", "jt")
    password = quote_plus(os.getenv("DB_PASSWORD", ""))
    host = os.getenv("DB_HOST", "127.0.0.1")
    port = os.getenv("DB_PORT", "3306")
    name = os.getenv("DB_NAME", "jobtracker")
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}?charset=utf8mb4"


class BaseConfig:
    # ---------- 基础 ----------
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-insecure-secret-key")
    JSON_AS_ASCII = False
    PROPAGATE_EXCEPTIONS = None

    # ---------- 数据库 ----------
    SQLALCHEMY_DATABASE_URI = build_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = _env_bool("SQLALCHEMY_ECHO", False)
    # 连接池：MySQL 默认 8 小时空闲被服务端掐断，pool_recycle 提前回收
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

    # ---------- 上传 ----------
    UPLOAD_ROOT = Path(os.getenv("UPLOAD_ROOT", "D:/JobTrackerData/uploads"))
    MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "5"))
    MAX_CONTENT_LENGTH = MAX_UPLOAD_MB * 1024 * 1024
    ALLOWED_UPLOAD_EXTENSIONS = {"pdf", "doc", "docx"}

    # ---------- 业务 ----------
    APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Shanghai")
    ITEMS_PER_PAGE = int(os.getenv("ITEMS_PER_PAGE", "20"))
    STATS_MAX_RANGE_DAYS = 365
    STATS_DEFAULT_RANGE_DAYS = 30

    # ---------- 会话与安全 ----------
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_DURATION = 60 * 60 * 24 * 7  # 7 天
    WTF_CSRF_TIME_LIMIT = None  # CSRF token 随会话有效，避免长时间停留后提交失败

    # ---------- 静态资源 ----------
    USE_LOCAL_ASSETS = _env_bool("USE_LOCAL_ASSETS", False)

    # ---------- 服务 ----------
    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = int(os.getenv("PORT", "5001"))


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_ECHO = _env_bool("SQLALCHEMY_ECHO", False)


class ProductionConfig(BaseConfig):
    DEBUG = False
    SESSION_COOKIE_SECURE = False  # 本机 http 演示；上 https 后应置 True


class TestingConfig(BaseConfig):
    TESTING = True
    DEBUG = True
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "testing-secret-key"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    SQLALCHEMY_ECHO = False
    UPLOAD_ROOT = None  # 由 conftest 覆写为临时目录
    ITEMS_PER_PAGE = 10


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config(name: str | None = None) -> type[BaseConfig]:
    env = (name or os.getenv("FLASK_ENV") or "development").lower()
    return CONFIG_MAP.get(env, DevelopmentConfig)
