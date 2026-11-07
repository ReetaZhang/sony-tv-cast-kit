# -*- coding: utf-8 -*-
"""全局状态：设备连接、APK 清单、安装/启动动作。"""

import json
import platform as _platform
import threading
import time
from pathlib import Path
from typing import List, Optional

from .adb import Adb, AdbError
from .logbus import LogBus
from .net import local_ipv4, same_subnet
from .paths import CATALOG_FILE, APK_DIR

APP_NAME = "索尼电视投屏助手"
APP_VERSION = "1.1.0"


def _load_catalog() -> List[dict]:
    """读取 apk/catalog.json，并补全文件是否存在、体积等运行时信息。"""
    items: List[dict] = []
    if CATALOG_FILE.exists():
        try:
            raw = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                items = raw
        except (ValueError, OSError):
            items = []

    if not items:  # 兜底：直接把 apk 目录里的文件列出来
        for f in sorted(APK_DIR.glob("*.apk")):
            items.append({
                "id": f.stem, "file": f.name, "title": f.stem,
                "package": "", "version": "", "launch": "", "desc": "",
                "tags": [], "rename": False, "verified": False,
            })

    for it in items:
        path = APK_DIR / it.get("file", "")
        it["exists"] = path.is_file()
        it["size"] = path.stat().st_size if it["exists"] else 0
        it["installed"] = False
        it["installed_version"] = ""
        it.setdefault("tags", [])
        it.setdefault("rename", False)
        it.setdefault("verified", False)
    return items


class State:
    def __init__(self, mock: bool = False):
        self.log = LogBus()
        self.lock = threading.RLock()
        self.adb = Adb(self.log)
        self.apks = _load_catalog()
        self.serial: Optional[str] = None
        self.device: Optional[dict] = None
        self.busy = False
        self.mock = mock

        if mock:
            from .mock import MockAdb
            self.adb = MockAdb(self.log)  # type: ignore[assignment]
            self.log.info("已进入演示模式（不连接真实设备）")
        else:
            self.adb.locate()  # 只查找，不自动下载；连接时再按需下载

    # ------------------------------------------------------------------
    def snapshot(self) -> dict:
        with self.lock:
            return {
                "app": {"name": APP_NAME, "version": APP_VERSION},
                "platform": "%s %s" % (_platform.system(), _platform.release()),
                "local_ip": local_ipv4(),
                "adb": {
                    "ready": bool(getattr(self.adb, "path", None)),
                    "version": getattr(self.adb, "version", None),
                    "path": getattr(self.adb, "path", None),
                },
                "device": self.device,
                "apks": [dict(a) for a in self.apks],
                "busy": self.busy,
                "mock": self.mock,
            }

    # ------------------------------------------------------------------
    def ensure_adb(self) -> bool:
        self.busy = True
        try:
            self.adb.ensure()
            self.adb.version_info()
            return True
        except AdbError as exc:
            self.log.err(str(exc))
            return False
        finally:
            self.busy = False

    def scan(self, port: int = 5555) -> List[str]:
        from .net import scan_adb
        self.busy = True
        try:
            self.log.info("正在扫描局域网 %s/24 的 5555 端口…" % ".".join(local_ipv4().split(".")[:3]))
            hosts = scan_adb(port=port)
            if hosts:
                self.log.ok("发现 %d 台可连接设备：%s" % (len(hosts), "、".join(hosts)))
            else:
                self.log.warn("没有发现开放 5555 端口的设备，请确认电视已开启「网络调试」")
            return hosts
        finally:
            self.busy = False

    def connect(self, host: str) -> bool:
        host = (host or "").strip()
        if not host:
            self.log.err("请输入电视的 IP 地址")
            return False
        self.busy = True
        try:
            if not self.ensure_adb():
                return False
            local = local_ipv4()
            bare = host.split(":")[0]
            if bare.count(".") == 3 and not same_subnet(local, bare):
                self.log.warn("提示：%s 与电脑（%s）不在同一网段，可能连不上" % (bare, local))
            ok, out = self.adb.connect(host)
            if not ok:
                low = (out or "").lower()
                if low.strip() == "timeout":
                    self.log.err("连接超时：请确认电视 IP 正确、已打开「网络调试」，并且与电脑在同一 Wi-Fi")
                elif "refused" in low:
                    self.log.err("连接被拒绝：电视的「网络调试」可能未开启，或端口不是 5555")
                elif "unable to connect" in low or "timed out" in low:
                    self.log.err("无法连接到 %s，请检查 IP、Wi-Fi 与路由器隔离设置" % host)
                else:
                    self.log.err("连接失败：%s" % (out or "未知错误"))
                return False
            if not self._refresh_device(expected=host, retries=6):
                self.log.warn("已连接但未获取到设备信息，请稍后点「刷新」")
                return False
            return True
        finally:
            self.busy = False

    def pair(self, host: str, port: int, code: str) -> bool:
        self.busy = True
        try:
            if not self.ensure_adb():
                return False
            ok, out = self.adb.pair(host, int(port), code)
            if ok:
                self.log.ok("配对成功，正在连接…")
                return self.connect(host)
            self.log.err("配对失败：%s" % (out or "请检查配对码"))
            return False
        finally:
            self.busy = False

    def refresh(self) -> bool:
        self.busy = True
        try:
            if not self.ensure_adb():
                return False
            return self._refresh_device()
        finally:
            self.busy = False

    def _refresh_device(self, expected: Optional[str] = None, retries: int = 3) -> bool:
        for attempt in range(retries):
            devices = self.adb.devices()
            if expected:
                devices = [d for d in devices if d["serial"].startswith(expected.split(":")[0])] or devices
            online = [d for d in devices if d["state"] == "device"]
            if online:
                target = online[0]
                info = self.adb.props(target["serial"])
                info["serial"] = target["serial"]
                info["model"] = info.get("model") or target.get("model") or "Android TV"
                self.serial = target["serial"]
                self.device = info
                self._refresh_compatibility()
                self.log.ok("已连接：%s（Android %s）" % (info["model"], info.get("android") or "?"))
                self._refresh_installed()
                return True

            unauthorized = [d for d in devices if d["state"] == "unauthorized"]
            if unauthorized:
                self.log.warn("电视还未授权本电脑，请看电视屏幕上的「允许调试」弹窗并选择允许")
                time.sleep(1.5)
                continue
            if attempt < retries - 1:
                time.sleep(1.2)

        self.serial = None
        self.device = None
        self.log.warn("未发现已连接的电视")
        return False

    def _refresh_compatibility(self) -> None:
        """根据电视的 ABI 列表，标记哪些安装包装得了。"""
        abilist = (self.device or {}).get("abilist") or []
        if not abilist:
            for apk in self.apks:
                apk["compatible"] = None   # 未知，不拦
            return
        for apk in self.apks:
            abis = apk.get("abis") or []
            apk["compatible"] = (not abis) or any(a in abilist for a in abis)

    def _refresh_installed(self) -> None:
        if not self.serial:
            return
        for apk in self.apks:
            pkg = apk.get("package") or ""
            if not pkg:
                continue
            apk["installed"] = self.adb.is_installed(self.serial, pkg)
            apk["installed_version"] = (
                self.adb.installed_version(self.serial, pkg) if apk["installed"] else ""
            )

    # ------------------------------------------------------------------
    def _find_apk(self, apk_id: str) -> Optional[dict]:
        return next((a for a in self.apks if a["id"] == apk_id), None)

    def install(self, apk_id: str) -> bool:
        apk = self._find_apk(apk_id)
        if not apk or not self.serial:
            self.log.err("请先连接电视，再选择要安装的接收端")
            return False
        path = APK_DIR / apk["file"]
        if not path.exists():
            self.log.err("安装包缺失：%s" % path)
            return False
        if apk.get("compatible") is False:
            self.log.err("这台电视缺少该安装包所需的 CPU 架构（%s），请改装「全功能版」" % ", ".join(apk.get("abis") or []))
            return False

        self.busy = True
        try:
            size_mb = path.stat().st_size / 1048576
            self.log.info("正在安装「%s」（%.1f MB），请保持电视通电…" % (apk["title"], size_mb))
            ok, out = self.adb.install(self.serial, path)
            if not ok:
                low = (out or "").lower()
                if "insufficient_storage" in low:
                    self.log.err("电视存储空间不足，请先清理后再安装")
                elif "no_matching_abis" in low:
                    self.log.err("电视不支持 32 位应用，请改装「全功能版」（含 64 位）")
                elif "older_sdk" in low:
                    self.log.err("电视系统版本过低，装不上这个接收端")
                elif "version downgrade" in low:
                    self.log.err("已安装版本更高，请先卸载旧版")
                elif "device offline" in low or "no devices" in low:
                    self.log.err("电视连接已断开，请回到第 1 步重新连接")
                else:
                    self.log.err("安装失败：%s" % (out or "未知错误"))
                return False
            self.log.ok("安装成功：%s" % apk["title"])
            self.adb.grant_overlay(self.serial, apk["package"])
            self.adb.whitelist_battery(self.serial, apk["package"])
            apk["installed"] = True
            apk["installed_version"] = self.adb.installed_version(self.serial, apk["package"])
            return True
        finally:
            self.busy = False

    def launch(self, apk_id: str) -> bool:
        apk = self._find_apk(apk_id)
        if not apk or not self.serial:
            self.log.err("请先连接电视")
            return False
        if not apk.get("launch"):
            self.log.warn("该安装包没有记录启动组件，请到电视应用列表手动打开")
            return False
        self.busy = True
        try:
            ok, out = self.adb.launch(self.serial, apk["launch"])
            if ok:
                time.sleep(1.5)
                running = self.adb.is_running(self.serial, apk["package"])
                self.log.ok("已在电视上启动「%s」%s" % (apk["title"], "，接收服务运行中" if running else ""))
                return True
            self.log.err("启动失败：%s" % (out or "未知错误"))
            return False
        finally:
            self.busy = False

    def rename(self, apk_id: str, name: str) -> bool:
        apk = self._find_apk(apk_id)
        name = (name or "").strip()
        if not apk or not self.serial:
            self.log.err("请先连接电视")
            return False
        if not name:
            self.log.err("名称不能为空")
            return False
        if not apk.get("rename"):
            self.log.warn("「%s」不支持改名，它会以固定名称出现在 AirPlay 列表中" % apk["title"])
            return False
        self.busy = True
        try:
            code, out = self.adb.set_setting(self.serial, apk["package"], "server_name", name)
            if code == 0:
                self.log.ok("接收端名称已设为「%s」" % name)
                self.adb.force_stop(self.serial, apk["package"])
                self.launch(apk_id)
                return True
            self.log.err("设置名称失败：%s" % (out or "该版本可能不支持"))
            return False
        finally:
            self.busy = False

    def check(self, apk_id: str) -> dict:
        """对电视上的接收端做一次自检（进程 / 端口 / 协议）。"""
        apk = self._find_apk(apk_id)
        if not apk or not self.serial:
            self.log.err("请先连接电视并安装接收端")
            return {"ok": False, "steps": [], "ports": [], "server_info": "", "port": None}

        if self.mock:
            steps = [
                {"key": "process", "label": "接收服务进程", "ok": True, "detail": "运行中（演示）"},
                {"key": "ports", "label": "网络端口监听", "ok": True, "detail": "监听中：7000、7100、7001（演示）"},
                {"key": "protocol", "label": "AirPlay 协议响应", "ok": True, "detail": "端口 7000 返回了 server-info（演示）"},
            ]
            self.log.ok("自检通过（演示数据）")
            return {"ok": True, "steps": steps, "ports": [7000, 7100, 7001], "server_info": "", "port": 7000}

        self.busy = True
        try:
            from .probe import run_checks
            self.log.info("开始自检「%s」…" % apk["title"])
            return run_checks(self.adb, self.serial, apk["package"], apk, self.log)
        finally:
            self.busy = False

    def disconnect(self) -> None:
        with self.lock:
            if self.serial:
                self.adb.disconnect(self.serial)
            self.serial = None
            self.device = None
            self.log.info("已断开与电视的连接")
