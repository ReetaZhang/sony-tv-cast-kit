# -*- coding: utf-8 -*-
"""内存日志总线：前端每秒轮询 /api/state 取增量日志。"""

import threading
import time
from collections import deque


class LogBus:
    def __init__(self, capacity: int = 800):
        self._items = deque(maxlen=capacity)
        self._seq = 0
        self._lock = threading.Lock()

    def add(self, level: str, message: str) -> None:
        with self._lock:
            self._seq += 1
            self._items.append(
                {
                    "seq": self._seq,
                    "ts": time.strftime("%H:%M:%S"),
                    "level": level,   # info / ok / warn / err / cmd
                    "msg": str(message),
                }
            )

    # 语义化快捷方法 -------------------------------------------------
    def info(self, msg: str) -> None:
        self.add("info", msg)

    def ok(self, msg: str) -> None:
        self.add("ok", msg)

    def warn(self, msg: str) -> None:
        self.add("warn", msg)

    def err(self, msg: str) -> None:
        self.add("err", msg)

    def cmd(self, msg: str) -> None:
        self.add("cmd", msg)

    def since(self, seq: int):
        with self._lock:
            return [x for x in self._items if x["seq"] > seq]

    def tail(self, n: int = 100):
        with self._lock:
            return list(self._items)[-n:]
