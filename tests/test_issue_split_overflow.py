"""契约：完成卡超 140KB 安全线时按原文素顺序拆成多张卡，正文一字不丢。

老板 2026-09-15 要求：「内容过长，已截断」改成分条发送。
飞书单卡体积上限实测 148KB 过 / 150KB 拒（200860），CARDKIT_SAFE_BYTES=140KB。
旧策略 _fit_card_bytes 一刀切截所有 markdown（含答案正文）→ 正文丢字。
新策略 split_complete_card：
  - 卡不超限 → 原样单卡；
  - 超限 → 顶层元素按原顺序贪心装箱进多张卡（主卡带 header，续卡带「⏳ 续」标记），
    正文总量必须保全；仅当单元素自身超单卡容量时才内部截断（保底语义）。
"""

import copy
import json

from hermes_fry_cards.cardkit.builder import (
    CARDKIT_SAFE_BYTES,
    _card_bytes,
    split_complete_card,
)


def _card_with(elements, header=True):
    card = {
        "schema": "2.0",
        "config": {"update_multi": True},
        "body": {"elements": list(elements)},
    }
    if header:
        card["header"] = {"title": {"tag": "plain_text", "content": "🍟 test"}}
    return card


def _md(content, el_id=None):
    el = {"tag": "markdown", "content": content}
    if el_id:
        el["element_id"] = el_id
    return el


def _collect_markdown(card):
    """按文档序抽出所有 markdown 正文。"""
    out = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("tag") == "markdown" and isinstance(node.get("content"), str):
                out.append(node["content"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(card.get("body", card))
    return out


def test_small_card_returns_single_unchanged():
    card = _card_with([_md("hello"), _md("world", "a1")])
    out = split_complete_card(copy.deepcopy(card))
    assert len(out) == 1
    assert out[0]["body"]["elements"] == card["body"]["elements"]


def test_oversized_answer_splits_without_loss():
    # 12 个 20KB 元素 = ~240KB，必超 140KB 线
    parts = [_md(("段落%d:" % i) + ("x" * 20000), f"p{i}") for i in range(12)]
    card = _card_with(parts)
    out = split_complete_card(card)
    assert len(out) > 1
    for c in out:
        assert _card_bytes(c) <= CARDKIT_SAFE_BYTES
    # 正文一字不丢：去掉续卡标记后，按序拼接必须等于原文
    joined = "".join(
        md for c in out for md in _collect_markdown(c) if not md.startswith("⏳ 续第")
    )
    original = "".join(p["content"] for p in parts)
    assert joined == original
    # 主卡带 header；至少一张续卡带「续」字样标记
    assert out[0].get("header")
    assert any("续" in md for c in out[1:] for md in _collect_markdown(c))


def test_giant_single_element_still_truncated_as_last_resort():
    # 单个元素自身超单卡容量：拆不动，保底内部截断但卡必须达标
    huge = _md("y" * (10 * 1024 * 1024), "huge")
    card = _card_with([_md("intro"), huge, _md("outro")])
    out = split_complete_card(card)
    for c in out:
        assert _card_bytes(c) <= CARDKIT_SAFE_BYTES
    joined = "".join(md for c in out for md in _collect_markdown(c))
    assert "intro" in joined and "outro" in joined  # 邻居正文保住
    assert "已截断" in joined                        # 仅超大元素本体带截断标记


def test_panel_and_footer_follow_order():
    panel = {
        "tag": "collapsible_panel",
        "header": {"title": {"tag": "plain_text", "content": "💭"}},
        "elements": [_md("r" * 30000)],
    }
    parts = [_md("a" * 60000), panel, _md("footer-ish"), _md("b" * 60000)]
    card = _card_with(parts)
    out = split_complete_card(card)
    for c in out:
        assert _card_bytes(c) <= CARDKIT_SAFE_BYTES
    # 元素顺序跨卡保持：剔除续页标记后，按序展平的 tag 序列与输入一致
    flat = [
        e["tag"]
        for c in out
        for e in c["body"]["elements"]
        if not (e.get("tag") == "markdown" and str(e.get("content", "")).startswith("⏳ 续第"))
    ]
    assert flat == [p["tag"] for p in parts]
