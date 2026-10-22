"""应用工厂。

为什么用工厂函数而不是模块级全局 app：
1. 测试可传入 ``testing`` 配置，得到互相隔离的实例；
2. 扩展对象只 init_app 一次，避免循环导入；
3. waitress / flask cli / pytest 三种入口共用同一套装配逻辑。
"""

from __future__ import annotations

import logging
from pathlib import Path

from flask import Flask, jsonify, request

from app.extensions import csrf, db, login_manager, migrate
from config import get_config


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(get_config(config_name))

    _ensure_dirs(app)
    _register_extensions(app)
    _register_blueprints(app)
    _register_error_handlers(app)
    _register_template_helpers(app)
    _register_cli(app)
    _configure_logging(app)

    @app.get("/healthz")
    def healthz():
        """健康检查：同时探数据库与上传目录，便于启动脚本判断是否就绪。"""
        db_ok, db_error = True, ""
        try:
            db.session.execute(db.text("SELECT 1"))
        except Exception as exc:  # pragma: no cover - 仅在库不可用时触发
            db_ok, db_error = False, str(exc)[:200]
            db.session.rollback()

        upload_root = Path(app.config["UPLOAD_ROOT"] or "")
        upload_ok = upload_root.is_dir() and _is_writable(upload_root)

        status = 200 if (db_ok and upload_ok) else 503
        return (
            jsonify(
                {
                    "ok": status == 200,
                    "database": {"ok": db_ok, "error": db_error},
                    "upload_root": {"path": str(upload_root), "ok": upload_ok},
                    "version": "1.0.0",
                }
            ),
            status,
        )

    return app


def _is_writable(path: Path) -> bool:
    probe = path / ".write_probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def _ensure_dirs(app: Flask) -> None:
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    upload_root = app.config.get("UPLOAD_ROOT")
    if upload_root:
        app.config["UPLOAD_ROOT"] = Path(upload_root)
        app.config["UPLOAD_ROOT"].mkdir(parents=True, exist_ok=True)


def _register_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db, directory=str(Path(app.root_path).parent / "migrations"))
    login_manager.init_app(app)
    csrf.init_app(app)

    # 触发模型注册（Alembic autogenerate 需要完整 metadata）
    from app import models  # noqa: F401


def _register_blueprints(app: Flask) -> None:
    from app.blueprints import register_blueprints

    register_blueprints(app)


def _register_error_handlers(app: Flask) -> None:
    from app.errors.handlers import register_error_handlers

    register_error_handlers(app)


def _register_template_helpers(app: Flask) -> None:
    from app.utils import constants
    from app.utils.dtime import humanize_dt, now_local
    from app.utils.security import human_size
    from app.utils.url import display_url, host_of

    app.jinja_env.filters["humanize"] = humanize_dt
    app.jinja_env.filters["filesize"] = human_size
    app.jinja_env.filters["urlhost"] = display_url
    app.jinja_env.filters["dt"] = lambda value, fmt="%Y-%m-%d %H:%M": value.strftime(fmt) if value else "—"
    app.jinja_env.filters["d"] = lambda value, fmt="%Y-%m-%d": value.strftime(fmt) if value else "—"
    app.jinja_env.filters["nl2br"] = lambda value: (value or "").replace("\n", "<br>")

    app.jinja_env.globals.update(
        STATUS_LABELS=constants.STATUS_LABELS,
        STATUS_COLORS=constants.STATUS_COLORS,
        STATUS_BADGES=constants.STATUS_BADGES,
        STATUS_ORDER=constants.STATUS_ORDER,
        CHANNEL_LABELS=constants.CHANNEL_LABELS,
        ROUND_LABELS=constants.ROUND_LABELS,
        RESULT_LABELS=constants.RESULT_LABELS,
        RESULT_BADGES=constants.RESULT_BADGES,
        RESULT_COLORS=constants.RESULT_COLORS,
        SCALE_LABELS=constants.SCALE_LABELS,
        INDUSTRY_OPTIONS=constants.INDUSTRY_OPTIONS,
        SORT_OPTIONS=constants.SORT_OPTIONS,
        STAGE_LABELS=constants.STAGE_LABELS,
        host_of=host_of,
        now_local=now_local,
        app_name="JobTracker",
    )

    @app.context_processor
    def inject_nav():
        """给导航栏提供当前模块标识，避免每个模板手写 active 类。"""
        endpoint = request.endpoint or ""
        section = endpoint.split(".")[0] if "." in endpoint else ""
        return {"active_section": section}

    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response


def _register_cli(app: Flask) -> None:
    from app.cli import register_cli

    register_cli(app)


def _configure_logging(app: Flask) -> None:
    if app.config.get("TESTING"):
        return
    level = logging.DEBUG if app.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    app.logger.setLevel(level)
