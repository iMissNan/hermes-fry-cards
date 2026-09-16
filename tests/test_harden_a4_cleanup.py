"""WO-0916-HARDEN-01 A4 — /stop 全量残留清理 + spinner 兜底灭测试.

TDD 红→绿：基线 on_session_aborted 只清当前 session_key；同 chat 其它残留
session 的 spinner 永远转圈。新增 force_cleanup_all_sessions 遍历非终态
session→ABORT→seal（seal 失败也要 close_streaming 兜底，双失败记 error 不抛）。
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from hermes_fry_cards.controller import StreamCardController
from hermes_fry_cards.streaming.session import CardSession, SessionState
from tests.test_controller import _setup_ctrl

_REAL_SLEEP = asyncio.sleep


async def _noop_sleep(sec: float) -> None:
    """协作式快进：真实让出事件循环但不等满退避。"""
    await _REAL_SLEEP(0)


def _register(
    ctrl: StreamCardController,
    msg: str,
    key: str | None = None,
    chat_id: str = "chat",
) -> CardSession:
    session = CardSession(msg, chat_id, asyncio.get_running_loop())
    session.state = SessionState.STREAMING
    ctrl._sessions[msg] = session
    if key:
        ctrl._session_keys[key] = session
        session.session_key = key
    return session


def _drain(ctrl: StreamCardController):
    """把 _fire_and_forget 收进当前 running loop，保证收尾协程真被 await（消 N-4 warning）。"""
    return patch.object(ctrl, "_fire_and_forget", side_effect=lambda coro, loop: asyncio.ensure_future(coro))


class TestForceCleanupAllSessions:
    @pytest.mark.asyncio
    async def test_multi_session_stop_cleans_all_residuals(self) -> None:
        """多 session 并存时 /stop 全清：目标 key 封卡，同 chat 残留也全部 ABORT→seal."""
        ctrl = _setup_ctrl()
        s_first = _register(ctrl, "first", "session:first")
        s_second = _register(ctrl, "second", "session:second")

        with (
            patch.object(ctrl, "_complete_session_wait", new_callable=AsyncMock, return_value=True),
            _drain(ctrl),
        ):
            await ctrl.on_session_aborted(session_key="session:first")
            await _REAL_SLEEP(0.05)

        assert s_first.state == SessionState.ABORTED
        # A4 核心：同 chat 残留 session 不再漏清
        assert s_second.state == SessionState.ABORTED

    @pytest.mark.asyncio
    async def test_force_cleanup_skips_terminal_sessions(self) -> None:
        """终态 session 不误杀."""
        ctrl = _setup_ctrl()
        s_done = _register(ctrl, "done")
        s_done.state = SessionState.COMPLETED
        s_fail = _register(ctrl, "failed_one")
        s_fail.state = SessionState.FAILED
        s_active = _register(ctrl, "active")

        with (
            patch.object(ctrl, "_complete_session_wait", new_callable=AsyncMock, return_value=True),
            _drain(ctrl),
        ):
            ctrl.force_cleanup_all_sessions(reason="test")
            await _REAL_SLEEP(0.05)

        assert s_done.state == SessionState.COMPLETED
        assert s_fail.state == SessionState.FAILED
        assert s_active.state == SessionState.ABORTED

    @pytest.mark.asyncio
    async def test_seal_failure_still_closes_streaming(self) -> None:
        """整改令 R-3（M-2）重写：mock 真实链路——client 炸 update 使
        _do_complete_card 吞异常返回 False（生产真实形态），验证 emergency close 被调。
        旧版 side_effect=RuntimeError 打桩是假绿灯：生产 seal 从不抛异常。"""
        from hermes_fry_cards.feishu import FeishuAPIError

        ctrl = _setup_ctrl()
        s_active = _register(ctrl, "active", "session:active")
        s_active.card_id = "card_active"

        async def exploding_update(*a, **k):
            raise FeishuAPIError("update exploded", code=999999)

        assert ctrl._client is not None
        ctrl._client.cardkit_update = exploding_update
        with (
            patch("hermes_fry_cards.streaming.controller.asyncio.sleep", new=_noop_sleep),
            patch.object(ctrl, "_emergency_close_streaming", new_callable=AsyncMock) as emergency,
            _drain(ctrl),
        ):
            ctrl.force_cleanup_all_sessions(reason="test")
            await _REAL_SLEEP(0.3)

        emergency.assert_awaited_once_with(s_active)

    @pytest.mark.asyncio
    async def test_double_failure_logs_error_not_raise(self) -> None:
        """seal 返回 False 且 emergency close 也炸：记 error 不抛（双失败语义）。"""
        from hermes_fry_cards.feishu import FeishuAPIError

        ctrl = _setup_ctrl()
        s_active = _register(ctrl, "active")
        s_active.card_id = "card_active"

        async def exploding_update(*a, **k):
            raise FeishuAPIError("update exploded", code=999999)

        assert ctrl._client is not None
        ctrl._client.cardkit_update = exploding_update
        ctrl._client.cardkit_close_streaming = AsyncMock(
            side_effect=FeishuAPIError("close exploded", code=999999)
        )
        with (
            patch("hermes_fry_cards.streaming.controller.asyncio.sleep", new=_noop_sleep),
            patch("hermes_fry_cards.controller._logger") as mock_logger,
            _drain(ctrl),
        ):
            ctrl.force_cleanup_all_sessions(reason="test")
            await _REAL_SLEEP(0.3)

        mock_logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_no_sessions_is_noop(self) -> None:
        ctrl = _setup_ctrl()
        ctrl.force_cleanup_all_sessions(reason="empty")  # 不抛


class TestChatScopedCleanupR1:
    """WO-0916-HARDEN-01-R R-1（B-2+M-7）：force_cleanup 必须按 chat 过滤，
    /stop chatA 不得误杀 chatB 的 STREAMING 卡（红队跨 chat 误杀指控钉死）。"""

    @pytest.mark.asyncio
    async def test_stop_chat_a_does_not_touch_chat_b_streaming(self) -> None:
        """chatA /stop 不影响 chatB STREAMING——跨 chat 不误杀钉死测试。"""
        ctrl = _setup_ctrl()
        s_a = _register(ctrl, "a1", "session:a", chat_id="chatA")
        s_a_residual = _register(ctrl, "a2", chat_id="chatA")  # 同 chat 残留，应被一并清
        s_b = _register(ctrl, "b1", "session:b", chat_id="chatB")  # 别的 chat 流式卡，不得动

        with (
            patch.object(ctrl, "_complete_session_wait", new_callable=AsyncMock, return_value=True),
            _drain(ctrl),
        ):
            await ctrl.on_session_aborted(session_key="session:a")
            await asyncio.sleep(0.05)

        assert s_a.state == SessionState.ABORTED
        assert s_a_residual.state == SessionState.ABORTED  # 同 chat 残留一并清（工单原文语义）
        assert s_b.state == SessionState.STREAMING  # 跨 chat 零打扰

    @pytest.mark.asyncio
    async def test_force_cleanup_with_chat_id_only_touches_that_chat(self) -> None:
        ctrl = _setup_ctrl()
        s_a = _register(ctrl, "a1", chat_id="chatA")
        s_b = _register(ctrl, "b1", chat_id="chatB")
        s_b_terminal = _register(ctrl, "b2", chat_id="chatB")
        s_b_terminal.state = SessionState.COMPLETED

        with (
            patch.object(ctrl, "_complete_session_wait", new_callable=AsyncMock, return_value=True),
            _drain(ctrl),
        ):
            ctrl.force_cleanup_all_sessions(chat_id="chatA", reason="test")
            await asyncio.sleep(0.05)

        assert s_a.state == SessionState.ABORTED
        assert s_b.state == SessionState.STREAMING
        assert s_b_terminal.state == SessionState.COMPLETED

    @pytest.mark.asyncio
    async def test_force_cleanup_none_keeps_global_semantics(self) -> None:
        """chat_id=None 保留全局语义供显式运维。"""
        ctrl = _setup_ctrl()
        s_a = _register(ctrl, "a1", chat_id="chatA")
        s_b = _register(ctrl, "b1", chat_id="chatB")

        with (
            patch.object(ctrl, "_complete_session_wait", new_callable=AsyncMock, return_value=True),
            _drain(ctrl),
        ):
            ctrl.force_cleanup_all_sessions(chat_id=None, reason="ops")
            await asyncio.sleep(0.05)

        assert s_a.state == SessionState.ABORTED
        assert s_b.state == SessionState.ABORTED
