"""CardKit v2.0 卡片构建器 — i18n、元素构建、卡片组装."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from ..streaming.segments import Segment, SegmentType
from ..streaming.tooluse import ToolDisplayStep
from .i18n import _LOCALES, _T, _i18n, _t
from .markdown import (
    _downgrade_tables,
    _split_long_text,
    clamp_utf8,
    optimize_markdown_style,
)

STREAMING_ELEMENT_ID = "streaming_content"
REASONING_ELEMENT_ID = "reasoning_content"
REASONING_TEXT_ELEMENT_ID = "reasoning_text"
TOOL_PANEL_ELEMENT_ID = "tool_panel"
LOADING_ELEMENT_ID = "loading_icon"
_LOADING_ELEMENT_ID = LOADING_ELEMENT_ID  # 兼容旧私有引用
_LOADING_IMG_KEY = "img_v3_02vb_496bec09-4b43-4773-ad6b-0cdd103cd2bg"

# 工具面板单次 payload 的最大步骤数（流式 partial_update 与完成态 seal 共用）。
# 实测（2026-09-14 对照飞书 CardKit API）：
#   - 200 元素上限按【嵌套组件总数】计，tool panel 每步 ≈7 个嵌套元素；
#   - 39 步（≈276 嵌套）建卡/全量更新即 300305；partial_update 灌 40~100 步
#     当次返回成功但已静默顶过 200，此后该卡所有写入一律 300305；
#   - 20 步 ≈143 嵌套，给完成卡的推理面板/答案分块/footer 留足余量。
TOOL_PANEL_MAX_STEPS = 20
# WO-0916-HARDEN-01 A3：完成卡单段 markdown 元素的字节预算（与 2400 字符 ≈7200 字节口径对齐，
# 中文 3 字节/字下飞书 CardKit 单元素保守值）。
_ANSWER_ELEMENT_BUDGET_BYTES = 7000
# WO-0916-HARDEN-01 A3：工具面板 children 总字节预算——步数封顶防不住 N 个中等输出的
# 字节膨胀（设计借鉴 aiduPOP (monkey2jack, MIT) cardkit/elements.py panel 预算层），
# 超预算从最老步骤折叠，至少保留最近 2 步。
_PANEL_BUDGET_BYTES = 8000
# 200860「card over max size」实测（2026-09-15）：全量卡 JSON 148KB 过 / 150KB 拒。
# 安全线取 140KB，给结构开销与编码膨胀留余量。
CARDKIT_SAFE_BYTES = 140 * 1024


def cap_tool_steps(
    steps: list[ToolDisplayStep], max_steps: int = TOOL_PANEL_MAX_STEPS
) -> tuple[list[ToolDisplayStep], int]:
    """工具面板 payload 封顶：保留最近 max_steps 步，返回 (capped, omitted_count)。"""
    if len(steps) <= max_steps:
        return steps, 0
    return steps[-max_steps:], len(steps) - max_steps


_CARDKIT_TRUNC_MARK = "\n\n…（内容过长，已截断）"


def _card_bytes(card: dict[str, Any]) -> int:
    return len(json.dumps(card, ensure_ascii=False).encode())


def _iter_markdown_nodes(card: dict[str, Any]):
    """递归收集卡片里所有带正文 content 的 markdown 节点（面板子项/答案/footer）。"""
    def walk(node: Any):
        if isinstance(node, dict):
            if node.get("tag") == "markdown" and isinstance(node.get("content"), str):
                yield node
            for value in node.values():
                yield from walk(value)
        elif isinstance(node, list):
            for value in node:
                yield from walk(value)
    yield from walk(card.get("body", card))


def _fit_card_bytes(card: dict[str, Any], *, limit: int = CARDKIT_SAFE_BYTES) -> dict[str, Any]:
    """把全量卡压进飞书 200860 体积上限（实测 148KB 过 / 150KB 拒）。

    seal/complete 的全量卡包含全部 reasoning 面板 + answer + footer，长任务轻松
    超 150KB → cardkit_update 三连拒 → 卡片永久停在「处理中」。逐级瘦身：
    1) 按体积比例截断各 markdown 正文（尾部保留截断标记，保底 256 字符）；
    2) 仍超限则折半砍最长的一段；
    3) 结构本身也撑爆时，从前往后丢元素（思考面板在前、最终答案在尾，优先保答案）。
    任何输入都不抛异常；幂等（已达标直接原样返回副本）。
    """
    import copy

    fitted = copy.deepcopy(card)
    size = _card_bytes(fitted)
    if size <= limit:
        return fitted
    nodes = list(_iter_markdown_nodes(fitted))
    # 第 1 级：按比例一刀切，给结构与截断标记留 15% 余量
    scale = (limit * 0.85) / size
    for node in nodes:
        content = node["content"]
        keep = max(256, int(len(content) * scale) - len(_CARDKIT_TRUNC_MARK))
        if keep < len(content):
            node["content"] = content[:keep] + _CARDKIT_TRUNC_MARK
    # 第 2 级：微调，反复折半当前最长的一段
    while _card_bytes(fitted) > limit:
        big = max((n for n in nodes if len(n["content"]) > 300),
                  key=lambda n: len(n["content"]), default=None)
        if big is None:
            break
        big["content"] = big["content"][: len(big["content"]) // 2] + _CARDKIT_TRUNC_MARK
    # 第 3 级：结构性超限，从前往后丢顶层元素（保尾部答案与 footer）
    elements = fitted.get("body", {}).get("elements")
    if isinstance(elements, list):
        while _card_bytes(fitted) > limit and len(elements) > 1:
            elements.pop(0)
    return fitted


# 拆卡保险丝：再能装也封顶，防异常输入下卡数失控
_MAX_OVERFLOW_CARDS = 20


def split_complete_card(card: dict[str, Any]) -> list[dict[str, Any]]:
    """完成卡超 140KB 安全线时按原文素顺序拆成多张卡，正文一字不丢。

    飞书单卡体积上限实测 148KB 过 / 150KB 拒（200860）。旧策略对全部 markdown
    一刀切截断（含答案正文）→ 用户看到「内容过长，已截断」。新策略贪心装箱：
    顶层元素按原顺序装进多张卡（主卡带原 header，续卡带「续第 k 页」标记），
    仅当单元素自身超单卡容量时才对它内部截断（_fit_card_bytes 保底语义）。
    任何输入都不抛异常；卡不超时返回单元素列表（ deepcopy，原样可发）。
    """
    import copy as _copy

    if _card_bytes(card) <= CARDKIT_SAFE_BYTES:
        return [_copy.deepcopy(card)]
    elements = (card.get("body") or {}).get("elements")
    if not isinstance(elements, list) or not elements:
        return [_fit_card_bytes(card)]

    # 骨架开销 = 空 body 的整卡字节 + JSON 括号余量
    skeleton = _copy.deepcopy(card)
    skeleton["body"]["elements"] = []
    skeleton.pop("summary", None)
    if isinstance(skeleton.get("config"), dict):
        skeleton["config"].pop("summary", None)
    base = _card_bytes(skeleton) + 256
    capacity = max(CARDKIT_SAFE_BYTES - base, 8 * 1024)

    bins: list[list[dict[str, Any]]] = []
    cur: list[dict[str, Any]] = []
    cur_size = 0

    def _flush() -> None:
        nonlocal cur, cur_size
        if cur:
            bins.append(cur)
            cur, cur_size = [], 0

    def _place(el: dict[str, Any]) -> None:
        nonlocal cur, cur_size
        size = _card_bytes(el)
        if cur and cur_size + size > capacity:
            _flush()
        cur.append(el)
        cur_size += size

    for el in elements:
        if _card_bytes(el) > capacity:
            # 面板超容量：把子元素按原顺序拆进多个同构面板，一个字不丢；
            # 非面板/拆不动的单元素才走内部截断保底。
            children = el.get("elements")
            if el.get("tag") == "collapsible_panel" and isinstance(children, list) and children:
                sub: list[dict[str, Any]] = []
                sub_size = 0
                panel_overhead = _card_bytes(el) - sum(_card_bytes(c) for c in children) + 64
                for ch in children:
                    ch_size = _card_bytes(ch)
                    if ch_size > capacity:  # 子元素自身超容 → 只截这一个
                        shrunk = _fit_card_bytes(
                            {"schema": "2.0", "body": {"elements": [_copy.deepcopy(ch)]}},
                            limit=int(capacity),
                        )["body"]["elements"]
                        for piece in shrunk:
                            if sub and sub_size + _card_bytes(piece) + panel_overhead > capacity:
                                frag = _copy.deepcopy(el)
                                frag["elements"] = sub
                                frag.pop("element_id", None)
                                _place(frag)
                                sub, sub_size = [], 0
                            sub.append(piece)
                            sub_size += _card_bytes(piece)
                        continue
                    if sub and sub_size + ch_size + panel_overhead > capacity:
                        frag = _copy.deepcopy(el)
                        frag["elements"] = sub
                        frag.pop("element_id", None)  # 避免跨卡 Duplicate ID
                        _place(frag)
                        sub, sub_size = [], 0
                    sub.append(_copy.deepcopy(ch))
                    sub_size += ch_size
                if sub:
                    frag = _copy.deepcopy(el)
                    frag["elements"] = sub
                    frag.pop("element_id", None)
                    _place(frag)
                continue
            # 单元素超容量：只对这一个元素做内部截断，其余正文不动
            shrunk = _fit_card_bytes(
                {"schema": "2.0", "body": {"elements": [_copy.deepcopy(el)]}},
                limit=int(capacity),
            )
            for piece in (shrunk.get("body") or {}).get("elements") or []:
                _place(piece)
            continue
        _place(_copy.deepcopy(el))
    _flush()

    # 保险丝：封顶 _MAX_OVERFLOW_CARDS，多余内容并进末卡并瘦身（极端巨型场景）
    if len(bins) > _MAX_OVERFLOW_CARDS:
        head, tail = bins[: _MAX_OVERFLOW_CARDS - 1], [e for b in bins[_MAX_OVERFLOW_CARDS - 1:] for e in b]
        fitted_tail = _fit_card_bytes(
            {"schema": "2.0", "body": {"elements": tail}}, limit=int(capacity)
        )["body"]["elements"]
        bins = head + [fitted_tail]

    if len(bins) == 1:
        return [_fit_card_bytes(card)]

    cards: list[dict[str, Any]] = []
    for i, bin_els in enumerate(bins):
        if i == 0:
            c = _copy.deepcopy(card)
            c["body"]["elements"] = bin_els
        else:
            c = _copy.deepcopy(skeleton)
            c["body"]["elements"] = [
                {"tag": "markdown",
                 "content": f"⏳ 续第 {i + 1} 页（上一条消息因体积超限自动分条，正文未删减）"}
            ] + bin_els
        cards.append(c)
    return cards


def _truncate_model(name: str) -> str:
    """截断模型名：or/lc/LongCat-2.0 → ⇲LongCat-2.0（保留最后一段）.

    如果开启 truncate_model_name 才调用；未开启时原样返回。
    """
    if not name:
        return name
    parts = name.split("/")
    if len(parts) > 1:
        return f"⇲{parts[-1]}"
    return name


def _display_model(name: str) -> str:
    """模型显示名：别名优先（~/.hermes/model_aliases.json 子串匹配），未命中回落截断逻辑.

    别名文件由 Config().model_aliases() 每次重读（热更新）；命中即返回别名，
    未命中且 truncate_model_name 开启时走 _truncate_model。
    """
    if not name:
        return name
    from ..config import Config

    cfg = Config()
    aliases = cfg.model_aliases()
    lowered = name.lower()
    for key, alias in aliases.items():
        if key and key in lowered:
            return alias
    if cfg.truncate_model_name:
        return _truncate_model(name)
    return name


def _collapsible_panel(
    *,
    expanded: bool,
    title_el: dict,
    elements: list[dict],
    vertical_spacing: str = "4px",
    icon_position: str = "right",
) -> dict:
    icon_el = {
        "tag": "standard_icon",
        "token": "down-small-ccm_outlined",
        "size": "16px 16px",
    }
    if icon_position == "right":
        icon_el["color"] = "grey"
    return {
        "tag": "collapsible_panel",
        "expanded": expanded,
        "header": {
            "title": title_el,
            "vertical_align": "center",
            "icon": icon_el,
            "icon_position": icon_position,
            "icon_expanded_angle": -180,
        },
        "border": {"color": "grey", "corner_radius": "5px"},
        "vertical_spacing": vertical_spacing,
        "padding": "8px 8px 8px 8px",
        "elements": elements,
    }


def _streaming_element(
    content: str = "",
    *,
    element_id: str = STREAMING_ELEMENT_ID,
    text_size: str = "normal_v2",
) -> dict:
    return {
        "tag": "markdown",
        "content": content,
        "text_align": "left",
        "text_size": text_size,
        "margin": "0px 0px 0px 0px",
        "element_id": element_id,
    }


_HEADER_STATES: dict[str, dict[str, str]] = {
    "streaming": {"template": "blue", "i18n_key": "processing_prefix"},
    "completed": {"template": "green", "i18n_key": "status_completed"},
    "error": {"template": "red", "i18n_key": "status_error"},
    "stopped": {"template": "red", "i18n_key": "status_stopped"},
}


def _build_header(status: str) -> dict[str, Any]:
    """构建卡片级 header — 流式蓝 / 完成绿 / 停止红."""
    cfg = _HEADER_STATES.get(status, _HEADER_STATES["completed"])
    en_text, zh_text = _T[cfg["i18n_key"]]
    return {
        "title": {
            "tag": "plain_text",
            "content": en_text,
            "i18n_content": _i18n(en_text, zh_text),
        },
        "template": cfg["template"],
    }


def _loading_element() -> dict:
    return {
        "tag": "markdown",
        "content": " ",
        "icon": {
            "tag": "custom_icon",
            "img_key": _LOADING_IMG_KEY,
            "size": "16px 16px",
        },
        "element_id": _LOADING_ELEMENT_ID,
    }


def _build_tool_panel(
    steps: list[ToolDisplayStep],
    elapsed_ms: float = 0,
    *,
    expanded: bool = True,
    element_id: str | None = TOOL_PANEL_ELEMENT_ID,
) -> dict:
    en_t, zh_t = _T["tool_use"]
    en_parts, zh_parts = [en_t], [zh_t]
    if steps:
        tpl_en, tpl_zh = _T["steps"]
        en_parts.append(tpl_en.format(len(steps), "s" if len(steps) > 1 else ""))
        zh_parts.append(tpl_zh.format(len(steps), ""))
    if elapsed_ms > 0:
        en_parts.append(f"({_format_elapsed(elapsed_ms)})")
        zh_parts.append(f"({_format_elapsed(elapsed_ms)})")

    children: list[dict] = []
    for s in steps:
        children.extend(_build_tool_step_elements(s))

    panel = _collapsible_panel(
        expanded=expanded,
        title_el={
            "tag": "plain_text",
            "content": f"🔧 {' · '.join(en_parts)}",
            "i18n_content": _i18n(f"🔧 {' · '.join(en_parts)}", f"🔧 {' · '.join(zh_parts)}"),
            "text_color": "grey",
            "text_size": "notation",
        },
        elements=children,
    )
    if element_id:
        panel["element_id"] = element_id
    return panel


def _build_tool_step_elements(step: ToolDisplayStep) -> list[dict]:
    elements: list[dict] = [_build_tool_step_title(step)]
    detail = _build_tool_step_detail(step)
    if detail:
        elements.append(detail)
    output = _build_tool_step_output(step)
    if output:
        elements.append(output)
    return elements


def _build_tool_step_title(step: ToolDisplayStep) -> dict:
    status = step.get("status", "running")
    status_info = _tool_status_info(status)
    title = step.get("title", step.get("name", "tool"))
    content = f"**{_escape_md(title)}** · <font color='{status_info['color']}'>{status_info['label']}</font>"
    return {
        "tag": "div",
        "icon": {
            "tag": "standard_icon",
            "token": step.get("icon", "tool_02"),
            "color": "grey",
        },
        "text": {
            "tag": "lark_md",
            "content": content,
            "text_size": "notation",
        },
    }


def _build_tool_step_detail(step: ToolDisplayStep) -> dict | None:
    detail = step.get("detail", "").strip()
    if not detail:
        return None
    return {
        "tag": "div",
        "margin": "0px 0px 0px 22px",
        "text": {
            "tag": "plain_text",
            "content": detail,
            "text_color": "grey",
            "text_size": "notation",
        },
    }


def _build_tool_step_output(step: ToolDisplayStep) -> dict | None:
    error_block = step.get("error_block")
    result_block = step.get("result_block")

    lines: list[str] = []
    if error_block:
        lines.append("**Error**")
        lines.append(
            error_block.get("fenced")
            or _format_code_block(error_block.get("content", ""), error_block.get("language", "text"))
        )
    elif result_block:
        lines.append("**Result**")
        lines.append(
            result_block.get("fenced")
            or _format_code_block(result_block.get("content", ""), result_block.get("language", "json"))
        )

    if not lines:
        return None

    return {
        "tag": "div",
        "margin": "0px 0px 0px 22px",
        "text": {
            "tag": "lark_md",
            "content": "\n".join(lines),
            "text_size": "notation",
        },
    }


def _tool_status_info(status: str) -> dict[str, str]:
    return {
        "running": {"label": "Running", "color": "turquoise"},
        "success": {"label": "Succeeded", "color": "green"},
        "error": {"label": "Failed", "color": "red"},
    }.get(status, {"label": status.capitalize(), "color": "grey"})


def _format_code_block(content: str, language: str) -> str:
    normalized = content.replace("\r\n", "\n").strip()
    fence = "`" * max(3, _longest_backtick_run(normalized) + 1)
    return f"{fence}{language}\n{normalized}\n{fence}"


def _longest_backtick_run(value: str) -> int:
    matches = re.findall(r"`+", value)
    return max((len(m) for m in matches), default=0)


def _escape_md(value: str) -> str:
    return re.sub(r"([`*_{}\[\]<>])", r"\\\1", value.replace("\\", "\\\\"))


def _build_reasoning_panel(
    text: str, elapsed_ms: float = 0, *, expanded: bool = False, element_id: str | None = None,
    text_element_id: str | None = REASONING_TEXT_ELEMENT_ID,
) -> dict:
    if elapsed_ms > 0:
        d = _format_elapsed(elapsed_ms)
        en_label, zh_label = _T["thought_for"][0].format(d), _T["thought_for"][1].format(d)
    elif not text.strip():
        en_label, zh_label = _T["thinking_panel"]
    else:
        en_label, zh_label = _T["thought"]
    panel = _collapsible_panel(
        expanded=expanded,
        title_el={
            "tag": "plain_text",
            "content": f"💭 {en_label}",
            "i18n_content": _i18n(f"💭 {en_label}", f"💭 {zh_label}"),
            "text_color": "grey",
            "text_size": "notation",
        },
        elements=[{
            "tag": "markdown",
            "content": text,
            "text_size": "notation",
            **({"element_id": text_element_id} if text_element_id else {}),
        }],
        vertical_spacing="8px",
    )
    if element_id:
        panel["element_id"] = element_id
    return panel


def _build_footer_elements(
    footer_data: dict | None,
    is_error: bool = False,
    is_aborted: bool = False,
    fields: list[list[str]] | None = None,
    show_label: bool = False,
    text_size: str = "notation",
) -> list[dict]:
    if fields is None:
        fields = [["status", "elapsed", "context", "model"]]

    data = footer_data or {}
    en_lines: list[str] = []
    zh_lines: list[str] = []
    for row in fields:
        en_parts: list[str] = []
        zh_parts: list[str] = []
        for field in row:
            en, zh = _render_footer_field(field, data, is_error, is_aborted, show_label)
            if en:
                en_parts.append(en)
                if zh:
                    zh_parts.append(zh)
        if en_parts:
            en_lines.append(" · ".join(en_parts))
            zh_lines.append(" · ".join(zh_parts))

    if not en_lines:
        return []

    en_content = "\n".join(en_lines)
    zh_content = "\n".join(zh_lines)
    if is_error:
        en_content = f"<font color='red'>{en_content}</font>"
        zh_content = f"<font color='red'>{zh_content}</font>"

    return [
        {
            "tag": "markdown",
            "content": en_content,
            "i18n_content": _i18n(en_content, zh_content),
            "text_size": text_size,
        },
    ]


def _render_footer_field(
    name: str,
    data: dict,
    is_error: bool,
    is_aborted: bool,
    show_label: bool,
) -> tuple[str | None, str | None]:
    if name == "status":
        if is_error:
            return _T["status_error"]
        if is_aborted:
            return _T["status_stopped"]
        return _T["status_completed"]

    if name == "elapsed":
        duration = data.get("duration", 0)
        if isinstance(duration, (int, float)) and duration > 0:
            val = _format_elapsed(duration * 1000)
            if show_label:
                return _T["elapsed"][0].format(val), _T["elapsed"][1].format(val)
            return val, val
        return None, None

    if name == "model":
        v = data.get("model") or None
        if v:
            v = _display_model(v)
        return v, v

    if name == "tokens":
        input_t = data.get("input_tokens", 0) or 0
        output_t = data.get("output_tokens", 0) or 0
        if input_t or output_t:
            v = f"↑ {_compact(input_t)} ↓ {_compact(output_t)}"
            return v, v
        return None, None

    if name == "context":
        used = data.get("context_used", 0) or 0
        max_c = data.get("context_max", 0) or 0
        if max_c:
            pct = int(used / max_c * 100)
            val = f"{_compact(used)}/{_compact(max_c)} ({pct}%)"
            if show_label:
                return _T["context"][0].format(val), _T["context"][1].format(val)
            return val, val
        return None, None

    return None, None


def _compact(n: int) -> str:
    if n >= 1_000_000:
        m = n / 1_000_000
        return f"{int(m)}M" if m >= 100 else f"{m:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _format_elapsed(ms: float) -> str:
    seconds = ms / 1000
    return f"{seconds:.1f}s" if seconds < 60 else f"{int(seconds // 60)}m {int(seconds % 60)}s"


_CONTEXT_BAR_STEPS = ("█", "▓", "▒", "░")  # 实 → 半实 → 半空 → 空，渐变阴影


def _context_progress_bar(used: int, total: int, width: int = 8) -> str:
    """生成渐变阴影进度条，格式: ███▓▒░░░（实心到空的密度渐变）"""
    if total <= 0:
        return ""
    pct = min(used / total * 100, 100)
    n = pct / 100 * width  # 浮点进度位置（0..width）
    cells: list[str] = []
    for i in range(width):
        pos = i + 0.5  # 每格中心
        if pos <= n:
            # 完全填满的格子：除了最靠近边界的一格，其余都是实心
            if n - pos >= 0.5:
                cells.append("█")
            elif n - pos >= 0.25:
                cells.append("▓")
            else:
                cells.append("▒")
        elif pos - 1 <= n:
            # 边界格：按剩余进度选密度
            frac = n - (pos - 1)  # 0..1
            if frac > 0.66:
                cells.append("▓")
            elif frac > 0.33:
                cells.append("▒")
            else:
                cells.append("░")
        else:
            cells.append("░")
    return "".join(cells)


def _context_progress_block(used: int, total: int, width: int = 10) -> str:
    """[已废弃] block 样式在桌面端/移动端显示不一致，不再使用."""
    return _context_progress_bar(used, total, width)


def _context_text(used: int, total: int) -> str:
    """生成上下文纯文本，格式: 55.6k/1.0m (5%)"""
    if total <= 0:
        return ""
    pct = min(used / total * 100, 100)
    if total >= 1_000_000:
        # total 用 m，used 根据大小用 k 或 m
        total_str = f"{total / 1_000_000:.1f}m"
        if used < 1_000_000:
            used_str = f"{used / 1_000:.1f}k"
        else:
            used_str = f"{used / 1_000_000:.1f}m"
        return f"{used_str}/{total_str} ({pct:.0f}%)"
    if total >= 1_000:
        return f"{used / 1_000:.1f}k/{total / 1_000:.1f}k ({pct:.0f}%)"
    return f"{used}/{total} ({pct:.0f}%)"


def _context_pct(used: int, total: int) -> str:
    """生成上下文使用百分比，格式: 35%"""
    if total <= 0:
        return ""
    pct = min(used / total * 100, 100)
    return f"{pct:.0f}%"


def _context_progress_with_text(used: int, total: int, width: int = 8) -> str:
    """生成文本+渐变进度条，格式: 55.6k/1.0m [███▓▒░░░] 5%"""
    if total <= 0:
        return ""
    pct = min(used / total * 100, 100)
    bar = _context_progress_bar(used, total, width)
    if total >= 1_000_000:
        total_str = f"{total / 1_000_000:.1f}m"
        if used < 1_000_000:
            used_str = f"{used / 1_000:.1f}k"
        else:
            used_str = f"{used / 1_000_000:.1f}m"
        return f"{used_str}/{total_str} [{bar}] {pct:.0f}%"
    if total >= 1_000:
        return f"{used / 1_000:.1f}k/{total / 1_000:.1f}k [{bar}] {pct:.0f}%"
    return f"{used}/{total} [{bar}] {pct:.0f}%"


def build_streaming_tool_use_pending_panel() -> dict[str, Any]:
    panel = _collapsible_panel(
        expanded=False,
        title_el={
            "tag": "plain_text",
            "content": _T["tool_pending"][0],
            "i18n_content": _t("tool_pending"),
            "text_color": "grey",
            "text_size": "notation",
        },
        elements=[],
    )
    panel["element_id"] = TOOL_PANEL_ELEMENT_ID
    return panel


def build_streaming_card_v2(
    *,
    tool_steps: list[ToolDisplayStep] | None = None,
    elapsed_ms: float = 0,
    show_tool_use: bool = True,
    show_reasoning: bool = False,
    show_streaming_element: bool = True,
    header_enabled: bool = False,
    text_size: str = "normal_v2",
    width_mode: str = "default",
) -> dict[str, Any]:
    """CardKit 2.0 流式占位卡片 — 工具面板合并到底部."""
    elements: list[dict] = []

    if show_reasoning:
        elements.append(
            _build_reasoning_panel(" ", expanded=True, element_id=REASONING_ELEMENT_ID)
        )

    if show_streaming_element:
        elements.append(_streaming_element(text_size=text_size))

    # 工具面板放在底部（answer之后，loading之前）
    if show_tool_use:
        if tool_steps:
            elements.append(_build_tool_panel(tool_steps, elapsed_ms))
        else:
            elements.append(build_streaming_tool_use_pending_panel())

    elements.append(_loading_element())

    card = {
        "schema": "2.0",
        "config": {
            "width_mode": width_mode,
            "streaming_mode": True,
            "streaming_config": {
                "print_frequency_ms": {"default": 15},
                "print_step": {"default": 1},
                "print_strategy": "fast",
            },
            "locales": _LOCALES,
            "summary": {
                "content": _T["processing"][0],
                "i18n_content": _t("processing"),
            },
        },
        "body": {"elements": elements},
    }
    if header_enabled:
        card["header"] = _build_header("streaming")
    return card


def build_complete_card(
    *,
    segments: list[Segment],
    all_tool_steps: list[ToolDisplayStep],
    footer_data: dict | None = None,
    is_error: bool = False,
    is_aborted: bool = False,
    footer_fields: list[list[str]] | None = None,
    footer_show_label: bool = True,
    footer_enabled: bool = True,
    footer_text_size: str = "notation",
    panel_expanded: bool = False,
    header_enabled: bool = False,
    body_text_size: str = "normal_v2",
    show_tool_use: bool = True,
    width_mode: str = "default",
) -> dict[str, Any]:
    """完成态流式卡片 — 推理+工具合并成底部统一面板，答案在上面."""
    elements: list[dict] = []
    has_answer = False
    # 收集所有 reasoning rounds + tool steps，合并成一个底部统一面板
    reasoning_rounds: list[dict] = []
    tool_steps_total: list[ToolDisplayStep] = []
    tool_elapsed_ms = 0

    for seg in segments:
        if seg.type == SegmentType.REASONING:
            if seg.text:
                reasoning_rounds.append({
                    "text": seg.text,
                    "elapsed_ms": seg.elapsed_ms,
                    "text_el_id": seg.text_el_id,  # 复用流式阶段的 text element id，避免完成态 Duplicate ID
                })
        elif seg.type == SegmentType.TOOL:
            if not show_tool_use:
                continue
            start = seg.tool_offset
            end = seg.tool_end_offset if seg.tool_end_offset else len(all_tool_steps)
            steps = all_tool_steps[start:end]
            if steps:
                tool_steps_total.extend(steps)
                tool_elapsed_ms += seg.elapsed_ms or 0
        elif seg.type == SegmentType.ANSWER and seg.text:
            has_answer = True
            content = _downgrade_tables(optimize_markdown_style(seg.text))
            for chunk in _split_long_text(content):
                # WO-0916-HARDEN-01 A3：单段按 UTF-8 字节钳制（中文 3 字节膨胀坑——
                # 字符级 2400 预算在中文下可膨胀到 7200+ 字节，飞书按字节计）
                chunk = clamp_utf8(chunk, _ANSWER_ELEMENT_BUDGET_BYTES)
                elements.append({"tag": "markdown", "content": chunk, "text_size": body_text_size})

    # 推理+工具合并成底部一个统一面板（在答案之后、footer 之前）
    # 短回复或无工具调用时不展示统一面板（避免冗余 header）
    _panel_duration_ms = 0
    if footer_data:
        _d = footer_data.get("duration")
        if isinstance(_d, (int, float)) and _d > 0:
            _panel_duration_ms = _d * 1000
    _min_duration_ms = 0
    try:
        from ..config import Config
        _min_duration_ms = float(Config().unified_panel_min_duration) * 1000
    except Exception:
        _min_duration_ms = 5000
    _show_unified_panel = (
        (reasoning_rounds or tool_steps_total)
        and show_tool_use
        and (tool_steps_total or _panel_duration_ms >= _min_duration_ms)
    )
    if _show_unified_panel:
        # 状态边框颜色：完成=绿色, 中断=黄色, 异常=红色
        if is_error:
            border_color = "red"
        elif is_aborted:
            border_color = "yellow"
        else:
            border_color = "green"
        # 构建统一面板内容：先推理轮次，再工具步骤
        unified_children: list[dict] = []
        for i, rnd in enumerate(reasoning_rounds):
            if rnd["text"].strip():
                # 复用流式阶段 text_el_id，避免与已完成卡片上现有元素重名（Duplicate ID）。
                # 流式阶段 text_el_id 形如 reasoning_{c}_text，非空；若为空则用带索引后缀的唯一 ID，
                # 绝不回落到固定 REASONING_TEXT_ELEMENT_ID，防止单轮 reasoning 在 merge 更新下重复。
                text_el_id = rnd.get("text_el_id") or f"reasoning_text_{i}"
                unified_children.append(_build_reasoning_panel(
                    text=rnd["text"],
                    elapsed_ms=rnd["elapsed_ms"],
                    expanded=panel_expanded,
                    text_element_id=text_el_id,
                ))
        if tool_steps_total:
            # payload 封顶（与流式面板同口径）：seal 全量重建灌入全部历史步骤会直接
            # 300305/200860 被拒 → 旧卡永远停在转圈态（今天 4 次 seal failed 实证）。
            tool_steps_total, _omitted_steps = cap_tool_steps(tool_steps_total)
            # WO-0916-HARDEN-01 A3：字节预算第二层——步数封顶防不住 N 个中等输出的
            # 字节膨胀，超 _PANEL_BUDGET_BYTES 从最老步骤折叠（保最近 2 步）。
            def _steps_bytes(steps: list[ToolDisplayStep]) -> int:
                return sum(
                    len(json.dumps(el, ensure_ascii=False).encode("utf-8"))
                    for s in steps
                    for el in _build_tool_step_elements(s)
                )

            while len(tool_steps_total) > 2 and _steps_bytes(tool_steps_total) > _PANEL_BUDGET_BYTES:
                tool_steps_total = tool_steps_total[1:]
            tool_panel = _build_tool_panel(tool_steps_total, tool_elapsed_ms, expanded=panel_expanded, element_id=None)
            if "elements" in tool_panel:
                unified_children.extend(tool_panel["elements"])
        # header: 🍟 model · 💭n · 🔧n · ⏳ context · ⏱️ elapsed
        model_name = (footer_data or {}).get("model") or ""
        if model_name:
            model_name = _display_model(model_name)
        # 优先用 tool_elapsed_ms，否则用 footer_data 的 duration，否则用 session 总耗时
        elapsed_ms = tool_elapsed_ms
        if not elapsed_ms and footer_data:
            duration = footer_data.get("duration")
            if isinstance(duration, (int, float)) and duration > 0:
                elapsed_ms = duration * 1000
        elapsed_str = _format_elapsed(elapsed_ms) if elapsed_ms else ""
        elapsed_part = f" · ⏱️ {elapsed_str}" if elapsed_str else ""
        # 上下文信息：支持进度条 / 纯文本，通过配置独立控制
        context_part = ""
        if footer_data:
            ctx_used = footer_data.get("context_used", 0) or 0
            ctx_max = footer_data.get("context_max", 0) or 0
            if ctx_used > 0 and ctx_max > 0:
                from ..config import Config
                cfg = Config()
                if cfg.show_context:
                    mode = cfg.context_display_mode
                    if mode == "text":
                        context_part = f" · {_context_text(ctx_used, ctx_max)}"
                    elif mode == "bar":
                        context_part = f" · [{_context_progress_bar(ctx_used, ctx_max)}] {_context_pct(ctx_used, ctx_max)}"
                    elif mode == "block":
                        # [已废弃] block 样式桌面/移动端显示不一致，回落到 bar
                        context_part = f" · [{_context_progress_bar(ctx_used, ctx_max)}] {_context_pct(ctx_used, ctx_max)}"
                    elif mode == "block_text":
                        # [已废弃] block_text 同步回落为 text_bar（渐变样式）
                        context_part = f" · {_context_progress_with_text(ctx_used, ctx_max)}"
                    else:  # text_bar
                        context_part = f" · {_context_progress_with_text(ctx_used, ctx_max)}"
        header_text = f"🍟 {model_name} · 💭{len(reasoning_rounds)} · 🔧{len(tool_steps_total)}{context_part}{elapsed_part}"
        unified_panel = {
            "tag": "collapsible_panel",
            "expanded": panel_expanded,
            "header": {
                "title": {"tag": "plain_text", "content": header_text},
                "text_color": "grey", "text_size": "notation",
            },
            "border": {"color": border_color, "corner_radius": "5px"},
            "elements": unified_children,
        }
        elements.append(unified_panel)

    if not has_answer:
        elements.append({"tag": "markdown", "content": _T["done"][0], "text_size": body_text_size})

    if footer_enabled:
        elements.extend(
            _build_footer_elements(
                footer_data,
                is_error,
                is_aborted,
                fields=footer_fields,
                show_label=footer_show_label,
                text_size=footer_text_size,
            )
        )

    summary_text = ""
    for seg in reversed(segments):
        if seg.type in (SegmentType.ANSWER, SegmentType.REASONING) and seg.text:
            summary_text = seg.text
            break
    summary = summary_text[:120].replace("\n", " ").replace("```", "").strip()

    card: dict[str, Any] = {
        "schema": "2.0",
        "config": {
            "width_mode": width_mode,
            "wide_screen_mode": True,
            "update_multi": True,
            "locales": _LOCALES,
        },
    }
    if summary:
        card["config"]["summary"] = {"content": summary}
    card["body"] = {"elements": elements}
    if header_enabled:
        header_status = "error" if is_error else "stopped" if is_aborted else "completed"
        card["header"] = _build_header(header_status)
    # 体积治理移交调用方（2026-09-15 分条改造）：complete 路径用 split_complete_card
    # 拆多卡保全文；seal 路径自行 _fit_card_bytes 瘦身（封卡是过渡态，截了无妨）。
    return card


def _format_run_time(run_time: str) -> str:
    """将 ISO 时间戳格式化为可读日期时间，失败则原样返回."""
    if not run_time:
        return ""
    try:
        dt = datetime.fromisoformat(run_time)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return run_time


def build_cron_card(
    content: str, *, task_name: str = "", run_time: str = ""
) -> dict[str, Any]:
    """Cron 推送用的极简静态卡片 — schema 2.0，可选 header + markdown 内容."""
    card: dict[str, Any] = {
        "schema": "2.0",
        "config": {"wide_screen_mode": True, "locales": _LOCALES},
        "body": {"elements": []},
    }
    header_parts = [p for p in (task_name, _format_run_time(run_time)) if p]
    if header_parts:
        card["header"] = {
            "title": {"tag": "lark_md", "content": ":Alarm: " + " · ".join(header_parts)},
            "template": "blue",
        }
    if not content.strip():
        return card
    summary = content[:120].replace("\n", " ").replace("```", "").strip()
    if summary:
        card["config"]["summary"] = {"content": summary}
    for chunk in _split_long_text(optimize_markdown_style(content)):
        if chunk.strip():
            card["body"]["elements"].append({"tag": "markdown", "content": chunk})
    return card


def build_background_card(preview: str, content: str) -> dict[str, Any]:
    """Background 任务完成推送卡片 — schema 2.0，header + markdown."""
    card: dict[str, Any] = {
        "schema": "2.0",
        "config": {"wide_screen_mode": True, "locales": _LOCALES},
        "header": {
            "title": {"tag": "plain_text", "content": f"✅ Background: \"{preview}\""},
        },
        "body": {"elements": []},
    }
    body = content if content.strip() else "(No response generated)"
    summary = body[:120].replace("\n", " ").replace("```", "").strip()
    if summary:
        card["config"]["summary"] = {"content": summary}
    for chunk in _split_long_text(optimize_markdown_style(body)):
        if chunk.strip():
            card["body"]["elements"].append({"tag": "markdown", "content": chunk})
    return card
