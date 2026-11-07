# -*- coding: utf-8 -*-
"""接收端自检：确认服务在跑、端口在听、AirPlay HTTP 接口有响应。

这些检查都在电脑侧完成，不需要 iPhone：
- 进程检查：pidof
- 端口检查：ss / /proc/net/tcp
- 协议检查：adb forward 把端口映射到本机，请求 GET /server-info
"""

import re
import socket
import time
from typing import List, Optional, Tuple


# AirPlay 常用端口（UxPlay 默认 7000/7001/7100）
PREFERRED_PORTS = [7000, 7100, 7001, 8000, 8080]


def _shell(adb, serial: str, cmd: str, timeout: int = 15) -> str:
    try:
        code, out = adb.run(["shell", cmd], timeout=timeout, serial=serial, quiet=True)
        return out if code == 0 else ""
    except Exception:  # noqa: BLE001
        return ""


def listening_ports(adb, serial: str) -> List[int]:
    """列出设备上处于 LISTEN 状态的 TCP 端口。"""
    ports = set()

    out = _shell(adb, serial, "ss -ltn")
    for line in (out or "").splitlines():
        if not line.strip().lower().startswith("listen"):
            continue
        for token in line.split():
            m = re.search(r":(\d{2,5})$", token)
            if m:
                ports.add(int(m.group(1)))
                break

    if not ports:  # 老系统没有 ss，直接读 /proc/net/tcp
        for name in ("tcp", "tcp6"):
            out = _shell(adb, serial, "cat /proc/net/%s" % name)
            for line in (out or "").splitlines()[1:]:
                parts = line.split()
                if len(parts) < 4 or parts[3] != "0A":  # 0A = LISTEN
                    continue
                m = re.match(r"^[0-9A-Fa-f]{8,32}:([0-9A-Fa-f]{4})$", parts[1])
                if m:
                    ports.add(int(m.group(1), 16))

    return sorted(p for p in ports if p > 1024)


def _free_local_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def http_server_info(adb, serial: str, remote_port: int, timeout: float = 1.6) -> Optional[str]:
    """把电视上的端口转发到本机，请求 AirPlay 的 /server-info。"""
    local = _free_local_port()
    try:
        code, _ = adb.run(["forward", "tcp:%d" % local, "tcp:%d" % remote_port],
                          timeout=10, serial=serial, quiet=True)
        if code != 0:
            return None
        deadline = time.time() + timeout
        with socket.create_connection(("127.0.0.1", local), timeout=timeout) as s:
            req = ("GET /server-info HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                   "User-Agent: AirPlay/1.0\r\nConnection: close\r\n\r\n")
            s.sendall(req.encode())
            chunks = []
            while time.time() < deadline:
                try:
                    data = s.recv(4096)
                except socket.timeout:
                    break
                if not data:
                    break
                chunks.append(data)
                joined = b"".join(chunks)
                if b"\r\n\r\n" in joined or len(joined) > 8192:
                    break
            return b"".join(chunks).decode("utf-8", "replace")
    except OSError:
        return None
    finally:
        try:
            adb.run(["forward", "--remove", "tcp:%d" % local], timeout=8, serial=serial, quiet=True)
        except Exception:  # noqa: BLE001
            pass


def looks_like_airplay(body: str, port: Optional[int] = None) -> bool:
    """判断响应是否来自 AirPlay 服务。

    UxPlay 对未签名的请求会返回 400 "URL not signed correctly"，
    这本身就是 AirPlay 服务在正常工作的证据。
    """
    if not body:
        return False
    low = body.lower()
    if "url not signed correctly" in low or "server-info" in low:
        return True
    if "deviceid" in low or "features" in low or "pk" in low or "airplay" in low:
        return True
    if port in PREFERRED_PORTS and low.startswith("http/"):
        return True
    return False


def run_checks(adb, serial: str, package: str, apk: dict, log) -> dict:
    """执行完整自检，返回给前端渲染的结果。"""
    steps = []

    # 1. 进程
    log.info("自检 1/3：检查服务进程")
    running = adb.is_running(serial, package)
    steps.append({
        "key": "process",
        "label": "接收服务进程",
        "ok": running,
        "detail": "运行中" if running else "未运行（请先点「启动接收端」）",
    })

    if not running:
        return {"ok": False, "steps": steps, "ports": [], "server_info": "", "port": None}

    # 2. 端口
    log.info("自检 2/3：读取监听端口")
    ports = listening_ports(adb, serial)
    steps.append({
        "key": "ports",
        "label": "网络端口监听",
        "ok": bool(ports),
        "detail": ("监听中：" + "、".join(str(p) for p in ports[:8])) if ports
                  else "没有读到监听端口（可能受系统权限限制）",
    })

    # 3. AirPlay HTTP 接口
    log.info("自检 3/3：探测 AirPlay 接口")
    candidates = [p for p in PREFERRED_PORTS if p in ports]
    candidates += [p for p in ports if p not in candidates]
    body, hit_port = "", None
    for port in candidates[:12]:
        body = http_server_info(adb, serial, port) or ""
        if looks_like_airplay(body, port):
            hit_port = port
            break
    if hit_port is not None:
        unsigned = "url not signed" in body.lower()
        detail = ("端口 %d 的 AirPlay 服务已响应" % hit_port) + \
                 ("（未签名请求被正确拒绝，属正常现象）" if unsigned else "")
    else:
        detail = "未探测到 AirPlay 响应（若进程在跑，可能只是端口读取受限）"
    steps.append({
        "key": "protocol",
        "label": "AirPlay 协议响应",
        "ok": hit_port is not None,
        "detail": detail,
    })

    ok = all(s["ok"] for s in steps)
    if ok:
        log.ok("自检通过：服务在运行，AirPlay 接口可访问")
    else:
        log.warn("自检未完全通过，请查看下方每一项的状态")
    return {"ok": ok, "steps": steps, "ports": ports,
            "server_info": body[:600], "port": hit_port}
