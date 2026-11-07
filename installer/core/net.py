# -*- coding: utf-8 -*-
"""局域网工具：本机地址、网段扫描。

注意：开了 VPN / 代理（Clash、Surge 等）时，默认路由可能落在 utun 虚拟网卡上，
所以这里不直接用“对外连接”的地址，而是枚举物理网卡并优先选择私有网段地址。
"""

import ipaddress
import platform
import re
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

# 这些网段不是家里/办公室的真实局域网，扫描没有意义
_BENCHMARK_NETS = [ipaddress.ip_network("198.18.0.0/15")]


def _is_usable(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if addr.version != 4 or addr.is_loopback or addr.is_link_local or addr.is_multicast:
        return False
    return not any(addr in net for net in _BENCHMARK_NETS)


def _rank(ip: str) -> int:
    """私有网段优先，其中 192.168 > 10 > 172.16/12。"""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return -99
    if ip.startswith("192.168."):
        return 40
    if ip.startswith("10."):
        return 30
    if addr in ipaddress.ip_network("172.16.0.0/12"):
        return 20
    if addr.is_private:
        return 10
    return 0


def _ips_from_ifconfig() -> List[str]:
    """macOS / Linux：解析 ifconfig 或 ip addr 输出。"""
    ips: List[str] = []
    for cmd in (["ifconfig"], ["ip", "-o", "-4", "addr", "show"]):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=6).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        if not out:
            continue
        for line in out.splitlines():
            m = re.search(r"inet\s+(?:addr:)?(\d+\.\d+\.\d+\.\d+)", line)
            if m:
                ips.append(m.group(1))
        if ips:
            break
    return ips


def _ips_from_ipconfig() -> List[str]:
    """Windows：解析 ipconfig。"""
    try:
        out = subprocess.run(["ipconfig"], capture_output=True, timeout=8).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    text = out.decode("mbcs", errors="ignore") if isinstance(out, bytes) else out
    ips = []
    for line in text.splitlines():
        if "IPv4" in line or "IP Address" in line:
            m = re.search(r"(\d+\.\d+\.\d+\.\d+)", line)
            if m:
                ips.append(m.group(1))
    return ips


def local_ipv4() -> str:
    candidates: List[str] = []

    system = platform.system()
    if system == "Windows":
        candidates += _ips_from_ipconfig()
    else:
        candidates += _ips_from_ifconfig()

    # 补充：DNS 解析本机名
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            candidates.append(info[4][0])
    except OSError:
        pass

    usable = [ip for ip in dict.fromkeys(candidates) if _is_usable(ip)]
    if usable:
        usable.sort(key=_rank, reverse=True)
        return usable[0]

    # 兜底：UDP connect（可能落在 VPN 网卡上）
    for target in ("192.168.1.1", "10.0.0.1", "8.8.8.8"):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((target, 80))
            ip = s.getsockname()[0]
            if _is_usable(ip):
                return ip
        except OSError:
            pass
        finally:
            s.close()
    return "127.0.0.1"


def same_subnet(ip_a: str, ip_b: str, prefix: int = 24) -> bool:
    try:
        net = ipaddress.ip_network("%s/%d" % (ip_a, prefix), strict=False)
        return ipaddress.ip_address(ip_b) in net
    except ValueError:
        return False


def _probe(host: str, port: int, timeout: float) -> Optional[str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return host
    except OSError:
        return None


def scan_adb(port: int = 5555, timeout: float = 0.45, workers: int = 96) -> List[str]:
    """扫描本机所在 /24 网段中开放指定端口的设备。"""
    local = local_ipv4()
    try:
        network = ipaddress.ip_network(local + "/24", strict=False)
    except ValueError:
        return []

    hosts = [str(h) for h in network.hosts() if str(h) != local]
    found: List[str] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_probe, h, port, timeout): h for h in hosts}
        for fut in as_completed(futures):
            result = fut.result()
            if result:
                found.append(result)
    found.sort(key=lambda x: tuple(int(p) for p in x.split(".")))
    return found


def tcp_open(host: str, port: int, timeout: float = 1.5) -> bool:
    return _probe(host, port, timeout) is not None
