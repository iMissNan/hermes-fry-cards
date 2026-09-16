"""Markdown 文本处理 — 标题降级、表格降级、图片 key 剥离、长文本分块."""

from __future__ import annotations

import logging
import re

_logger = logging.getLogger("hermes_fry_cards")

_MAX_CARD_TABLES = 5
_MAX_CHUNK_CHARS = 2400

__all__ = [
    "_downgrade_tables",
    "_find_tables_outside_code_blocks",
    "_split_long_text",
    "_strip_invalid_image_keys",
    "clamp_utf8",
    "optimize_markdown_style",
]


def clamp_utf8(text: str, max_bytes: int = 7000, preserve_tail: bool = True) -> str:
    """按 UTF-8 字节数钳制文本——二分找字节安全边界，绝不切断多字节字符.

    WO-0916-HARDEN-01 A3（设计借鉴 aiduPOP (monkey2jack, MIT) cardkit/md.py clamp_utf8）：
    中文 3 字节/字、emoji 4 字节/字，字符级预算在飞书 JSON 侧会膨胀爆掉；
    preserve_tail=True 用于完成态封卡（60% 头 + 40% 尾 + 中段省略标记，
    确保开头背景与末尾结论都不丢）；False 用于流式渐进截断。
    任何输入不抛异常；text 在预算内时原样返回（零误伤）。
    """
    if len(text.encode("utf-8")) <= max_bytes:
        return text

    if not preserve_tail:
        suffix = "\n\n…（内容过长已截断，防卡片溢出）…"  # noqa: RUF001
        budget = max_bytes - len(suffix.encode("utf-8"))
        if budget <= 0:
            return suffix[: max(0, max_bytes)]
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if len(text[:mid].encode("utf-8")) <= budget:
                lo = mid
            else:
                hi = mid - 1
        return text[:lo] + suffix

    # 首尾双保：60% 头 + 40% 尾 + 中段省略标记
    omission_tag = "\n\n…（中段已省略，保留开头与末尾，防卡片溢出）…\n\n"  # noqa: RUF001
    tag_bytes = len(omission_tag.encode("utf-8"))
    net_budget = max_bytes - tag_bytes
    if net_budget <= 0:
        # 极端小预算：退化为纯尾部截断
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if len(text[:mid].encode("utf-8")) <= max_bytes:
                lo = mid
            else:
                hi = mid - 1
        return text[:lo]

    head_budget = int(net_budget * 0.60)
    tail_budget = net_budget - head_budget

    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if len(text[:mid].encode("utf-8")) <= head_budget:
            lo = mid
        else:
            hi = mid - 1
    head_text = text[:lo]

    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if len(text[-mid:].encode("utf-8")) <= tail_budget:
            lo = mid
        else:
            hi = mid - 1
    tail_text = text[-lo:] if lo > 0 else ""

    return head_text + omission_tag + tail_text


def _find_tables_outside_code_blocks(text: str) -> list[tuple[int, int, str]]:
    """查找代码块外的 markdown 表格，返回 [(start, end, raw), ...]."""
    code_ranges: list[tuple[int, int]] = []
    for m in re.finditer(r"```[\s\S]*?```", text):
        code_ranges.append((m.start(), m.end()))

    def _in_code(idx: int) -> bool:
        return any(s <= idx < e for s, e in code_ranges)

    results: list[tuple[int, int, str]] = []
    for m in re.finditer(r"\|.+\|\n\|[-:| ]+\|[\s\S]*?(?=\n\n|\n(?!\|)|$)", text):
        if not _in_code(m.start()):
            results.append((m.start(), m.end(), m.group(0)))
    return results


def _downgrade_tables(text: str, limit: int = _MAX_CARD_TABLES) -> str:
    """超限表格降级为代码块（保留内容可见但飞书不渲染为表格元素）."""
    matches = _find_tables_outside_code_blocks(text)
    if len(matches) <= limit:
        return text
    result = text
    for start, end, raw in reversed(matches[limit:]):
        replacement = f"```\n{raw}\n```"
        result = result[:start] + replacement + result[end:]
    return result


def _strip_invalid_image_keys(text: str) -> str:
    """移除非 img_ 前缀的图片引用."""
    if "![" not in text:
        return text

    def _replace(m: re.Match) -> str:
        return m.group(0) if m.group(2).startswith("img_") else ""

    return re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", _replace, text)


def optimize_markdown_style(text: str) -> str:
    """优化流式 Markdown 以适配飞书 CardKit 渲染.

    1. 提取代码块用占位符保护
    2. 标题降级: H1 -> H4, H2-H6 -> H5
    3. 还原代码块
    4. 压缩多余空行
    5. 剥离无效图片 key（非 img_xxx 格式）
    """
    try:
        # 1. 提取代码块
        mark = "___CB_"
        code_blocks: list[str] = []

        def _extract(m: re.Match) -> str:
            prefix = m.group(1) or ""
            block = m.group(0)[len(prefix) :]
            idx = len(code_blocks)
            code_blocks.append(block)
            return f"{prefix}{mark}{idx}___"

        r = re.sub(r"(^|\n)(`{3,})([^\n]*)\n[\s\S]*?\n\2(?=\n|$)", _extract, text)

        # 2. 标题降级（仅当存在 H1-H3 时）
        if re.search(r"^#{1,3} ", text, re.MULTILINE):
            r = re.sub(r"^#{2,6} (.+)$", r"##### \1", r, flags=re.MULTILINE)
            r = re.sub(r"^# (.+)$", r"#### \1", r, flags=re.MULTILINE)

        # 3. 还原代码块
        for i, block in enumerate(code_blocks):
            r = r.replace(f"{mark}{i}___", block)

        # 4. 压缩多余空行
        r = re.sub(r"\n{3,}", "\n\n", r)

        # 5. 剥离无效图片 key
        r = _strip_invalid_image_keys(r)

        return r
    except Exception:
        _logger.debug("optimize_markdown_style failed", exc_info=True)
        return text


def _split_long_text(text: str, limit: int = _MAX_CHUNK_CHARS) -> list[str]:
    """将超长文本按段落/换行拆分为多个不超过 limit 字符的块."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        cut = text.rfind("\n\n", 0, limit)
        if cut < limit // 2:
            cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return chunks
