"""自定义 WTForms 校验器。

复用的校验逻辑放这里，表单里只写一行 ``validators=[HttpUrl()]``，
避免每个表单各写一份「补 https 前缀」的重复代码。
"""

from __future__ import annotations

import re

from wtforms.validators import ValidationError

from app.utils.url import InvalidUrlError, normalize_url

COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")


class HttpUrl:
    """校验并「就地规范化」URL：把 www.x.com 补成 https://www.x.com。"""

    def __init__(self, message: str | None = None, max_length: int = 255):
        self.message = message
        self.max_length = max_length

    def __call__(self, form, field):
        raw = (field.data or "").strip()
        if not raw:
            field.data = None
            return
        try:
            field.data = normalize_url(raw, max_length=self.max_length)
        except InvalidUrlError as exc:
            raise ValidationError(self.message or str(exc)) from exc


class ColorHex:
    def __init__(self, message: str = "颜色必须是 #RRGGBB 格式"):
        self.message = message

    def __call__(self, form, field):
        value = (field.data or "").strip()
        if value and not COLOR_PATTERN.match(value):
            raise ValidationError(self.message)
