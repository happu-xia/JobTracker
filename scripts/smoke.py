"""端到端冒烟：以真实 HTTP 方式跑一遍「未登录 → 登录 → 浏览全部页面」。

与 pytest 的区别：pytest 走 Flask test client + SQLite，
这里走 waitress + MySQL + 真实 Cookie/CSRF，验证的是部署链路。

    python scripts/smoke.py                 # 默认连 http://127.0.0.1:5001
    python scripts/smoke.py --base http://127.0.0.1:5001 --user demo --password demo1234
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

CSRF_RE = re.compile(r'name="csrf_token"[^>]*value="([^"]+)"')
APP_LINK_RE = re.compile(r'href="/applications/(\d+)"')

# (路径, 期望状态码集合, 断言必须出现的文案)
PAGES: list[tuple[str, set[int], str | None]] = [
    ("/", {200}, "看板"),
    ("/applications", {200}, "投递记录"),
    ("/applications/new", {200}, "记录投递"),
    ("/companies", {200}, "企业库"),
    ("/companies/new", {200}, "添加企业"),
    ("/resumes", {200}, "我的简历"),
    ("/resumes/upload", {200}, "上传简历"),
    ("/job-types", {200}, "职位类型"),
    ("/job-types/new", {200}, "新增职位类型"),
    ("/stats", {200}, "数据统计"),
    ("/stats/data", {200}, None),
    ("/stats/export", {200}, None),
    ("/auth/password", {200}, "修改密码"),
]


class Result:
    def __init__(self) -> None:
        self.failed: list[str] = []

    def check(self, ok: bool, label: str, detail: str = "") -> None:
        print(f"{'[ OK ]' if ok else '[FAIL]'} {label:<34} {detail}")
        if not ok:
            self.failed.append(label)


class Client:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def request(self, path: str, data: dict | None = None) -> tuple[int, bytes, str]:
        url = self.base + path
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        req = urllib.request.Request(url, data=body, method="POST" if body else "GET")
        try:
            with self.opener.open(req, timeout=15) as resp:
                return resp.status, resp.read(), resp.geturl()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read(), url

    def csrf_of(self, html: bytes) -> str | None:
        match = CSRF_RE.search(html.decode("utf-8", "replace"))
        return match.group(1) if match else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:5001")
    parser.add_argument("--user", default="demo")
    parser.add_argument("--password", default="demo1234")
    args = parser.parse_args()

    result = Result()
    client = Client(args.base)
    print(f"目标：{args.base}\n" + "-" * 70)

    # 1. 健康检查
    try:
        status, body, _ = client.request("/healthz")
    except OSError as exc:
        print(f"[FAIL] 服务不可达：{exc}")
        print("       先启动： ./.venv/Scripts/waitress-serve.exe --port=5001 wsgi:app")
        return 1
    payload = json.loads(body or b"{}")
    result.check(status == 200 and payload.get("ok") is True, "健康检查 /healthz", str(payload))

    # 2. 未登录必须被挡回登录页
    status, _, final_url = client.request("/")
    result.check(status == 200 and "/auth/login" in final_url, "未登录访问被重定向", final_url)

    # 3. 登录页可取到 CSRF token
    status, body, _ = client.request("/auth/login")
    token = client.csrf_of(body)
    result.check(status == 200 and token is not None, "登录页 CSRF token", (token or "")[:16] + "...")

    # 4. 错误密码必须失败（防爆破/防枚举）
    if token:
        status, body, _ = client.request(
            "/auth/login",
            {"account": args.user, "password": "definitely-wrong", "csrf_token": token},
        )
        text = body.decode("utf-8", "replace")
        result.check(status == 200 and "账号或密码错误" in text, "错误密码被拒绝")

    # 5. 正确账号登录
    status, body, _ = client.request("/auth/login")
    token = client.csrf_of(body)
    if token:
        status, body, final_url = client.request(
            "/auth/login",
            {
                "account": args.user,
                "password": args.password,
                "csrf_token": token,
                "remember": "y",
            },
        )
        logged_in = "登录" not in final_url and status == 200
        result.check(logged_in, f"登录成功（{args.user}）", final_url)
        if not logged_in:
            print("       账号或密码不对；若演示数据被重置，请重新执行 seed-demo")

    # 6. 逐页巡检
    for path, expected, needle in PAGES:
        status, body, _ = client.request(path)
        text = body.decode("utf-8", "replace")
        ok = status in expected and (needle is None or needle in text)
        result.check(ok, f"页面 {path}", f"{status}" + ("" if ok else f" 期望 {expected} / 含「{needle}」"))

    # 7. 详情页与面试表单依赖真实 id，单独取一条数据验证
    status, body, _ = client.request("/applications")
    match = APP_LINK_RE.search(body.decode("utf-8", "replace"))
    if match:
        app_id = match.group(1)
        status, body, _ = client.request(f"/applications/{app_id}")
        result.check(status == 200, f"页面 /applications/{app_id}（详情）", str(status))
        status, body, _ = client.request(f"/applications/{app_id}/interviews/new")
        ok = status == 200 and "添加面试" in body.decode("utf-8", "replace")
        result.check(ok, f"页面 /applications/{app_id}/interviews/new", str(status))
    else:
        result.check(False, "找不到投递记录", "演示数据为空，先跑 seed-demo")

    # 8. 越权访问他人资源必须 404（不泄露存在性）
    status, _, _ = client.request("/applications/999999")
    result.check(status == 404, "越权/不存在的投递 → 404", str(status))

    print("-" * 70)
    if result.failed:
        print(f"{len(result.failed)} 项未通过：" + "、".join(result.failed))
        return 1
    print("全部通过：服务、认证、CSRF、鉴权、页面渲染链路均正常")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
