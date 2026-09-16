"""WO-0916-HARDEN-01-R R-4（对应红队 M-5+M-6）— _interrupt_order 同生命周期 + LRU 淘汰.

红队指控复现：
- M-5：_interrupt_order 只在超界时 pop(0)，两条清理路径（_dispose_session 的
  stale_keys、完成消费 pop）只动 _interrupt_map 不动 order → order 无界增长，
  且残留幽灵 key 使 while 淘汰循环空转（map 早已没有该 key）。
- M-6：FIFO 按插入序淘汰最老——中断风暴下活跃链头（最老但被链式改写仍指向
  活跃 session）会被误淘，重定向链断裂。

整改：order 与 map 同步清理；淘汰改 LRU（命中/改写 move_to_end）+ 淘汰循环
跳过 value 仍指向活跃 session 的条目。
"""

from __future__ import annotations

import asyncio

from hermes_fry_cards.controller import _INTERRUPT_MAP_MAX, StreamCardController
from hermes_fry_cards.streaming.session import CardSession, SessionState


def _ctrl() -> StreamCardController:
    ctrl = StreamCardController()
    ctrl._initialized = True
    return ctrl


class TestOrderMapSameLifecycle:
    def test_dispose_session_prunes_order(self) -> None:
        """M-5：_dispose_session 删 stale map 条目时必须同步删 order，否则幽灵 key 无界累积。"""
        ctrl = _ctrl()
        # 链：用户连发消息 old_chain 被 new_msg 中断；new_msg 的 session 完成后 dispose
        session = CardSession("new_msg", "chat", asyncio.new_event_loop())
        ctrl._sessions["new_msg"] = session
        ctrl._record_interrupt("old_chain", "new_msg")
        assert "old_chain" in ctrl._interrupt_order

        ctrl._dispose_session(session)  # map 中 value==new_msg 的 stale key 被删

        assert "old_chain" not in ctrl._interrupt_map
        assert "old_chain" not in ctrl._interrupt_order  # R-4：order 同步清

    def test_completion_pop_prunes_order(self) -> None:
        """M-5：完成消费路径 _interrupt_map.pop(message_id) 后 order 不得残留。"""
        ctrl = _ctrl()
        ctrl._record_interrupt("m1", "m2")
        popped = ctrl._interrupt_map.pop("m1", None)
        assert popped == "m2"
        # 走整改后的统一入口模拟：_record_interrupt 之外，消费点必须调 order 清理
        ctrl._forget_interrupt_key("m1")
        assert "m1" not in ctrl._interrupt_order

    def test_ghost_order_entries_do_not_stall_eviction(self) -> None:
        """幽灵 order 条目不得让淘汰空转：塞入大量已被 dispose 清的 key 后溢出淘汰仍正常。"""
        ctrl = _ctrl()
        for i in range(_INTERRUPT_MAP_MAX):
            ctrl._record_interrupt(f"o{i}", f"n{i}")
        # 模拟清理路径：全部 key 走 _forget（旧实现里 order 会留 200 幽灵）
        for i in range(_INTERRUPT_MAP_MAX):
            ctrl._forget_interrupt_key(f"o{i}")
        ctrl._record_interrupt("fresh", "new")
        assert len(ctrl._interrupt_order) <= _INTERRUPT_MAP_MAX + 1
        assert len(ctrl._interrupt_map) == 1


class TestLruEviction:
    def test_touch_moves_key_to_end(self) -> None:
        """命中已有 key 的 _record_interrupt 改写视作 touch → move_to_end。"""
        ctrl = _ctrl()
        for i in range(_INTERRUPT_MAP_MAX):
            ctrl._record_interrupt(f"o{i}", f"n{i}")
        ctrl._record_interrupt("o0", "n0-v2")  # touch 最老 key
        assert ctrl._interrupt_order[-1] == "o0"
        for i in range(5):  # 再塞 5 条：旧 FIFO 会淘 o0，LRU 淘 o1..o5
            ctrl._record_interrupt(f"x{i}", f"y{i}")
        assert "o0" in ctrl._interrupt_map  # 被 touch 过 → 不淘
        assert "o1" not in ctrl._interrupt_map  # 未 touch 的老 key 先淘

    def test_eviction_skips_entries_pointing_to_active_session(self) -> None:
        """M-6 钉死：中断风暴下，value 仍指向活跃 session 的链头不被淘。"""
        ctrl = _ctrl()
        # 活跃链头：o0 -> new_live，且 new_live 有在册 session
        live = CardSession("new_live", "chat", asyncio.new_event_loop())
        live.state = SessionState.STREAMING
        ctrl._sessions["new_live"] = live
        ctrl._record_interrupt("o0", "new_live")
        # 风暴：201 条指向已消失 session 的条目
        for i in range(_INTERRUPT_MAP_MAX + 1):
            ctrl._record_interrupt(f"storm{i}", f"ghost{i}")
        assert "o0" in ctrl._interrupt_map  # 活跃链头幸存
        assert ctrl._interrupt_map["o0"] == "new_live"
        assert len(ctrl._interrupt_map) <= _INTERRUPT_MAP_MAX
        # 无活跃可跳过后，总量仍收敛在上限内：ghost 条目被淘
        assert "storm0" not in ctrl._interrupt_map

    def test_200_chain_head_survives_201_storm(self) -> None:
        """工单原话：中断风暴 201 条，活跃链头不被淘。"""
        ctrl = _ctrl()
        live = CardSession("live", "chat", asyncio.new_event_loop())
        live.state = SessionState.STREAMING
        ctrl._sessions["live"] = live
        for i in range(201):
            ctrl._record_interrupt(f"i{i}", "live" if i == 0 else f"dead{i}")
        assert ctrl._interrupt_map.get("i0") == "live"
        assert len(ctrl._interrupt_map) <= _INTERRUPT_MAP_MAX
