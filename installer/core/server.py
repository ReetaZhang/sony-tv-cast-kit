# -*- coding: utf-8 -*-
"""本地 HTTP 服务：静态页面 + JSON API。"""

import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from .paths import GUIDE_FILE, WEB_DIR
from .state import State


MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".json": "application/json; charset=utf-8",
}


class ApiHandler(BaseHTTPRequestHandler):
    state: State
    action_lock = threading.Lock()
    protocol_version = "HTTP/1.1"
    server_version = "SonyCastKit/1.0"

    # ------------------------------------------------------------------
    def log_message(self, fmt, *args):  # 关闭默认访问日志，避免刷屏
        return

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, data, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _file(self, path: Path) -> None:
        if not path.is_file():
            self._json({"ok": False, "error": "文件不存在：%s" % path.name}, 404)
            return
        ctype = MIME.get(path.suffix.lower(), "application/octet-stream")
        self._send(200, path.read_bytes(), ctype)

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except (ValueError, UnicodeDecodeError):
            return {}

    # ------------------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path in ("/", "/index.html"):
                self._file(WEB_DIR / "index.html")
            elif path == "/api/state":
                self._json({"ok": True, "state": self.state.snapshot(),
                            "logs": self.state.log.tail(300)})
            elif path == "/api/ping":
                self._json({"ok": True})
            elif path == "/guide":
                self._file(GUIDE_FILE)
            elif path.startswith("/static/"):
                rel = path[len("/static/"):]
                target = (WEB_DIR / rel).resolve()
                if WEB_DIR.resolve() not in target.parents:
                    self._json({"ok": False, "error": "forbidden"}, 403)
                    return
                self._file(target)
            elif path == "/favicon.ico":
                self._file(WEB_DIR / "favicon.svg")
            else:
                self._json({"ok": False, "error": "not found"}, 404)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            self._json({"ok": False, "error": "服务器内部错误"}, 500)

    # ------------------------------------------------------------------
    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        payload = self._body()
        handler = {
            "/api/scan": self._api_scan,
            "/api/connect": self._api_connect,
            "/api/pair": self._api_pair,
            "/api/refresh": self._api_refresh,
            "/api/install": self._api_install,
            "/api/launch": self._api_launch,
            "/api/rename": self._api_rename,
            "/api/disconnect": self._api_disconnect,
            "/api/prepare": self._api_prepare,
            "/api/check": self._api_check,
        }.get(path)

        if not handler:
            self._json({"ok": False, "error": "not found"}, 404)
            return

        if not self.action_lock.acquire(blocking=False):
            self._json({"ok": False, "error": "上一步操作还在进行中，请稍候"}, 409)
            return
        try:
            result = handler(payload)
            result.setdefault("ok", False)
            result["state"] = self.state.snapshot()
            result["logs"] = self.state.log.tail(300)
            self._json(result)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self.state.log.err("操作异常：%s" % exc)
            self._json({"ok": False, "error": str(exc),
                        "state": self.state.snapshot(),
                        "logs": self.state.log.tail(300)}, 500)
        finally:
            self.action_lock.release()

    # ------------------------------------------------------------------
    # API 实现
    # ------------------------------------------------------------------
    def _api_scan(self, _payload: dict) -> dict:
        hosts = self.state.scan()
        return {"ok": True, "hosts": hosts}

    def _api_connect(self, payload: dict) -> dict:
        ok = self.state.connect(**{"host": payload.get("host", "")})
        return {"ok": ok}

    def _api_pair(self, payload: dict) -> dict:
        ok = self.state.pair(
            payload.get("host", ""),
            int(payload.get("port") or 0),
            str(payload.get("code", "")).strip(),
        )
        return {"ok": ok}

    def _api_refresh(self, _payload: dict) -> dict:
        return {"ok": self.state.refresh()}

    def _api_install(self, payload: dict) -> dict:
        return {"ok": self.state.install(str(payload.get("id", "")))}

    def _api_launch(self, payload: dict) -> dict:
        return {"ok": self.state.launch(str(payload.get("id", "")))}

    def _api_rename(self, payload: dict) -> dict:
        return {"ok": self.state.rename(str(payload.get("id", "")), str(payload.get("name", "")))}

    def _api_disconnect(self, _payload: dict) -> dict:
        self.state.disconnect()
        return {"ok": True}

    def _api_prepare(self, _payload: dict) -> dict:
        return {"ok": self.state.ensure_adb()}

    def _api_check(self, payload: dict) -> dict:
        result = self.state.check(str(payload.get("id", "")))
        return {"ok": bool(result.get("ok")), "check": result}


def build_server(host: str, port: int, state: State) -> ThreadingHTTPServer:
    handler = type("BoundApiHandler", (ApiHandler,), {"state": state})
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.daemon_threads = True
    return httpd
