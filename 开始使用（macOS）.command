#!/bin/bash
# 双击本文件即可启动「索尼电视投屏助手」安装向导
cd "$(dirname "$0")" || exit 1

echo "=============================================="
echo "  索尼电视投屏助手 · 安装向导"
echo "=============================================="

if ! command -v python3 >/dev/null 2>&1; then
  echo ""
  echo "未找到 python3。请先安装 Python 3（https://www.python.org/downloads/），"
  echo "或改用 U 盘方式安装接收端，详见「使用说明.html」。"
  echo ""
  read -n 1 -s -r -p "按任意键退出…"
  exit 1
fi

exec python3 "installer/main.py"
