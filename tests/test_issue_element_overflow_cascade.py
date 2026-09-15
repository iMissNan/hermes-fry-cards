"""复现：长会话（>38 次工具调用）卡片雪崩式 300305。

实测背景（2026-09-14 飞书 API 对照实验）：
- 飞书 200 元素上限按「嵌套组件总数」计；tool panel 每步 ≈7 个嵌套元素，39 步单面板即爆。
- partial_update_element 灌 40~100 步面板时**当次返回成功**（静默把卡顶过 200），
  之后该卡任何 add_elements 一律 300305 → 卡片停止更新/拆卡雪崩/完成失败。

插件缺陷：dirty 工具面板每次更新都灌 all_steps[0:len(all_steps)]（全会话历史步骤），
长会话必炸；新卡首建面板同样全量 → 新卡秒死 → force-split 连环。

本模块钉死修复后契约：所有发往服务端的工具面板步骤数 ≤ TOOL_PANEL_MAX_STEPS，
且本地 element 估算与实际 payload 同口径。
"""
from __future__ import annotations

import asyncio
import json

import pytest

from hermes_fry_cards.streaming.segment_helper import (
    TOOL_PANEL_MAX_STEPS,
    cap_tool_steps,
    estimate_tool_elements,
)
from hermes_fry_cards.streaming.session import CardSession, SessionState

from test_controller import _setup_ctrl


def _mk_steps(n: int):
    return [
        {
            "name": "terminal",
            "title": f"执行命令 ({i}ms)",
            "status": "success",
            "detail": "ls",
            "output": "ok",
            "error": "",
            "icon": "setting-inter_outlined",
            "elapsed_ms": float(i),
            "result_block": {"language": "text", "content": "ok", "fenced": "```\nok\n```"},
            "error_block": None,
        }
        for i in range(n)
    ]


def _feed_tools(ctrl, session, n: int) -> None:
    """向 session 灌入 n 个已完成工具调用并同步 segments。"""
    for i in range(n):
        session.tool_use.record_start("terminal", f"cmd{i}")
        session.tool_use.record_end("terminal", output="ok")
    total = len(session.tool_use.build_display_steps())
    session.segment_state.on_tool_event(total)


def _panel_steps_from_call(call_args) -> int:
    """从 batch_update actions 里提取 tool_panel partial_update 的步数。
    每步渲染为带 icon 的标题 div + detail/result div，按标题 div 计步。"""
    actions = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("actions")
    for a in actions or []:
        if a.get("action") == "partial_update_element" and a["params"]["element_id"] == "tool_panel":
            children = a["params"]["partial_element"].get("elements", [])
            return sum(1 for c in children if "icon" in c)
    return -1


@pytest.mark.asyncio
async def test_dirty_tool_panel_update_is_capped() -> None:
    """核心回归：历史工具步骤远超上限时，dirty 面板更新 payload 必须封顶。"""
    ctrl = _setup_ctrl()
    client = ctrl._client
    session = CardSession("msg_cap", "chat", asyncio.get_running_loop())
    session.state = SessionState.STREAMING
    session.card_id = "card_cap"
    session.card_msg_id = "msg_cap_card"
    session.tool_panel_created = True
    _feed_tools(ctrl, session, TOOL_PANEL_MAX_STEPS * 3)
    total_steps = len(session.tool_use.build_display_steps())
    assert total_steps > TOOL_PANEL_MAX_STEPS, "前提：历史步骤超过封顶线"

    seg = session.segment_state.segments[-1]
    seg.created = True
    seg.element_estimate = estimate_tool_elements(0, total_steps, session.tool_use.build_display_steps())
    session.element_count = 10

    # dirty 面板 → flush 走合并面板更新分支
    session.tool_use.record_start("terminal", "cmd_last")
    session.tool_use.record_end("terminal", output="ok")
    session.segment_state.on_tool_event(len(session.tool_use.build_display_steps()))
    seg = session.segment_state.segments[-1]
    seg.created = True
    seg.dirty = True

    await ctrl._do_flush(session)

    panel_calls = [c for c in client.cardkit_batch_update.call_args_list if _panel_steps_from_call(c) >= 0]
    assert panel_calls, "应发出 tool_panel 更新"
    for c in panel_calls:
        assert _panel_steps_from_call(c) <= TOOL_PANEL_MAX_STEPS, (
            f"面板 payload {c} 步骤数超上限，会静默顶爆服务端 200 元素限制"
        )


@pytest.mark.asyncio
async def test_first_tool_panel_creation_is_capped() -> None:
    """新卡首建面板（tool_panel_created=False）同样必须封顶——force-split 后新卡秒死的主因。"""
    ctrl = _setup_ctrl()
    client = ctrl._client
    session = CardSession("msg_first", "chat", asyncio.get_running_loop())
    session.state = SessionState.STREAMING
    session.card_id = "card_first"
    session.card_msg_id = "msg_first_card"
    session.tool_panel_created = False  # 新卡：面板未建
    _feed_tools(ctrl, session, TOOL_PANEL_MAX_STEPS * 3)

    await ctrl._do_flush(session)

    calls = [c for c in client.cardkit_batch_update.call_args_list if _panel_steps_from_call(c) >= 0]
    assert calls, "首建应发出 tool_panel 更新"
    for c in calls:
        assert _panel_steps_from_call(c) <= TOOL_PANEL_MAX_STEPS


def test_cap_tool_steps_keeps_latest_and_counts() -> None:
    """cap_tool_steps 契约：保留最近 N 步，返回被省略数量。"""
    steps = _mk_steps(5)
    capped, omitted = cap_tool_steps(steps, 3)
    assert len(capped) == 3
    assert omitted == 2
    assert capped == steps[-3:], "应保留最近的步骤"
    capped2, omitted2 = cap_tool_steps(steps, 10)
    assert capped2 == steps and omitted2 == 0


def test_estimate_matches_capped_payload() -> None:
    """本地估算必须与封顶后的 payload 同口径，防 element_count 虚高/失真。"""
    steps = _mk_steps(60)
    capped, _ = cap_tool_steps(steps, TOOL_PANEL_MAX_STEPS)
    est = estimate_tool_elements(0, len(capped), capped)
    assert est < 180, f"{TOOL_PANEL_MAX_STEPS} 步估算应低于阈值，实得 {est}"
