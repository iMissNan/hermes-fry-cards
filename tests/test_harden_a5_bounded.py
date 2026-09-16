"""WO-0916-HARDEN-01 A5 — _interrupt_map 有界状态测试.

TDD 红→绿：基线 _interrupt_map 无上限（长跑进程内存无界增长）。
新增 _INTERRUPT_MAP_MAX=200，超限按插入序淘汰最老。
"""

from __future__ import annotations

from hermes_fry_cards.controller import _INTERRUPT_MAP_MAX, StreamCardController


class TestInterruptMapBounded:
    def test_max_constant(self) -> None:
        assert _INTERRUPT_MAP_MAX == 200

    def test_overflow_evicts_oldest(self) -> None:
        """塞 201 条：len==200 且最老被淘."""
        ctrl = StreamCardController()
        for i in range(_INTERRUPT_MAP_MAX + 1):
            ctrl._record_interrupt(f"old{i}", f"new{i}")

        assert len(ctrl._interrupt_map) == _INTERRUPT_MAP_MAX
        assert "old0" not in ctrl._interrupt_map  # 最老被淘
        assert ctrl._interrupt_map["old1"] == "new1"  # 次老保留
        assert ctrl._interrupt_map[f"old{_INTERRUPT_MAP_MAX}"] == f"new{_INTERRUPT_MAP_MAX}"

    def test_under_limit_no_eviction(self) -> None:
        ctrl = StreamCardController()
        for i in range(50):
            ctrl._record_interrupt(f"old{i}", f"new{i}")
        assert len(ctrl._interrupt_map) == 50
        assert "old0" in ctrl._interrupt_map

    def test_250_overflow(self) -> None:
        """工单反向验证：构造 250 条溢出."""
        ctrl = StreamCardController()
        for i in range(250):
            ctrl._record_interrupt(f"o{i}", f"n{i}")
        assert len(ctrl._interrupt_map) == 200
        for i in range(50):  # 前 50 条已淘
            assert f"o{i}" not in ctrl._interrupt_map
        for i in range(50, 250):
            assert ctrl._interrupt_map[f"o{i}"] == f"n{i}"

    def test_update_existing_key_does_not_evict(self) -> None:
        """更新已存在 key 不应触发淘汰（值覆盖即可）."""
        ctrl = StreamCardController()
        for i in range(_INTERRUPT_MAP_MAX):
            ctrl._record_interrupt(f"old{i}", f"new{i}")
        ctrl._record_interrupt("old5", "newer5")
        assert len(ctrl._interrupt_map) == _INTERRUPT_MAP_MAX
        assert ctrl._interrupt_map["old5"] == "newer5"

    def test_on_interrupted_routes_through_bounded_write(self) -> None:
        """on_interrupted 的写入走有界入口（集成位验证）."""
        ctrl = StreamCardController()
        ctrl._cfg = ctrl._cfg
        # 直接塞满再走 on_interrupted —— 不建真实卡（fire_and_forget 关闭协程）
        for i in range(_INTERRUPT_MAP_MAX):
            ctrl._record_interrupt(f"m{i}", f"n{i}")
        with patch_fire_and_forget(ctrl):
            ctrl.on_interrupted(
                old_message_id="oldest",
                new_message_id="newest",
                chat_id="chat",
            )
        assert len(ctrl._interrupt_map) <= _INTERRUPT_MAP_MAX


def patch_fire_and_forget(ctrl: StreamCardController):
    from unittest.mock import patch

    return patch.object(ctrl, "_fire_and_forget", side_effect=lambda coro, loop: coro.close())
