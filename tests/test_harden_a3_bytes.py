"""WO-0916-HARDEN-01 A3 — UTF-8 字节级截断 + 完成卡/panel 字节预算测试.

TDD 红→绿：基线无 clamp_utf8（4300 汉字单 chunk 7200 字节无字节口径）；
builder 完成卡 payload 无按字节钳制；工具面板只有步数封顶无字节预算。
"""

from __future__ import annotations

import json

from hermes_fry_cards.cardkit.builder import (
    _PANEL_BUDGET_BYTES,
    _card_bytes,
    build_complete_card,
)
from hermes_fry_cards.cardkit.markdown import clamp_utf8
from hermes_fry_cards.streaming.segments import Segment, SegmentState, SegmentType
from hermes_fry_cards.streaming.tooluse import ToolUseTracker

# ── clamp_utf8 本体 ──


class TestClampUtf8:
    def test_short_text_untouched(self) -> None:
        text = "hello 世界"
        assert clamp_utf8(text, 7000) == text

    def test_exact_boundary_untouched(self) -> None:
        text = "汉" * 100
        assert clamp_utf8(text, 300) == text

    def test_all_chinese_3byte_boundary(self) -> None:
        """4300 汉字 = 12900 字节 → 钳到 ≤7000 字节且不切断多字节字符."""
        text = "汉" * 4300
        out = clamp_utf8(text, 7000)
        assert len(out.encode("utf-8")) <= 7000
        # 不误切：输出可完整编码（无 replacement/悬空字节）
        assert out.encode("utf-8").decode("utf-8") == out
        assert out.startswith("汉")
        assert out.endswith("汉")

    def test_emoji_4byte_boundary(self) -> None:
        """emoji 4 字节边界不切断."""
        text = "🎉" * 3000  # 12000 字节
        out = clamp_utf8(text, 7000)
        assert len(out.encode("utf-8")) <= 7000
        assert out.encode("utf-8").decode("utf-8") == out
        # 尾部也是完整 emoji
        assert out[-1] == "🎉"

    def test_mixed_content_boundary(self) -> None:
        """中英混合 + emoji：任意 max_bytes 下输出均合法."""
        unit = "a汉🎉b"  # 1+3+4+1 = 9 字节
        text = unit * 1000  # 9000 字节
        for max_bytes in (100, 999, 4500, 7000):
            out = clamp_utf8(text, max_bytes)
            assert len(out.encode("utf-8")) <= max_bytes
            assert out.encode("utf-8").decode("utf-8") == out

    def test_head_tail_preserved(self) -> None:
        """首尾双保：开头与结尾内容都在（60% 头 + 40% 尾 + 中段省略标记）."""
        head = "HEAD-MARKER" + "a" * 2000
        tail = "b" * 2000 + "TAIL-MARKER"
        text = head + "汉" * 2000 + tail
        out = clamp_utf8(text, 7000)
        assert "HEAD-MARKER" in out
        assert "TAIL-MARKER" in out
        assert "省略" in out
        assert len(out.encode("utf-8")) <= 7000

    def test_tail_dropped_when_disabled(self) -> None:
        text = "a" * 5000 + "TAIL-MARKER"
        out = clamp_utf8(text, 1000, preserve_tail=False)
        assert len(out.encode("utf-8")) <= 1000
        assert "TAIL-MARKER" not in out

    def test_max_bytes_smaller_than_marker(self) -> None:
        """极端小预算不抛异常."""
        out = clamp_utf8("汉" * 100, 10)
        assert len(out.encode("utf-8")) <= 60  # 极端退化允许最小保底


# ── 完成卡 answer 段落按字节钳制（build_complete_card 内） ──


def _answer_segment(text: str) -> Segment:
    seg = Segment(SegmentType.ANSWER, "el_answer")
    seg.text = text
    seg.created = True
    return seg


def _complete_card_with_answer(text: str) -> dict:
    return build_complete_card(
        segments=[_answer_segment(text)],
        all_tool_steps=[],
        footer_data={"duration": 1.0, "model": "test"},
        footer_enabled=True,
    )


class TestCompleteCardAnswerByteClamp:
    def test_4300_chinese_answer_within_7000_bytes_per_element(self) -> None:
        """工单反向验证：4300 汉字答案的单段 markdown 元素 ≤7000 字节."""
        card = _complete_card_with_answer("汉" * 4300)
        md_elements = [
            el
            for el in card["body"]["elements"]
            if el.get("tag") == "markdown" and "汉" in el.get("content", "")
        ]
        assert md_elements, "answer markdown 元素应存在"
        for el in md_elements:
            assert len(el["content"].encode("utf-8")) <= 7000

    def test_short_answer_untouched(self) -> None:
        card = _complete_card_with_answer("短回答")
        md = [el for el in card["body"]["elements"] if el.get("content") == "短回答"]
        assert md

    def test_answer_not_lost_only_clamped(self) -> None:
        """钳制保留头尾，不是整体丢弃."""
        text = "START" + "汉" * 4300 + "END"
        card = _complete_card_with_answer(text)
        contents = "".join(
            el.get("content", "") for el in card["body"]["elements"] if el.get("tag") == "markdown"
        )
        assert "START" in contents
        assert "END" in contents


# ── 工具面板字节预算 ──


def _panel_card(steps_count: int, output_unit: str = "汉" * 500) -> dict:
    tracker = ToolUseTracker()
    for i in range(steps_count):
        tracker.record_start("exec", f"cmd-{i}")
        tracker.record_end("exec", output=output_unit)
    segments = SegmentState()
    segments.on_tool_event(steps_count)
    seg = Segment(SegmentType.TOOL, "tool_panel")
    seg.tool_offset = 0
    seg.tool_end_offset = steps_count
    seg.created = True
    return build_complete_card(
        segments=[seg],
        all_tool_steps=tracker.build_display_steps(),
        footer_data={"duration": 1.0, "model": "test"},
        footer_enabled=True,
    )


class TestPanelBudgetBytes:
    def test_constant_exists(self) -> None:
        assert _PANEL_BUDGET_BYTES == 8000

    def test_huge_steps_folded_from_oldest(self) -> None:
        """40 步 × 500 汉字输出 → panel children 字节 ≤ 8000 且保最近 2 步."""
        card = _panel_card(40)
        panels = [
            el for el in card["body"]["elements"] if el.get("tag") == "collapsible_panel"
        ]
        assert panels
        children = panels[0]["elements"]
        children_bytes = sum(len(json.dumps(c, ensure_ascii=False).encode()) for c in children)
        assert children_bytes <= _PANEL_BUDGET_BYTES
        # 至少保最近 2 步（每步含 500 汉字输出 ≈1.5KB）
        assert len(children) >= 2

    def test_small_steps_untouched(self) -> None:
        """3 步小输出不折叠."""
        card = _panel_card(3)
        panels = [el for el in card["body"]["elements"] if el.get("tag") == "collapsible_panel"]
        children = panels[0]["elements"]
        assert len(children) >= 3

    def test_card_total_bytes_bounded(self) -> None:
        """整卡体积有上界（panel 预算生效的最终效果）."""
        card = _panel_card(60)
        assert _card_bytes(card) < 60 * 1024
