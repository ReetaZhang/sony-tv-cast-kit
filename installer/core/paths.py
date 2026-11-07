# -*- coding: utf-8 -*-
"""集中管理套件内的路径。

目录结构::

    索尼电视投屏套件/
    ├── apk/                 接收端 APK 与清单
    ├── tools/               自动下载的 adb（platform-tools）
    ├── 安装向导/            本程序
    │   ├── main.py
    │   ├── core/
    │   └── web/
    └── 使用说明.html
"""

from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent      # .../安装向导
ROOT_DIR = APP_DIR.parent                             # .../索尼电视投屏套件
APK_DIR = ROOT_DIR / "apk"
TOOLS_DIR = ROOT_DIR / "tools"
WEB_DIR = APP_DIR / "web"
CATALOG_FILE = APK_DIR / "catalog.json"
GUIDE_FILE = ROOT_DIR / "使用说明.html"


def ensure_dirs() -> None:
    for d in (APK_DIR, TOOLS_DIR):
        d.mkdir(parents=True, exist_ok=True)
