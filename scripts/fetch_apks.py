# -*- coding: utf-8 -*-
"""下载两个上游 AirPlay 接收端 APK，并校验 SHA-256。

接收端是 GPL-3.0 的上游构建产物，本仓库不把它们放进 Git，
发布时由本脚本拉取、校验后再打包（见 scripts/build_release.py）。
"""

import argparse
import hashlib
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APK_DIR = ROOT / "apk"

APKS = [
    {
        "file": "AirPlay接收-精简版.apk",
        "version": "1.2.1",
        "project": "gzhanlei/uxplay-android",
        "page": "https://github.com/gzhanlei/uxplay-android",
        "url": "https://github.com/gzhanlei/uxplay-android/releases/download/v1.2.1/app-release.apk",
        "sha256": "3ed8915dd6c8461a5871c7f7b41a28ec6eac9264ea64e818dff2e45121c766ed",
    },
    {
        "file": "AirPlay接收-全功能版.apk",
        "version": "0.0.36",
        "project": "jqssun/android-airplay-server",
        "page": "https://github.com/jqssun/android-airplay-server",
        "url": "https://github.com/jqssun/android-airplay-server/releases/download/v0.0.36/app-release.apk",
        "sha256": "b8c7c595ed93f91562feedce92c27800f08f9c84df424f6ac2045e82324cf2a4",
    },
]


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "sony-tv-cast-kit/fetch"})
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as fh:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            if total:
                sys.stdout.write("\r    %d%%  %.1f/%.1f MB" % (
                    done * 100 // total, done / 1048576, total / 1048576))
                sys.stdout.flush()
    print()
    tmp.replace(dest)


def download_with_retry(url: str, dest: Path, attempts: int = 3) -> None:
    last = None
    for i in range(attempts):
        try:
            download(url, dest)
            return
        except Exception as exc:  # noqa: BLE001
            last = exc
            dest.with_suffix(dest.suffix + ".part").unlink(missing_ok=True)
            if i < attempts - 1:
                print("   第 %d 次失败（%s），2 秒后重试…" % (i + 1, exc))
                time.sleep(2 * (i + 1))
    raise last  # type: ignore[misc]


def main() -> int:
    parser = argparse.ArgumentParser(description="下载并校验接收端 APK")
    parser.add_argument("--force", action="store_true", help="即使已存在也重新下载")
    args = parser.parse_args()

    APK_DIR.mkdir(parents=True, exist_ok=True)
    failed = 0

    for item in APKS:
        dest = APK_DIR / item["file"]
        print("== %s (%s)" % (item["file"], item["project"]))

        if dest.exists() and not args.force:
            if sha256_of(dest) == item["sha256"]:
                print("   已存在且校验通过，跳过")
                continue
            print("   已存在但校验不符，重新下载")

        try:
            download_with_retry(item["url"], dest)
        except Exception as exc:  # noqa: BLE001
            print("   下载失败：%s" % exc)
            failed += 1
            continue

        digest = sha256_of(dest)
        if digest != item["sha256"]:
            print("   SHA-256 不匹配！")
            print("     期望 %s" % item["sha256"])
            print("     实际 %s" % digest)
            dest.unlink(missing_ok=True)
            failed += 1
        else:
            print("   校验通过 %s" % digest[:16])

    if failed:
        print("\n有 %d 个文件失败，请检查网络后重试。" % failed)
        return 1
    print("\n全部就绪。下一步：python scripts/build_release.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
