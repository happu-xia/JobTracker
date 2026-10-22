"""生产/演示入口（waitress 单进程）：

    waitress-serve --host=127.0.0.1 --port=5001 wsgi:app
"""

from __future__ import annotations

from app import create_app

app = create_app()
