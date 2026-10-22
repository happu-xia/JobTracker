"""生产/演示启动入口（waitress）：python serve.py

与 run.py 的分工：
- run.py   → Flask 内置服务器，debug + 自动重载，只适合开发
- serve.py → waitress 单进程、多线程，无重载，适合演示与压测

端口默认 5001，可用环境变量 PORT / HOST 覆盖。
PyCharm 里可直接选中这个文件点绿三角启动，点红方块停止。
"""

from __future__ import annotations

import os

from waitress import serve

from wsgi import app

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "5001"))

if __name__ == "__main__":
    print(f"JobTracker 已启动 → http://{HOST}:{PORT}")
    print("停止服务：点 PyCharm 运行面板的红色方块，或在此窗口按 Ctrl+C")
    serve(app, host=HOST, port=PORT, threads=8)
