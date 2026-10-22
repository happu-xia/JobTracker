"""baseline：6 张业务表 + 索引 + 约束

写法说明：这里没有把 DDL 逐条抄成 ``op.create_table(...)``，
而是直接调用模型元数据建表。原因是本迁移是「从零到当前 schema」的基线，
逐条抄写会引入第二份易漂移的 schema 定义；后续任何变更都由
``flask db migrate`` 自动生成增量脚本（那时才会有明细的 add_column 等）。

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-18
"""

from __future__ import annotations

from alembic import op

from app.extensions import db

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    db.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    db.metadata.drop_all(bind=op.get_bind())
