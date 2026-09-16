"""WO-0916-HARDEN-01 A2 — 瞬态错误码白名单扩容 + 300313/300314 分档重试测试.

TDD 红→绿：基线 feishu.py 无 300309/300313/300314/300317 处理，
本文件钉死扩容后的重试次数/退避序列/超限抛出/观测副作用行为。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from hermes_fry_cards.controller import StreamCardController
from hermes_fry_cards.feishu import FeishuAPIError
from hermes_fry_cards.streaming.session import CardSession, SessionState
from tests.test_controller import _setup_ctrl  # controller 侧复用
from tests.test_feishu import _client_with, _Resp

# ── 白名单扩容：cardkit_stream_element / cardkit_update / batch / create / settings ──


class TestTransientWhitelistExpanded:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("code", "caller"),
        [
            (300317, "update"),
            (300309, "update"),
            (300317, "element"),
            (300309, "element"),
            (300317, "create"),
            (300317, "settings"),
            (300317, "batch"),
        ],
        ids=[
            "seq-conflict-update",
            "streaming-closed-update",
            "seq-conflict-element",
            "streaming-closed-element",
            "seq-conflict-create",
            "seq-conflict-settings",
            "seq-conflict-batch",
        ],
    )
    async def test_new_transient_codes_retry_once(self, code: int, caller: str) -> None:
        mock = AsyncMock(
            side_effect=[
                _Resp(ok=False, code=code, msg="transient"),
                _Resp(ok=True),
            ]
        )
        client = _client_with(
            card_update=mock if caller == "update" else AsyncMock(),
            card_element_content=mock if caller == "element" else AsyncMock(),
            card_create=mock if caller == "create" else AsyncMock(),
            settings=mock if caller == "settings" else AsyncMock(),
            batch_update=mock if caller == "batch" else AsyncMock(),
        )
        if caller == "update":
            await client.cardkit_update("card", {"schema": "2.0"}, sequence=1)
        elif caller == "element":
            # cardkit_stream_element 走 asyncio.to_thread(sync_call)，mock 直接返回
            # 非协程对象即可（包 to_thread 反而包出 coroutine）
            client._client.cardkit.v1.card_element.content = mock  # type: ignore[attr-defined]
            with patch("hermes_fry_cards.feishu.asyncio.to_thread", new=lambda fn, *a: fn(*a)):
                await client.cardkit_stream_element("card", "el", "content")
        elif caller == "create":
            mock.side_effect = [
                _Resp(ok=False, code=code, msg="transient"),
                _Resp(ok=True, data=type("D", (), {"card_id": "ok"})()),
            ]
            await client.cardkit_create({"schema": "2.0"})
        elif caller == "settings":
            await client.cardkit_close_streaming("card")
        else:
            await client.cardkit_batch_update("card", [{"action": "add"}])
        assert mock.await_count == 2

    @pytest.mark.asyncio
    async def test_300313_uses_short_tier_three_retries(self) -> None:
        """300313 元素未持久化竞态：走 (0.2,0.2,0.2) 档，共 4 次尝试."""
        element = AsyncMock(
            side_effect=[
                _Resp(ok=False, code=300313, msg="not find elementID : x"),
                _Resp(ok=False, code=300313, msg="not find elementID : x"),
                _Resp(ok=False, code=300313, msg="not find elementID : x"),
                _Resp(ok=True),
            ]
        )
        client = _client_with()
        client._client.cardkit.v1.card_element.content = element
        with patch("hermes_fry_cards.feishu.asyncio.to_thread", new=lambda fn, *a: fn(*a)):
            await client.cardkit_stream_element("card", "el", "c")
        assert element.await_count == 4

    @pytest.mark.asyncio
    async def test_300314_same_short_tier(self) -> None:
        element = AsyncMock(
            side_effect=[
                _Resp(ok=False, code=300314, msg="element not found"),
                _Resp(ok=True),
            ]
        )
        client = _client_with()
        client._client.cardkit.v1.card_element.content = element
        with patch("hermes_fry_cards.feishu.asyncio.to_thread", new=lambda fn, *a: fn(*a)):
            await client.cardkit_stream_element("card", "el", "c")
        assert element.await_count == 2

    @pytest.mark.asyncio
    async def test_300313_backoff_sequence(self) -> None:
        """退避序列恰为 (0.2, 0.2, 0.2)."""
        delays: list[float] = []

        async def fake_sleep(sec: float) -> None:
            delays.append(sec)

        element = AsyncMock(
            side_effect=[
                _Resp(ok=False, code=300313, msg="x"),
                _Resp(ok=False, code=300313, msg="x"),
                _Resp(ok=False, code=300313, msg="x"),
                _Resp(ok=False, code=300313, msg="x"),
            ]
        )
        client = _client_with()
        client._client.cardkit.v1.card_element.content = element
        with (
            patch("hermes_fry_cards.feishu.asyncio.sleep", side_effect=fake_sleep),
            patch("hermes_fry_cards.feishu.asyncio.to_thread", new=lambda fn, *a: fn(*a)),
            pytest.raises(FeishuAPIError),
        ):
            await client.cardkit_stream_element("card", "el", "c")
        assert element.await_count == 4  # 1 初次 + 3 重试
        assert delays == [0.2, 0.2, 0.2]

    @pytest.mark.asyncio
    async def test_permanent_code_no_retry(self) -> None:
        """非白名单码（如 300315 schema）不重试，立即抛出."""
        element = AsyncMock(side_effect=[_Resp(ok=False, code=300315, msg="schema")])
        client = _client_with()
        client._client.cardkit.v1.card_element.content = element
        with (
            patch("hermes_fry_cards.feishu.asyncio.to_thread", new=lambda fn, *a: fn(*a)),
            pytest.raises(FeishuAPIError),
        ):
            await client.cardkit_stream_element("card", "el", "c")
        assert element.await_count == 1

    @pytest.mark.asyncio
    async def test_300317_exhausted_raises_after_full_tier(self) -> None:
        """300317 走常规档 3 连拒后原样抛出."""
        delays: list[float] = []

        async def fake_sleep(sec: float) -> None:
            delays.append(sec)

        mock = AsyncMock(
            side_effect=[
                _Resp(ok=False, code=300317, msg="conflict"),
                _Resp(ok=False, code=300317, msg="conflict"),
                _Resp(ok=False, code=300317, msg="conflict"),
                _Resp(ok=False, code=300317, msg="conflict"),
            ]
        )
        client = _client_with(card_update=mock)
        with (
            patch("hermes_fry_cards.feishu.asyncio.sleep", side_effect=fake_sleep),
            pytest.raises(FeishuAPIError),
        ):
            await client.cardkit_update("card", {"schema": "2.0"})
        assert mock.await_count == 4
        assert delays == [0.15, 0.5, 1.0]


# ── streaming/controller._handle_flush_error：300309 不再静默 ──


def _flush_session(ctrl: StreamCardController, msg: str = "msg_s309") -> CardSession:
    session = CardSession(msg, "chat", __import__("asyncio").get_running_loop())
    session.state = SessionState.STREAMING
    session.card_id = "card_s309"
    ctrl._sessions[msg] = session
    return session


class TestFlushError300309Observation:
    @pytest.mark.asyncio
    async def test_300309_logs_warning_and_marks_streaming_closed_seen(self) -> None:
        ctrl = _setup_ctrl()
        session = _flush_session(ctrl)
        with patch("hermes_fry_cards.streaming.controller._logger") as mock_logger:
            ctrl._handle_flush_error(FeishuAPIError("closed", code=300309), session=session)
        assert session.streaming_closed_seen is True
        mock_logger.warning.assert_called_once()
        assert "300309" in str(mock_logger.warning.call_args)

    @pytest.mark.asyncio
    async def test_other_codes_do_not_touch_flag(self) -> None:
        ctrl = _setup_ctrl()
        session = _flush_session(ctrl, "msg_other")
        ctrl._handle_flush_error(FeishuAPIError("rate", code=230020), session=session)
        assert session.streaming_closed_seen is False
        ctrl._handle_flush_error(FeishuAPIError("boom", code=999999), session=session)
        assert session.streaming_closed_seen is False

    @pytest.mark.asyncio
    async def test_300309_does_not_raise(self) -> None:
        """观测逻辑不得改变吞异常行为（回归保护：test_api_errors_swallowed 语义）."""
        ctrl = _setup_ctrl()
        session = _flush_session(ctrl, "msg_swell")
        ctrl._handle_flush_error(FeishuAPIError("closed", code=300309), session=session)  # 不抛
        assert session.state == SessionState.STREAMING
