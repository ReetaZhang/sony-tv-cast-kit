#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""索尼电视投屏助手 · 安装向导

用法：
    python3 main.py                # 启动并自动打开浏览器
    python3 main.py --demo         # 演示模式（模拟一台电视，便于预览）
    python3 main.py --port 8899    # 指定端口
"""

import argparse
import socket
import sys
import threading
import time
import webbrowser

from core.server import build_server
from core.state import State, APP_NAME, APP_VERSION


def find_port(start: int, host: str = "127.0.0.1", limit: int = 30) -> int:
    for port in range(start, start + limit):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    raise SystemExit("端口被占用，请用 --port 指定其它端口")


def main() -> None:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--port", type=int, default=8787, help="本地端口（默认 8787）")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认仅本机）")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--demo", action="store_true", help="演示模式，不连接真实设备")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

    state = State(mock=args.demo)
    port = find_port(args.port, args.host)
    url = "http://%s:%d" % (args.host, port)

    httpd = build_server(args.host, port, state)

    print("=" * 56)
    print("  %s v%s" % (APP_NAME, APP_VERSION))
    print("  已启动：%s" % url)
    print("  关闭此窗口即结束程序（Ctrl+C）")
    print("=" * 56)

    if not args.no_browser:
        threading.Thread(target=lambda: (time.sleep(0.8), webbrowser.open(url)),
                         daemon=True).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出。")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
