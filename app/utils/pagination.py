"""分页视图对象：把 Flask-SQLAlchemy 的 Pagination 转成模板友好的结构。

模板里不该出现 ``pagination.iter_pages`` 之类的框架 API 细节，
统一在这里算好「上一页/下一页/页码窗口」，模板只做渲染。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

from flask import request


@dataclass
class Pagination:
    items: list[Any]
    page: int
    per_page: int
    total: int
    pages: int
    args: dict[str, Any] = field(default_factory=dict)

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def prev_page(self) -> int:
        return max(self.page - 1, 1)

    @property
    def next_page(self) -> int:
        return min(self.page + 1, self.pages)

    @property
    def first_index(self) -> int:
        """当前页第一条的全局序号（从 1 开始），用于「共 N 条，当前 1-20」。"""
        return 0 if not self.total else (self.page - 1) * self.per_page + 1

    @property
    def last_index(self) -> int:
        return min(self.page * self.per_page, self.total)

    def page_numbers(self, window: int = 2) -> list[int | None]:
        """返回页码列表，``None`` 表示省略号。"""
        if self.pages <= 1:
            return [1] if self.pages == 1 else []
        pages: list[int | None] = []
        start = max(1, self.page - window)
        end = min(self.pages, self.page + window)
        if start > 1:
            pages.append(1)
            if start > 2:
                pages.append(None)
        pages.extend(range(start, end + 1))
        if end < self.pages:
            if end < self.pages - 1:
                pages.append(None)
            pages.append(self.pages)
        return pages

    def url_for_page(self, page: int) -> str:
        """保留当前全部查询参数，只替换 page（筛选与分页不互相打断）。"""
        params = {k: v for k, v in self.args.items() if v not in (None, "")}
        params["page"] = page
        return f"{request.path}?{urlencode(params)}"

    @classmethod
    def from_flask(cls, pagination, args: dict[str, Any] | None = None) -> "Pagination":
        return cls(
            items=list(pagination.items),
            page=pagination.page,
            per_page=pagination.per_page,
            total=pagination.total,
            pages=pagination.pages or 0,
            args=args or {},
        )
