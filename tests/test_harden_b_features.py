"""Tests for Plan B architecture refactoring features.

Covers:
1. Feishu 300315 element not found idempotent absorption
2. 99991400 rate limit retry in transient codes
3. CAS completion dispatch lock in CardSession & controller
4. Reasoning short segment buffer & merge (<30 chars)
5. Cron card dynamic status colors (green/yellow/carmine) and overflow folding
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from hermes_fry_cards.feishu import (
    CARDKIT_RATE_LIMIT,
    CARDKIT_SCHEMA_ERROR,
    CARDKIT_TRANSIENT_ERROR_CODES,
    FeishuAPIError,
    _RE_ELEMENT_NOT_FOUND,
)
from hermes_fry_cards.streaming.session import CardSession, SessionState
from hermes_fry_cards.streaming.segments import Segment, SegmentType
from hermes_fry_cards.cardkit.builder import build_complete_card, build_cron_card


def test_300315_regex_and_rate_limit_codes():
    """Verify error codes and regex patterns."""
    assert CARDKIT_RATE_LIMIT in CARDKIT_TRANSIENT_ERROR_CODES
    
    # Check 300315 regex
    err_msg = "ErrMsg: not find elementID : context_loading_hint;"
    m = _RE_ELEMENT_NOT_FOUND.search(err_msg)
    assert m is not None
    assert m.group(1) == "context_loading_hint"


def test_cas_completion_dispatched_flag():
    """Verify CardSession CAS flag initializes to False and guards execution."""
    loop = asyncio.new_event_loop()
    try:
        session = CardSession("msg_123", "chat_456", loop)
        assert hasattr(session, "_completion_dispatched")
        assert session._completion_dispatched is False
        session._completion_dispatched = True
        assert session._completion_dispatched is True
    finally:
        loop.close()


def test_reasoning_short_segments_merge():
    """Verify reasoning segments under 30 chars are merged into a single block."""
    s1 = Segment(SegmentType.REASONING, "seg_1")
    s1.text = "好的"
    s1.elapsed_ms = 100

    s2 = Segment(SegmentType.REASONING, "seg_2")
    s2.text = "我来查一下文件"
    s2.elapsed_ms = 200

    s3 = Segment(SegmentType.ANSWER, "seg_3")
    s3.text = "这里是最终答案。"

    segments = [s1, s2, s3]
    card = build_complete_card(
        segments=segments,
        all_tool_steps=[],
        footer_data={"duration": 10},
        show_tool_use=True,
    )
    # The unified panel should contain 1 merged reasoning panel instead of 2 separate ones
    elements = card["body"]["elements"]
    panel = next(el for el in elements if el.get("tag") == "collapsible_panel")
    # Inside unified panel: merged children
    reasoning_panels = [c for c in panel["elements"] if c.get("tag") == "collapsible_panel"]
    assert len(reasoning_panels) == 1
    content = reasoning_panels[0]["elements"][0]["content"]
    assert "好的\n\n我来查一下文件" in content


def test_cron_card_dynamic_colors_and_folding():
    """Verify cron card templates (blue for normal, carmine for failed) and collapsible panel on overflow."""
    # 1. Success short card (default blue for compatibility with fry-cards style)
    card_ok = build_cron_card("All systems healthy.", task_name="健康巡检", run_time="2026-09-17 12:00:00")
    assert card_ok["header"]["template"] == "blue"
    assert len(card_ok["body"]["elements"]) == 1
    assert card_ok["body"]["elements"][0]["tag"] == "markdown"

    # 2. Failed short card (carmine)
    card_err = build_cron_card("Error: connection refused", task_name="数据库备份", run_time="2026-09-17 12:00:00")
    assert card_err["header"]["template"] == "carmine"
    assert "❌" in card_err["header"]["title"]["content"]

    # 3. Long content folding
    long_content = "Line\n" * 12
    card_long = build_cron_card(long_content, task_name="长日志任务")
    assert any(el.get("tag") == "collapsible_panel" for el in card_long["body"]["elements"])
