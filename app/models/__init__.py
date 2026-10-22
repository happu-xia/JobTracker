"""模型统一导出。

Alembic autogenerate 依赖「所有模型都已被 import」才能看到完整 metadata，
因此这里集中 import 一遍，其他模块只需 ``from app import models``。
"""

from __future__ import annotations

from app.models.application import Application
from app.models.company import Company
from app.models.interview import Interview
from app.models.job_type import JobType
from app.models.resume import Resume
from app.models.user import User

__all__ = ["User", "Company", "JobType", "Resume", "Application", "Interview"]
