"""WO-0916-HARDEN-01-R R-2（对应红队 M-1+N-1）— 跨档不重置重试预算.

红队指控复现：前批分档切换写成 `retries_used = 1`——常规档已烧的重试次数被
清零/下调，交错码序列可打到 6~7 次调用。整改为跨档连续计数（首撞竞态码的
那次等待同样消耗一格预算），最坏总调用回落 ≤5。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from hermes_fry_cards.feishu import FeishuAPIError
from tests.test_feishu import _client_with, _Resp


async def _noop_sleep(sec: float) -> None:
    return None


class TestCrossTierBudgetNotReset:
    @pytest.mark.asyncio
    async def test_interleaved_codes_total_calls_bounded(self) -> None:
        """常规档烧满 3 次后再首撞 300313：预算跨档连续，无余额可烧 → 第 4 次调用即抛出。

        旧实现切档置 1 → 已烧 3 次被清零，同序列续烧到第 7 次调用（红队 M-1）。
        整改后最坏总调用 = 1 初始 + 3 重试 ≤5（R-2 预算约束）。
        """
        element = AsyncMock(
            side_effect=[
                _Resp(ok=False, code=300317, msg="conflict"),
                _Resp(ok=False, code=300317, msg="conflict"),
                _Resp(ok=False, code=300317, msg="conflict"),
                _Resp(ok=False, code=300313, msg="race"),  # 烧满常规档后才首撞竞态码
                _Resp(ok=False, code=300317, msg="conflict"),  # 旧 bug 会在这里续命
                _Resp(ok=False, code=300317, msg="conflict"),
            ]
        )
        client = _client_with()
        client._client.cardkit.v1.card_element.content = element
        with (
            patch("hermes_fry_cards.feishu.asyncio.sleep", new=_noop_sleep),
            patch("hermes_fry_cards.feishu.asyncio.to_thread", new=lambda fn, *a: fn(*a)),
            pytest.raises(FeishuAPIError),
        ):
            await client.cardkit_stream_element("card", "el", "c")
        assert element.await_count == 4

    @pytest.mark.asyncio
    async def test_race_switch_after_partial_burn_keeps_count(self) -> None:
        """烧 2 次常规档后切档：切档等待计第 3 格，之后 300317 再撞 1 次即抛。

        序列 317,317,313,317 → 修复后共 4 次调用；旧 bug（=1 清零）会跑到 6 次。
        """
        element = AsyncMock(
            side_effect=[
                _Resp(ok=False, code=300317, msg="conflict"),
                _Resp(ok=False, code=300317, msg="conflict"),
                _Resp(ok=False, code=300313, msg="race"),
                _Resp(ok=False, code=300317, msg="conflict"),
                _Resp(ok=False, code=300317, msg="conflict"),
                _Resp(ok=False, code=300317, msg="conflict"),
            ]
        )
        client = _client_with()
        client._client.cardkit.v1.card_element.content = element
        with (
            patch("hermes_fry_cards.feishu.asyncio.sleep", new=_noop_sleep),
            patch("hermes_fry_cards.feishu.asyncio.to_thread", new=lambda fn, *a: fn(*a)),
            pytest.raises(FeishuAPIError),
        ):
            await client.cardkit_stream_element("card", "el", "c")
        assert element.await_count == 4

    @pytest.mark.asyncio
    async def test_race_first_switch_still_allows_three_more_retries(self) -> None:
        """首撞即竞态码（预算=0）：切档等待计 1 格 + 后续 2 格 = 最坏 4 次调用，≤5。"""
        element = AsyncMock(
            side_effect=[
                _Resp(ok=False, code=300313, msg="race"),
                _Resp(ok=False, code=300317, msg="conflict"),
                _Resp(ok=False, code=300317, msg="conflict"),
                _Resp(ok=False, code=300317, msg="conflict"),
            ]
        )
        client = _client_with()
        client._client.cardkit.v1.card_element.content = element
        with (
            patch("hermes_fry_cards.feishu.asyncio.sleep", new=_noop_sleep),
            patch("hermes_fry_cards.feishu.asyncio.to_thread", new=lambda fn, *a: fn(*a)),
            pytest.raises(FeishuAPIError),
        ):
            await client.cardkit_stream_element("card", "el", "c")
        assert element.await_count == 4
