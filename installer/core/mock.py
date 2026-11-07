# -*- coding: utf-8 -*-
"""演示模式：模拟一台索尼电视，用于预览界面 / 培训演示（--demo）。"""

import time
from typing import List, Optional, Tuple


class MockAdb:
    def __init__(self, log):
        self.log = log
        self.path = "/demo/adb"
        self.version = "1.0.41"

    def ensure(self) -> str:
        return self.path

    def version_info(self) -> str:
        return self.version

    # -- 设备 ---------------------------------------------------------
    def devices(self) -> List[dict]:
        return [{"serial": "192.168.1.68:5555", "state": "device", "model": "BRAVIA_4K_GB"}]

    def connect(self, host: str, port: int = 5555) -> Tuple[bool, str]:
        time.sleep(0.6)
        return True, "connected to %s" % host

    def pair(self, host: str, port: int, code: str) -> Tuple[bool, str]:
        time.sleep(0.6)
        return True, "Successfully paired to %s:%s" % (host, port)

    def disconnect(self, address: str) -> None:
        pass

    def props(self, serial: str) -> dict:
        return {
            "model": "BRAVIA 4K GB ATV3", "brand": "Sony", "manufacturer": "Sony",
            "android": "10", "sdk": "29", "abi": "armeabi-v7a", "is_tv": True,
            "serial": "192.168.1.68:5555",
        }

    # -- 应用 ---------------------------------------------------------
    def is_installed(self, serial: str, package: str) -> bool:
        return False

    def installed_version(self, serial: str, package: str) -> str:
        return ""

    def install(self, serial: str, apk_path) -> Tuple[bool, str]:
        self.log.cmd("  Performing Streamed Install")
        time.sleep(1.2)
        self.log.cmd("  Success")
        return True, "Success"

    def launch(self, serial: str, component: str) -> Tuple[bool, str]:
        time.sleep(0.6)
        return True, "Starting: Intent"

    def force_stop(self, serial: str, package: str) -> None:
        pass

    def grant_overlay(self, serial: str, package: str) -> bool:
        return True

    def whitelist_battery(self, serial: str, package: str) -> None:
        pass

    def set_setting(self, serial: str, package: str, key: str, value: str) -> Tuple[bool, str]:
        return 0, "Broadcast completed"

    def is_running(self, serial: str, package: str) -> bool:
        return True

    def wait_boot(self, serial: str, timeout: int = 60) -> bool:
        return True
