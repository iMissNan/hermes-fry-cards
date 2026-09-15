"""契约：seal（cardkit_update 全量卡）体积必须 ≤ 安全线，超了逐级瘦身。

实测（2026-09-15 对照飞书 CardKit API）：全量卡 148KB 通过、150KB 报 200860
"card over max size"。长任务完成卡（全部 reasoning 面板 + answer + tool panel）
轻松超 150KB → seal 三连拒 → 卡片永久半截（2026-09-15 05:33 例，seq=1103）。

_fit_card_bytes 策略：先截思考面板正文（每面板尾部保留），再截 answer 元素，
仍超限则从前往后丢面板元素；任何路径下都不得抛异常、不得返回超限 JSON。
"""

import json

from hermes_fry_cards.cardkit.builder import CARDKIT_SAFE_BYTES, _fit_card_bytes


def _panel(content: str, el_id: str) -> dict:
    return {"tag": "collapsible_panel", "element_id": el_id,
            "header": {"title": {"tag": "plain_text", "content": "💭 Thinking"}},
            "elements": [{"tag": "markdown", "content": content, "element_id": el_id + "_md"}]}


def _card_with(parts):
    return {"schema": "2.0", "config": {}, "body": {"elements": list(parts)}}


def test_small_card_untouched():
    card = _card_with([_panel("hello", "r0"), {"tag": "markdown", "content": "ans", "element_id": "a0"}])
    out = _fit_card_bytes(card)
    assert out["body"]["elements"][0]["elements"][0]["content"] == "hello"
    assert out["body"]["elements"][1]["content"] == "ans"


def test_oversized_card_fits_after_fit():
    big = "x" * (10 * 1024 * 1024)  # 10MB，远超 150KB
    parts = [_panel(big, f"r{i}") for i in range(4)]
    parts.append({"tag": "markdown", "content": big, "element_id": "a0"})
    out = _fit_card_bytes(_card_with(parts))
    assert len(json.dumps(out, ensure_ascii=False).encode()) <= CARDKIT_SAFE_BYTES
    # answer 元素必须存活（用户要看的正文最后一段不能被丢光）
    assert any(e.get("element_id") == "a0" for e in out["body"]["elements"])
    # 每个 markdown 内容都被截过
    for e in out["body"]["elements"]:
        for sub in e.get("elements", [e]):
            assert len(sub.get("content", "")) <= CARDKIT_SAFE_BYTES


def test_fit_idempotent_and_empty_safe():
    card = _card_with([{"tag": "hr"}])
    assert _fit_card_bytes(_fit_card_bytes(card))["body"]["elements"][0]["tag"] == "hr"
