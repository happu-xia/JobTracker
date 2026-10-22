"""Flask CLI 扩展：初始化表结构、灌演示数据、统计冒烟。"""

from __future__ import annotations

from datetime import timedelta

import click
from flask import Flask
from flask.cli import with_appcontext

from app.extensions import db


def register_cli(app: Flask) -> None:
    @app.cli.command("init-db")
    @with_appcontext
    def init_db():
        """按模型直接建表（首次跑通的最短路径；正式演进用 flask db upgrade）。"""
        db.create_all()
        tables = ", ".join(sorted(db.metadata.tables))
        click.echo(f"表结构创建完成：{tables}")

    @app.cli.command("seed-demo")
    @click.option("--reset", is_flag=True, help="先清空 demo 账号的旧数据")
    @with_appcontext
    def seed_demo(reset: bool):
        """生成演示数据：demo / demo1234。"""
        from app.services.seed_service import seed_demo_data

        stats = seed_demo_data(reset=reset)
        click.echo(
            "演示数据就绪："
            f"用户 {stats['user']}，企业 {stats['companies']}，"
            f"投递 {stats['applications']}，面试 {stats['interviews']}，"
            f"简历 {stats['resumes']}"
        )

    @app.cli.command("stats-smoke")
    @with_appcontext
    def stats_smoke():
        """冒烟：对一个用户跑一遍全部统计查询，确认没有方言/语法问题。"""
        from app.models.user import User
        from app.services import stats_service
        from app.utils.dtime import today_local

        user = db.session.execute(db.select(User)).scalars().first()
        if user is None:
            click.echo("数据库里还没有用户，先执行 flask seed-demo")
            return

        end = today_local()
        result = stats_service.build_stats(user.id, end - timedelta(days=29), end)
        click.echo(f"KPI: {result['kpi']}")
        for key, chart in result["charts"].items():
            click.echo(f"  {key}: ok")
