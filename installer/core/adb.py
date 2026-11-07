# -*- coding: utf-8 -*-
"""adb 封装：定位 / 自动下载 / 设备管理 / 安装 / 启动 / 配置。"""

import os
import platform as _platform
import re
import shutil
import stat
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from .paths import TOOLS_DIR
from .logbus import LogBus

IS_WIN = os.name == "nt"
ADB_NAME = "adb.exe" if IS_WIN else "adb"

PLATFORM_TOOLS_URL = {
    "Darwin": "https://dl.google.com/android/repository/platform-tools-latest-darwin.zip",
    "Windows": "https://dl.google.com/android/repository/platform-tools-latest-windows.zip",
    "Linux": "https://dl.google.com/android/repository/platform-tools-latest-linux.zip",
}


class AdbError(RuntimeError):
    pass


class Adb:
    def __init__(self, log: LogBus):
        self.log = log
        self.path: Optional[str] = None
        self.version: Optional[str] = None
        self._lock = threading.Lock()
        self._env = None  # 某些环境下 HOME 不可写时，改用套件内的目录

    # ------------------------------------------------------------------
    # 定位与下载
    # ------------------------------------------------------------------
    def locate(self) -> Optional[str]:
        """按 环境变量 → 套件内 tools → 系统 PATH 的顺序查找 adb。"""
        candidates: List[Path] = []
        env = os.environ.get("ADB")
        if env:
            candidates.append(Path(env))
        candidates.append(TOOLS_DIR / "platform-tools" / ADB_NAME)
        found = shutil.which("adb")
        if found:
            candidates.append(Path(found))

        for c in candidates:
            try:
                if c and Path(c).is_file() and os.access(str(c), os.X_OK):
                    self.path = str(Path(c).resolve())
                    return self.path
            except OSError:
                continue
        return None

    def ensure(self) -> str:
        """确保 adb 可用；没有就自动下载 platform-tools。"""
        p = self.locate()
        if p:
            return p
        self.log.info("未找到 adb，正在从 Google 官方源下载 platform-tools（约 15MB）…")
        if not self.download():
            raise AdbError("adb 下载失败，请检查网络后重试，或手动安装 platform-tools")
        p = self.locate()
        if not p:
            raise AdbError("adb 下载完成但未找到可执行文件")
        self.log.ok("adb 已就绪：%s" % p)
        return p

    def download(self, progress: Optional[Callable[[int], None]] = None) -> bool:
        url = PLATFORM_TOOLS_URL.get(_platform.system())
        if not url:
            self.log.err("当前系统 (%s) 没有可用的 platform-tools 下载" % _platform.system())
            return False
        TOOLS_DIR.mkdir(parents=True, exist_ok=True)
        zip_path = TOOLS_DIR / "platform-tools.zip"
        tmp_path = TOOLS_DIR / "platform-tools.zip.part"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "sony-cast-kit/1.0"})
            with urllib.request.urlopen(req, timeout=60) as resp, open(tmp_path, "wb") as fh:
                total = int(resp.headers.get("Content-Length") or 0)
                done, last_pct = 0, -1
                while True:
                    chunk = resp.read(256 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
                    done += len(chunk)
                    if total:
                        pct = int(done * 100 / total)
                        if pct >= last_pct + 20:
                            last_pct = pct
                            self.log.info("下载中 %d%%（%.1f / %.1f MB）" % (pct, done / 1048576, total / 1048576))
                            if progress:
                                progress(pct)
            tmp_path.replace(zip_path)
            self.log.info("正在解压 platform-tools …")
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(TOOLS_DIR)
            zip_path.unlink(missing_ok=True)
            adb = TOOLS_DIR / "platform-tools" / ADB_NAME
            if adb.exists() and not IS_WIN:
                adb.chmod(adb.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            return adb.exists()
        except Exception as exc:  # noqa: BLE001 - 网络/磁盘异常统一提示
            self.log.err("下载 adb 失败：%s" % exc)
            tmp_path.unlink(missing_ok=True)
            return False

    # ------------------------------------------------------------------
    # 基础执行
    # ------------------------------------------------------------------
    def run(self, args: List[str], timeout: int = 30, serial: Optional[str] = None,
            quiet: bool = False) -> Tuple[int, str]:
        if not self.path:
            raise AdbError("adb 尚未就绪")
        cmd = [self.path]
        if serial:
            cmd += ["-s", serial]
        cmd += [str(a) for a in args]

        if not quiet:
            shown = " ".join(cmd[1:])
            if len(shown) > 160:
                shown = shown[:157] + "…"
            self.log.cmd("adb " + shown)

        kwargs = dict(stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                      text=True, encoding="utf-8", errors="replace")
        if self._env:
            kwargs["env"] = self._env
        if IS_WIN:
            kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        try:
            proc = subprocess.run(cmd, timeout=timeout, **kwargs)
            out = (proc.stdout or "").strip()
            if not quiet and out:
                for line in out.splitlines()[:12]:
                    self.log.add("cmd", "  " + line)
            return proc.returncode, out
        except subprocess.TimeoutExpired:
            self.log.err("命令超时（%ss）：adb %s" % (timeout, " ".join(args)))
            return 124, "timeout"
        except FileNotFoundError:
            raise AdbError("adb 可执行文件丢失")

    def version_info(self) -> str:
        if self.version:
            return self.version
        try:
            code, out = self.run(["version"], timeout=10, quiet=True)
            if code != 0 and "mkdir" in (out or "").lower():
                # HOME 不可写（受限账户、沙箱、企业策略）：把 adb 的配置目录放进套件
                home = TOOLS_DIR / "adb-home"
                home.mkdir(parents=True, exist_ok=True)
                self._env = dict(os.environ, HOME=str(home), USERPROFILE=str(home))
                self.log.warn("系统用户目录不可写，已改用套件内的 adb 配置目录")
                code, out = self.run(["version"], timeout=10, quiet=True)
                if code != 0:
                    raise AdbError("adb 无法启动：%s" % (out or "未知错误")[:200])
            m = re.search(r"version\s+([0-9.]+)", out or "")
            self.version = m.group(1) if m else (out.splitlines()[0] if out else "unknown")
        except AdbError:
            raise
        except Exception:  # noqa: BLE001
            self.version = "unknown"
        return self.version

    # ------------------------------------------------------------------
    # 设备
    # ------------------------------------------------------------------
    def devices(self) -> List[dict]:
        """返回已授权设备列表。"""
        _, out = self.run(["devices", "-l"], timeout=20, quiet=True)
        result = []
        for line in (out or "").splitlines():
            line = line.strip()
            if not line or line.startswith("List of devices"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            serial, state = parts[0], parts[1]
            model = ""
            m = re.search(r"\bmodel:(\S+)", line)
            if m:
                model = m.group(1)
            result.append({"serial": serial, "state": state, "model": model})
        return result

    def connect(self, host: str, port: int = 5555) -> Tuple[bool, str]:
        address = host if ":" in host else "%s:%d" % (host, port)
        code, out = self.run(["connect", address], timeout=15)
        ok = code == 0 and ("connected to" in out.lower())
        if "already connected" in out.lower():
            ok = True
        return ok, out

    def disconnect(self, address: str) -> None:
        self.run(["disconnect", address], timeout=15, quiet=True)

    def pair(self, host: str, port: int, code: str) -> Tuple[bool, str]:
        code_, out = self.run(["pair", "%s:%d" % (host, port), code], timeout=40)
        ok = code_ == 0 and "successfully paired" in out.lower()
        return ok, out

    # ------------------------------------------------------------------
    # 设备信息
    # ------------------------------------------------------------------
    def props(self, serial: str) -> dict:
        keys = [
            "ro.product.model", "ro.product.brand", "ro.product.manufacturer",
            "ro.build.version.release", "ro.build.version.sdk", "ro.product.cpu.abi",
            "ro.build.characteristics", "ro.serialno",
            "ro.product.cpu.abilist", "ro.product.cpu.abilist32",
        ]
        info = {}
        try:
            code, out = self.run(["shell", "getprop"], timeout=25, serial=serial, quiet=True)
            if code != 0:
                return info
            for line in out.splitlines():
                m = re.match(r"\[([^\]]+)\]:\s*\[(.*)\]", line.strip())
                if m and m.group(1) in keys:
                    info[m.group(1)] = m.group(2)
        except AdbError:
            return info
        return {
            "model": info.get("ro.product.model", ""),
            "brand": info.get("ro.product.brand", ""),
            "manufacturer": info.get("ro.product.manufacturer", ""),
            "android": info.get("ro.build.version.release", ""),
            "sdk": info.get("ro.build.version.sdk", ""),
            "abi": info.get("ro.product.cpu.abi", ""),
            "abilist": [x for x in (info.get("ro.product.cpu.abilist", "") or "").split(",") if x],
            "is_tv": "tv" in (info.get("ro.build.characteristics", "") or "").lower(),
            "serial": info.get("ro.serialno", "") or serial,
        }

    # ------------------------------------------------------------------
    # 应用
    # ------------------------------------------------------------------
    def is_installed(self, serial: str, package: str) -> bool:
        code, out = self.run(["shell", "pm", "list", "packages", package],
                             timeout=20, serial=serial, quiet=True)
        return code == 0 and ("package:%s" % package) in out

    def installed_version(self, serial: str, package: str) -> str:
        code, out = self.run(["shell", "dumpsys", "package", package],
                             timeout=25, serial=serial, quiet=True)
        if code != 0:
            return ""
        m = re.search(r"versionName=(\S+)", out or "")
        return m.group(1) if m else ""

    def install(self, serial: str, apk_path: Path) -> Tuple[bool, str]:
        if not apk_path.exists():
            return False, "APK 文件不存在：%s" % apk_path
        code, out = self.run(["install", "-r", str(apk_path)], timeout=420, serial=serial)
        ok = code == 0 and "Success" in out
        return ok, out

    def launch(self, serial: str, component: str) -> Tuple[bool, str]:
        code, out = self.run(["shell", "am", "start", "-n", component],
                             timeout=30, serial=serial)
        ok = code == 0 and "Error" not in out
        return ok, out

    def force_stop(self, serial: str, package: str) -> None:
        self.run(["shell", "am", "force-stop", package], timeout=20, serial=serial, quiet=True)

    def grant_overlay(self, serial: str, package: str) -> bool:
        """允许后台弹出画面（Android 10+ 必需）。"""
        code, _ = self.run(["shell", "appops", "set", package, "SYSTEM_ALERT_WINDOW", "allow"],
                           timeout=20, serial=serial, quiet=True)
        return code == 0

    def whitelist_battery(self, serial: str, package: str) -> None:
        self.run(["shell", "cmd", "deviceidle", "whitelist", "+" + package],
                 timeout=20, serial=serial, quiet=True)

    def set_setting(self, serial: str, package: str, key: str, value: str) -> Tuple[bool, str]:
        """部分接收端支持通过广播修改设置（如接收端名称）。"""
        return self.run(
            ["shell", "am", "broadcast", "-n", "%s/.SettingsReceiver" % package,
             "-a", "%s.SET_SETTING" % package, "--es", "key", key, "--es", "value", value],
            timeout=25, serial=serial, quiet=True,
        )

    def is_running(self, serial: str, package: str) -> bool:
        code, out = self.run(["shell", "pidof", package], timeout=15, serial=serial, quiet=True)
        return code == 0 and bool((out or "").strip())

    def wait_boot(self, serial: str, timeout: int = 60) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            code, out = self.run(["shell", "getprop", "sys.boot_completed"],
                                 timeout=10, serial=serial, quiet=True)
            if code == 0 and "1" in out:
                return True
            time.sleep(2)
        return False
