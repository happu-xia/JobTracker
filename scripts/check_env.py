"""环境自检：一条命令回答「为什么跑不起来」。

设计意图：把踩过的坑前置成检查项，避免面试演示时现场翻车。
覆盖 6 类问题：Python 版本、依赖缺失、.env 配置、MySQL 连通性、
数据表是否建好、上传目录是否可写（Windows 中文路径/权限）。

    python scripts/check_env.py

退出码 0 表示全部通过，1 表示存在阻断项。
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

PASS = "[ OK ]"
FAIL = "[FAIL]"
WARN = "[WARN]"

_errors: list[str] = []
_warnings: list[str] = []


def report(status: str, title: str, detail: str = "") -> None:
    line = f"{status} {title}"
    if detail:
        line = f"{line:<44} {detail}"
    print(line)
    if status == FAIL:
        _errors.append(title)
    elif status == WARN:
        _warnings.append(title)


def mask_dsn(dsn: str) -> str:
    """把连接串里的密码换成 ***，避免截图/日志泄漏到简历仓库。"""
    parts = urlsplit(dsn)
    if not parts.password:
        return dsn
    netloc = parts.netloc.replace(f":{parts.password}@", ":***@")
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


# ---------------------------------------------------------------- 1. Python
def check_python() -> None:
    version = sys.version_info
    detail = f"{version.major}.{version.minor}.{version.micro} ({sys.executable})"
    if version < (3, 10):
        report(FAIL, "Python 版本", detail + " —— 需要 >= 3.10（用了 X | Y 联合类型）")
    else:
        report(PASS, "Python 版本", detail)


# ---------------------------------------------------------------- 2. 依赖
def check_dependencies() -> None:
    from importlib import metadata

    required = {
        "flask": "Flask",
        "flask_sqlalchemy": "Flask-SQLAlchemy",
        "flask_migrate": "Flask-Migrate",
        "flask_login": "Flask-Login",
        "flask_wtf": "Flask-WTF",
        "pymysql": "PyMySQL",
        "dotenv": "python-dotenv",
        "waitress": "waitress",
        "tzdata": "tzdata",
    }
    missing = []
    for module, package in required.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
        else:
            try:
                version = metadata.version(package)
            except metadata.PackageNotFoundError:
                version = "?"
            print(f"{PASS} 依赖 {package:<28} {version}")
    if missing:
        report(FAIL, "依赖缺失", "、".join(missing) + " —— 执行 pip install -r requirements.txt")


# ---------------------------------------------------------------- 3. 配置
def check_config() -> None:
    from config import get_config

    cfg = get_config()
    dsn = cfg.SQLALCHEMY_DATABASE_URI
    report(PASS, "运行环境", cfg.__name__)
    report(PASS, "数据库连接串", mask_dsn(dsn))

    if dsn.startswith("sqlite"):
        report(WARN, "数据库类型", "当前为 SQLite，仅适合测试；演示请用 MySQL")

    if not os.getenv("SECRET_KEY"):
        report(FAIL, "SECRET_KEY", "未配置，会话与 CSRF 会失效")
    elif "insecure" in str(cfg.SECRET_KEY):
        report(WARN, "SECRET_KEY", "仍在使用默认值，生产环境必须替换")
    else:
        report(PASS, "SECRET_KEY", "已配置（%d 位）" % len(str(cfg.SECRET_KEY)))

    env_file = BASE_DIR / ".env"
    report(PASS if env_file.exists() else WARN, ".env 文件", str(env_file))


# ---------------------------------------------------------------- 4. 数据库
def check_database() -> None:
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import SQLAlchemyError

    from config import get_config

    url = get_config().SQLALCHEMY_DATABASE_URI
    try:
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            version = conn.execute(text("SELECT VERSION()")).scalar()
            report(PASS, "MySQL 连通性", str(version))

            if url.startswith("mysql"):
                charset = conn.execute(
                    text("SELECT @@character_set_database, @@collation_database")
                ).first()
                ok = str(charset[0]).lower() == "utf8mb4"
                report(PASS if ok else FAIL, "库字符集", f"{charset[0]} / {charset[1]}")

            tables = set(engine.dialect.get_table_names(conn))
    except SQLAlchemyError as exc:
        report(FAIL, "MySQL 连通性", str(exc).splitlines()[0][:120])
        print("\n      排查建议：")
        print("      1) 服务是否启动： mysqld --defaults-file=D:/JobTrackerData/mysql/my.ini")
        print("      2) 账号密码是否正确： 核对 .env 的 DB_USER / DB_PASSWORD")
        print("      3) 库是否已建： mysql -u root -p < scripts/create_db.sql")
        return

    expected = {"users", "companies", "job_types", "resumes", "applications", "interviews"}
    missing = expected - tables
    if missing:
        report(FAIL, "数据表", "缺少 " + "、".join(sorted(missing)) + " —— 执行 flask init-db")
        return
    report(PASS, "数据表", f"6/6 就绪（共 {len(tables)} 张）")

    with engine.connect() as conn:
        for table, label in (
            ("users", "账号"),
            ("companies", "企业"),
            ("applications", "投递"),
            ("interviews", "面试"),
            ("resumes", "简历"),
        ):
            count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            print(f"{PASS}   数据量 {label:<10} {count} 行")
        demo = conn.execute(text("SELECT COUNT(*) FROM users WHERE username = 'demo'")).scalar()
    if demo:
        report(PASS, "演示账号", "demo 已就绪（密码见 README）")
    else:
        report(WARN, "演示账号", "不存在 —— 执行 python -m flask --app wsgi seed-demo")


# ---------------------------------------------------------------- 5. 上传目录
def check_upload_dir() -> None:
    from config import get_config

    root = Path(get_config().UPLOAD_ROOT)
    if not root.is_absolute():
        report(FAIL, "上传目录", f"{root} 不是绝对路径")
        return

    try:
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=root, prefix=".probe_", delete=True) as fp:
            fp.write(b"ok")
        report(PASS, "上传目录可写", str(root))
    except OSError as exc:
        report(FAIL, "上传目录可写", f"{root} —— {exc}")

    if not str(root).isascii():
        report(WARN, "上传路径含中文", "Windows 下 send_file 可能异常，建议纯 ASCII 路径")

    try:
        import shutil

        free_gb = shutil.disk_usage(root.anchor or root).free / 1024**3
        report(PASS if free_gb > 1 else WARN, "剩余磁盘空间", f"{free_gb:.1f} GB")
    except OSError:
        pass


# ---------------------------------------------------------------- 6. 时区
def check_timezone() -> None:
    from app.utils.dtime import get_tz, now_local

    try:
        tz = get_tz()
        report(PASS, "时区", f"{tz} → 当前 {now_local():%Y-%m-%d %H:%M:%S}")
    except Exception as exc:  # noqa: BLE001 - 兜底检查，任何异常都视为失败
        report(FAIL, "时区", str(exc))


def main() -> int:
    parser = argparse.ArgumentParser(description="JobTracker 环境自检")
    parser.parse_args()

    print("=" * 78)
    print(" JobTracker 环境自检")
    print("=" * 78)
    check_python()
    print("-" * 78)
    check_dependencies()
    print("-" * 78)
    check_config()
    print("-" * 78)
    check_database()
    print("-" * 78)
    check_upload_dir()
    check_timezone()
    print("=" * 78)

    if _errors:
        print(f"存在 {len(_errors)} 个阻断项：" + "、".join(_errors))
        print("按上面提示修复后重跑本脚本。")
        return 1
    if _warnings:
        print(f"全部通过，{len(_warnings)} 个提醒项：" + "、".join(_warnings))
    else:
        print("全部通过，可以直接启动： python run.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
