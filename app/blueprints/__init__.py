"""蓝图注册。"""

from __future__ import annotations

from flask import Flask


def register_blueprints(app: Flask) -> None:
    from app.blueprints.applications import bp as applications_bp
    from app.blueprints.auth import bp as auth_bp
    from app.blueprints.companies import bp as companies_bp
    from app.blueprints.interviews import bp as interviews_bp
    from app.blueprints.job_types import bp as job_types_bp
    from app.blueprints.main import bp as main_bp
    from app.blueprints.resumes import bp as resumes_bp
    from app.blueprints.stats import bp as stats_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(companies_bp)
    app.register_blueprint(applications_bp)
    app.register_blueprint(interviews_bp)
    app.register_blueprint(resumes_bp)
    app.register_blueprint(job_types_bp)
    app.register_blueprint(stats_bp)
