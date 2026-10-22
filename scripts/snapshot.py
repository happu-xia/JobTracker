"""开发辅助：把登录后的页面导出为静态 HTML 快照，便于本地截图检查版式。

只在开发时用：python scripts/snapshot.py
产物写到 .preview/（已在 .gitignore 中忽略），资源路径会被改写成 file:// 绝对路径。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402

PAGES_STATIC = {
    "dashboard": "/",
    "applications": "/applications",
    "companies": "/companies",
    "resumes": "/resumes",
    "job_types": "/job-types",
    "stats": "/stats",
    "login": "/auth/login",
}


def dynamic_pages(app) -> dict[str, str]:
    """详情页的 id 每次重建数据都会变，这里动态取真实 id。"""
    from app.extensions import db
    from app.models.application import Application
    from app.models.company import Company

    with app.app_context():
        app_id = db.session.execute(db.select(Application.id).limit(1)).scalar()
        company_id = db.session.execute(db.select(Company.id).limit(1)).scalar()
    pages = {}
    if app_id:
        pages["application_detail"] = f"/applications/{app_id}"
    if company_id:
        pages["company_detail"] = f"/companies/{company_id}"
    return pages


def main() -> None:
    out_dir = ROOT / ".preview"
    out_dir.mkdir(exist_ok=True)
    static_uri = (ROOT / "app" / "static").as_uri()

    app = create_app("development")
    app.config["WTF_CSRF_ENABLED"] = False
    app.config["TESTING"] = True

    pages = dict(PAGES_STATIC)
    pages.update(dynamic_pages(app))

    client = app.test_client()
    client.post("/auth/login", data={"account": "demo", "password": "demo1234"})

    for name, path in pages.items():
        html = client.get(path).get_data(as_text=True)
        html = html.replace('"/static/', f'"{static_uri}/')
        target = out_dir / f"{name}.html"
        target.write_text(html, encoding="utf-8")
        print(f"wrote {target.name} ({len(html)} chars)")


if __name__ == "__main__":
    main()
