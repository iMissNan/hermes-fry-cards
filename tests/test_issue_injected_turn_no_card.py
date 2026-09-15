"""契约：注入回合（message_id=None）必须仍能获得卡片会话。

2026-09-14 例2 事故：后台子代理回执以 internal 注入事件进入 queued 排空路径，
其 message_id 为 None；旧守卫 `elif pending_event is not None and _lark_next_message_id`
直接跳过 on_message_started → 整个回合无卡片，文本又被网关按"已流式送达"抑制
（309 字差点凭空蒸发）。controller.on_message_started 对 None 有 synthetic 兜底
（uuid 会话 + send_card_to_chat），钩子模板必须把 None 传下去而不是拦截。
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from hermes_fry_cards.controller import StreamCardController
from hermes_fry_cards.patcher import _interrupt_hook


def _enable_with_loop(ctrl: StreamCardController) -> None:
    ctrl._cfg._raw = {
        "streaming": {"enabled": True},
        "feishu": {"app_id": "app", "app_secret": "secret"},
    }
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    ctrl._loop = loop


def test_drain_start_guard_passes_none_message_id_through():
    code = _interrupt_hook("        ")
    # 新守卫：只看 pending_event，不再要求 message_id 非空
    assert "elif pending_event is not None:" in code
    assert "elif pending_event is not None and _lark_next_message_id:" not in code
    # 且仍把 message_id 参数传给 controller（由 controller 决定 synthetic）
    start_call = code.split("on_message_started(", 1)[1]
    assert "message_id=_lark_next_message_id" in start_call.split(")", 1)[0]


def test_synthetic_session_registered_for_none_message_id():
    ctrl = StreamCardController()
    _enable_with_loop(ctrl)
    with patch.object(ctrl, "_fire_and_forget", side_effect=lambda coro, loop: coro.close()):
        ctrl.on_message_started(message_id=None, chat_id="chat-1",
                                session_key="agent:main:feishu:dm:c")
    # 合成会话存在：以 syn- 前缀注册，且 session_key 可解析（delta/完成钩子的兜底路径）
    assert ctrl._sessions, "message_id=None 时应创建 synthetic 会话而不是丢弃"
    synth_key = next(iter(ctrl._sessions))
    assert synth_key.startswith("syn-")
    assert ctrl._session_keys.get("agent:main:feishu:dm:c") is ctrl._sessions[synth_key]
