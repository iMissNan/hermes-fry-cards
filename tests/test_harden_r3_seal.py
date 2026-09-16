"""WO-0916-HARDEN-01-R R-3（对应红队 M-2）— force seal 兜底改判返回值.

红队指控复现：生产链路 `_complete_session_wait → _do_complete_card` 吞异常
（内部自带 3 次重试 + fallback close），最终失败返回 False 而**从不抛异常**——
前批 `_force_seal_one` 靠 `except Exception` 触发 `_emergency_close_streaming`
是死代码：seal 失败时 spinner 永远不灭。整改：按返回值 False 走 emergency close。

测试 mock 真实链路（client 炸 update/close），废除裸 RuntimeError 打桩的假绿灯。
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from hermes_fry_cards.feishu import FeishuAPIError
from hermes_fry_cards.streaming.session import CardSession, SessionState
from tests.test_controller import _setup_ctrl

_REAL_SLEEP = asyncio.sleep


async def _noop_sleep(sec: float) -> None:
    """协作式快进：真实让出事件循环但不等满退避。"""
    await _REAL_SLEEP(0)


def _seal_session(ctrl, msg: str, card_id: str) -> CardSession:
    session = CardSession(msg, "chat", asyncio.get_running_loop())
    session.state = SessionState.STREAMING
    session.card_id = card_id
    ctrl._sessions[msg] = session
    return session


class TestForceSealUsesReturnValue:
    @pytest.mark.asyncio
    async def test_seal_returning_false_triggers_emergency_close(self) -> None:
        """真实链路：client.update 持续抛 API 错 → _do_complete_card 吞异常返回
        False → _force_seal_one 必须走 emergency close_streaming 灭 spinner。

        旧实现只认异常，此场景 emergency 永不被调（红队 M-2 假绿灯指控）。
        """
        ctrl = _setup_ctrl()
        session = _seal_session(ctrl, "stuck", "card_stuck")

        async def exploding_update(*a, **k):
            raise FeishuAPIError("update exploded", code=999999)

        async def exploding_close(*a, **k):
            raise FeishuAPIError("close exploded", code=999999)

        assert ctrl._client is not None
        ctrl._client.cardkit_update = exploding_update
        ctrl._client.cardkit_close_streaming = exploding_close
        # _remove_loading_icon 走 batch_update——保持 AsyncMock 即可
        with (
            patch("hermes_fry_cards.streaming.controller.asyncio.sleep", new=_noop_sleep),
            patch.object(ctrl, "_emergency_close_streaming", new_callable=AsyncMock) as emergency,
        ):
            ctrl.force_cleanup_all_sessions(reason="test")
            await _REAL_SLEEP(0.3)
        emergency.assert_awaited_once_with(session)

    @pytest.mark.asyncio
    async def test_seal_success_does_not_emergency_close(self) -> None:
        ctrl = _setup_ctrl()
        _seal_session(ctrl, "ok", "card_ok")
        with patch.object(ctrl, "_emergency_close_streaming", new_callable=AsyncMock) as emergency:
            ctrl.force_cleanup_all_sessions(reason="test")
            await _REAL_SLEEP(0.3)
        emergency.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_emergency_close_failure_logs_error_not_raise(self) -> None:
        """seal 返回 False 且 emergency close 也炸：记 error 不抛（双失败语义保留）。"""
        ctrl = _setup_ctrl()
        session = _seal_session(ctrl, "dbl", "card_dbl")

        async def exploding_update(*a, **k):
            raise FeishuAPIError("update exploded", code=999999)

        assert ctrl._client is not None
        ctrl._client.cardkit_update = exploding_update
        ctrl._client.cardkit_close_streaming = AsyncMock(
            side_effect=FeishuAPIError("close exploded", code=999999)
        )
        with (
            patch("hermes_fry_cards.streaming.controller.asyncio.sleep", new=_noop_sleep),
            patch.object(ctrl, "_emergency_close_streaming", wraps=ctrl._emergency_close_streaming),
            patch("hermes_fry_cards.controller._logger") as mock_logger,
        ):
            ctrl.force_cleanup_all_sessions(reason="test")
            await _REAL_SLEEP(0.3)
        mock_logger.error.assert_called()
        assert session.card_id == "card_dbl"  # 收尾路径不得反向炸宿主（不抛即通过）
