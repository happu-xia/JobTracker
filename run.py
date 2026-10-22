"""开发环境启动入口：python run.py

生产/演示建议用 waitress：waitress-serve --port=5001 wsgi:app
（单进程、无 reloader，避免 debug 模式下双进程抢文件锁）
"""

from __future__ import annotations

import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5001")),
        debug=os.getenv("DEBUG", "1") == "1",
    )
