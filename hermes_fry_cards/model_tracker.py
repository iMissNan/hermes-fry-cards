"""真实应答模型追踪。

post_api_request 生命周期钩子（插件系统入口 hermes_fry_cards.register）在每次
API 应答后调用 record()；卡片收尾时 controller 用 resolve_actual() 取
「最后一口应答」的真实模型名（如 10Router 组合 my-com1 实际由 z-ai/glm-5.3 应答），
拼进 footer 供头部显示「组合名/真实模型」。

契约（tests/test_model_actual_display.py）：
- 只保留最近一条记录，够卡片收尾读取即可；
- 请求名与记录不符（后台线程串台）或记录过期时返回 ''，保守不显示；
- 空值一概不记录，绝不抛异常打扰 API 主路径。
"""

from __future__ import annotations

import threading
import time
from typing import Any

_lock = threading.Lock()
_latest: dict[str, Any] = {}

# 最后一口应答距卡片收尾可能隔一个长工具轮，超此时长视为过期不再采信
_MAX_AGE_S = 3600.0


def record(requested: str, actual: str, session_id: str = "") -> None:
    """记录一次 API 应答的真实模型."""
    if not actual:
        return
    global _latest
    with _lock:
        _latest = {
            "requested": (requested or "").strip(),
            "actual": str(actual).strip(),
            "session_id": (session_id or "").strip(),
            "ts": time.time(),
        }


def resolve_actual(requested: str) -> str:
    """取最近一次应答的真实模型名；串台/过期时返回 ''."""
    with _lock:
        data = dict(_latest)
    if not data.get("actual"):
        return ""
    if time.time() - (float(data.get("ts") or 0)) > _MAX_AGE_S:
        return ""
    req = (requested or "").strip()
    recorded_req = data.get("requested") or ""
    if req and recorded_req and req != recorded_req:
        return ""
    return data["actual"]
