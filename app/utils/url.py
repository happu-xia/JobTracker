"""URL 规范化与校验。

企业官网、JD 链接这类「用户手输 URL」有三个常见坑：
1. 用户只填 ``www.xxx.com``，浏览器跳到相对路径 → 必须补协议；
2. 用户填 ``javascript:alert(1)`` 或 ``data:text/html,...`` 形成 XSS 载体 → 必须拒绝非 http(s)；
3. 超长字符串直接入库 → 截断/限制。
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

BLOCKED_SCHEMES = {"javascript", "data", "vbscript", "file", "about", "jar"}

MAX_URL_LENGTH = 255


class InvalidUrlError(ValueError):
    """URL 非法（由表单校验器转换为中文错误提示）。"""


def normalize_url(raw: str | None, *, max_length: int = MAX_URL_LENGTH) -> str | None:
    """把用户输入规范成可安全渲染的 http(s) URL；空输入返回 None。

    >>> normalize_url("www.tencent.com")
    'https://www.tencent.com'
    >>> normalize_url("  HTTP://a.com/x?y=1  ")
    'http://a.com/x?y=1'
    """
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None

    if len(value) > max_length:
        raise InvalidUrlError(f"链接长度不能超过 {max_length} 个字符")

    # 含冒号但协议被拦 → 直接拒绝（不要自作主张补 https:// 变成怪 URL）
    if ":" in value.split("/", 1)[0]:
        scheme = value.split(":", 1)[0].strip().lower()
        if scheme in BLOCKED_SCHEMES:
            raise InvalidUrlError("不支持该链接协议，请填写以 http:// 或 https:// 开头的地址")
        if scheme not in {"http", "https"}:
            raise InvalidUrlError("链接必须以 http:// 或 https:// 开头")

    if not value.lower().startswith(("http://", "https://")):
        # 裸域名 / 裸路径统一补 https://
        value = "https://" + value.lstrip("/")

    parts = urlsplit(value)
    if not parts.netloc or "." not in parts.netloc:
        raise InvalidUrlError("链接格式不正确，例如 https://www.example.com")
    if any(ch.isspace() for ch in value):
        raise InvalidUrlError("链接中不能包含空格")

    # 协议与主机统一小写，其余原样（path/query 大小写敏感）
    port = f":{parts.port}" if parts.port else ""
    netloc = parts.hostname.lower() + port if parts.hostname else parts.netloc
    return urlunsplit((parts.scheme.lower(), netloc, parts.path, parts.query, parts.fragment))


def display_url(url: str | None) -> str:
    """展示用：去掉协议前缀，省出表格宽度。"""
    if not url:
        return ""
    return url.split("://", 1)[1] if "://" in url else url


def host_of(url: str | None) -> str:
    """取主机名，用于「打开官网」按钮的 title 与 favicon 猜测。"""
    if not url:
        return ""
    try:
        return urlsplit(url).hostname or ""
    except ValueError:
        return ""
