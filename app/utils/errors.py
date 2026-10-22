"""业务异常体系。

为什么不用 ``abort(400)``：视图层需要区分「用户可读的业务失败」与「真正的程序错误」。
业务失败应该带着中文提示回到列表页（flash），程序错误才走 500 页面。
"""

from __future__ import annotations


class BusinessError(Exception):
    """业务规则不满足，可安全展示给用户。"""

    status_code = 422

    def __init__(self, message: str, *, status_code: int | None = None, field: str | None = None):
        super().__init__(message)
        self.message = message
        self.field = field
        if status_code is not None:
            self.status_code = status_code

    def __str__(self) -> str:  # pragma: no cover - 仅用于日志
        return self.message


class NotFoundError(BusinessError):
    """资源不存在，或存在但不属于当前用户（越权一律当不存在，避免探测）。"""

    status_code = 404

    def __init__(self, message: str = "记录不存在或无权访问"):
        super().__init__(message, status_code=404)


class PermissionError_(BusinessError):
    status_code = 403

    def __init__(self, message: str = "没有权限执行该操作"):
        super().__init__(message, status_code=403)


class ConflictError(BusinessError):
    """唯一约束冲突、被引用不可删除等。"""

    status_code = 409


class ValidationError(BusinessError):
    status_code = 422
