# -*- coding: utf-8 -*-
"""把仓库内容 + 已下载的 APK 打成一个可直接分发的 zip。

输出：
    dist/索尼电视投屏套件.zip
    dist/SHA256SUMS.txt

zip 内文件名使用 UTF-8 标记，并保留可执行位（macOS 的 .command 双击即用）。
"""

import hashlib
import os
import shutil
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
BUNDLE_NAME = "索尼电视投屏套件"
ZIP_PATH = DIST / (BUNDLE_NAME + ".zip")

# 不进分发包的内容
EXCLUDE_TOP = {".git", ".github", "dist", "scripts", ".gitignore"}
EXCLUDE_NAMES = {"__pycache__", ".DS_Store"}

# APK 文件由 fetch_apks.py 下载，不放进 Git
APK_FILES = ["AirPlay接收-精简版.apk", "AirPlay接收-全功能版.apk"]


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_entries(stage: Path):
    entries = []
    for root, dirs, files in os.walk(stage):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_NAMES)
        for d in dirs:
            entries.append((Path(root) / d, True))
        for f in sorted(files):
            if f in EXCLUDE_NAMES or f.endswith(".pyc"):
                continue
            entries.append((Path(root) / f, False))
    return entries


def write_zip(stage: Path, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    entries = collect_entries(stage)
    with zipfile.ZipFile(out, "w", allowZip64=True) as zf:
        for path, is_dir in entries:
            rel = str(path.relative_to(stage.parent)).replace(os.sep, "/") + ("/" if is_dir else "")
            info = zipfile.ZipInfo(rel)
            st = path.stat()
            info.date_time = time.localtime(st.st_mtime)[:6]
            info.create_system = 3  # unix，保留权限
            mode = (st.st_mode & 0o777) | (0o755 if is_dir else 0)
            info.external_attr = (0o40000 | mode) << 16
            info.compress_type = zipfile.ZIP_STORED if is_dir else zipfile.ZIP_DEFLATED
            zf.writestr(info, b"" if is_dir else path.read_bytes())


def main() -> int:
    missing = [f for f in APK_FILES if not (ROOT / "apk" / f).exists()]
    if missing:
        print("缺少 APK：%s" % "、".join(missing))
        print("请先运行：python scripts/fetch_apks.py")
        return 1

    if DIST.exists():
        shutil.rmtree(DIST)
    stage = DIST / BUNDLE_NAME
    stage.mkdir(parents=True)

    # 1) 复制仓库内容（排除开发文件）
    for entry in sorted(ROOT.iterdir()):
        if entry.name in EXCLUDE_TOP:
            continue
        target = stage / entry.name
        if entry.is_dir():
            shutil.copytree(entry, target,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "*.apk"))
        else:
            shutil.copy2(entry, target)

    # 2) 放入 APK
    (stage / "apk").mkdir(parents=True, exist_ok=True)
    for name in APK_FILES:
        shutil.copy2(ROOT / "apk" / name, stage / "apk" / name)

    # 3) 保证启动器可执行
    launcher = stage / "开始使用（macOS）.command"
    if launcher.exists():
        launcher.chmod(0o755)

    # 4) 打包
    write_zip(stage, ZIP_PATH)

    # 5) 校验和
    sums = DIST / "SHA256SUMS.txt"
    lines = ["%s  %s" % (sha256_of(ZIP_PATH), ZIP_PATH.name)]
    for name in APK_FILES:
        lines.append("%s  %s" % (sha256_of(stage / "apk" / name), "apk/" + name))
    sums.write_text("\n".join(lines) + "\n", encoding="utf-8")

    size_mb = ZIP_PATH.stat().st_size / 1048576
    print("已生成 dist/%s（%.1f MB）" % (ZIP_PATH.name, size_mb))
    print("校验和：dist/SHA256SUMS.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
