"""统一异常处理。

两套响应形态：
- 浏览器请求 → 中文错误页（保留导航，用户能自己走回去）；
- 带 ``Accept: application/json`` 或是 API 路由 → JSON，避免前端拿到一坨 HTML。
"""

from __future__ import annotations

import logging

from flask import current_app, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from app.utils.errors import BusinessError

logger = logging.getLogger(__name__)

ERROR_TITLES = {
    400: "请求参数有误",
    401: "请先登录",
    403: "没有访问权限",
    404: "页面不存在",
    405: "请求方式不被允许",
    413: "文件太大了",
    422: "提交的内容不符合要求",
    500: "服务器开小差了",
}

ERROR_HINTS = {
    400: "请检查地址栏或表单内容后重试。",
    401: "登录状态可能已过期，请重新登录。",
    403: "该资源属于其他账号，或你的权限不足。",
    404: "记录可能已被删除，或链接已失效。",
    405: "请返回上一页通过页面按钮操作。",
    413: "单个简历文件不能超过 5MB，请压缩后重新上传。",
    422: "请检查填写内容是否完整、格式是否正确。",
    500: "如果反复出现，请把操作步骤反馈给开发者。",
}


def wants_json() -> bool:
    if request.path.startswith("/stats/data"):
        return True
    best = request.accept_mimetypes.best
    return bool(
        best == "application/json"
        and request.accept_mimetypes[best] > request.accept_mimetypes["text/html"]
    )


def _payload(status: int, message: str, detail: str = ""):
    return {
        "ok": False,
        "error": {
            "status": status,
            "title": ERROR_TITLES.get(status, "出错了"),
            "message": message,
            "hint": detail or ERROR_HINTS.get(status, ""),
        },
    }


def register_error_handlers(app):
    @app.errorhandler(BusinessError)
    def handle_business_error(exc: BusinessError):
        """业务异常：视为「用户可理解」的失败，不写 error 日志。"""
        status = exc.status_code
        if wants_json():
            return jsonify(_payload(status, exc.message)), status
        return (
            render_template(
                "errors/error.html",
                status=status,
                title=ERROR_TITLES.get(status, "操作失败"),
                message=exc.message,
                hint=ERROR_HINTS.get(status, ""),
            ),
            status,
        )

    @app.errorhandler(HTTPException)
    def handle_http_error(exc: HTTPException):
        status = exc.code or 500
        message = ERROR_TITLES.get(status, exc.description or "出错了")
        if status >= 500:
            logger.exception("HTTP %s: %s", status, exc.description)
        if wants_json():
            return jsonify(_payload(status, message)), status
        return (
            render_template(
                "errors/error.html",
                status=status,
                title=message,
                message=exc.description or message,
                hint=ERROR_HINTS.get(status, ""),
            ),
            status,
        )

    @app.errorhandler(Exception)
    def handle_unexpected_error(exc: Exception):
        """兜底：未预期异常记录堆栈，但绝不把堆栈抛给用户。"""
        logger.exception("未处理的异常: %s", exc)
        if current_app.config.get("TESTING") or current_app.debug:
            raise exc
        if wants_json():
            return jsonify(_payload(500, "服务器内部错误")), 500
        return (
            render_template(
                "errors/error.html",
                status=500,
                title=ERROR_TITLES[500],
                message="服务器内部错误",
                hint=ERROR_HINTS[500],
            ),
            500,
        )

    @app.errorhandler(413)
    def handle_too_large(_exc):
        message = f"单个文件不能超过 {app.config['MAX_UPLOAD_MB']}MB"
        if wants_json():
            return jsonify(_payload(413, message)), 413
        return (
            render_template(
                "errors/error.html",
                status=413,
                title=ERROR_TITLES[413],
                message=message,
                hint=ERROR_HINTS[413],
            ),
            413,
        )
