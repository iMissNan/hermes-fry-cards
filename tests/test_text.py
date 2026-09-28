"""streaming.text 测试 — reasoning 标签解析."""

from __future__ import annotations

import pytest

from hermes_fry_cards.streaming.text import (
    extract_thinking_content,
    split_reasoning_text,
    strip_reasoning_tags,
)


class TestSplitReasoningText:
    @pytest.mark.parametrize("text", [None, "", "   \n  "], ids=["none", "empty", "whitespace"])
    def test_empty_input_returns_empty(self, text: str | None) -> None:
        assert split_reasoning_text(text) == {}

    def test_plain_text_no_tags(self) -> None:
        assert split_reasoning_text("Hello world") == {"answer_text": "Hello world"}

    def test_reasoning_prefix(self) -> None:
        result = split_reasoning_text("Reasoning:\nstep 1\nstep 2")
        assert result.keys() == {"reasoning_text"}
        assert "step 1" in result["reasoning_text"]

    def test_reasoning_prefix_strips_underscore_lines(self) -> None:
        result = split_reasoning_text("Reasoning:\n_thinking_\ndone")
        assert "_thinking_" not in (result.get("reasoning_text") or "")

    def test_reasoning_prefix_too_short_ignored(self) -> None:
        # "Reasoning:\n" 单独存在不比前缀长，应走普通文本逻辑
        assert split_reasoning_text("Reasoning:\n") == {"answer_text": "Reasoning:\n"}

    @pytest.mark.parametrize(
        ("tag", "reasoning", "answer"),
        [
            ("thinking", "deep thoughts", "answer here"),
            ("thought", "reasoning", "the answer"),
            ("antthinking", "model thoughts", "response"),
        ],
    )
    def test_supported_reasoning_tags(self, tag: str, reasoning: str, answer: str) -> None:
        text = f"<{tag}>{reasoning}</{tag}>{answer}"
        result = split_reasoning_text(text)
        assert result["reasoning_text"] == reasoning
        assert answer in result["answer_text"]

    def test_tags_with_whitespace(self) -> None:
        text = "< thinking >content< /thinking >rest"
        result = split_reasoning_text(text)
        assert result["reasoning_text"] == "content"

    def test_unclosed_tag(self) -> None:
        text = "<thinking>ongoing reasoning"
        result = split_reasoning_text(text)
        assert result["reasoning_text"] == "ongoing reasoning"
        # 未闭合标签的内容属于推理，answer 不应残留
        assert result["answer_text"] is None


class TestExtractThinkingContent:
    def test_empty_string(self) -> None:
        assert extract_thinking_content("") == ""

    def test_no_tags(self) -> None:
        assert extract_thinking_content("plain text") == ""

    def test_single_pair(self) -> None:
        assert extract_thinking_content("<thinking>hello</thinking>") == "hello"

    def test_multiple_pairs(self) -> None:
        text = "<thinking>part1</thinking>ignored<thinking>part2</thinking>"
        assert extract_thinking_content(text) == "part1part2"

    def test_unclosed_tag_extracts_till_end(self) -> None:
        assert extract_thinking_content("<thinking>rest of text") == "rest of text"

    def test_case_insensitive(self) -> None:
        assert extract_thinking_content("<THOUGHT>content</THOUGHT>") == "content"


class TestStripReasoningTags:
    def test_removes_complete_block_with_content(self) -> None:
        # 完整块连同内容一起移除，否则 reasoning 泄漏进 answer，
        # 完成卡片上与 💭 面板前后重复
        assert strip_reasoning_tags("<thinking>content</thinking>") == ""

    def test_mixed_text_keeps_surrounding(self) -> None:
        text = "before<thinking>inner</thinking>after"
        result = strip_reasoning_tags(text)
        assert result == "beforeafter"

    def test_removes_multiple_blocks(self) -> None:
        text = "a<thinking>x</thinking>b<thought>y</thought>c"
        assert strip_reasoning_tags(text) == "abc"

    def test_unclosed_tail_removed(self) -> None:
        assert strip_reasoning_tags("answer<thinking>tail to end") == "answer"

    def test_stray_close_tag_removed(self) -> None:
        # 跨 delta 拆分的残留闭合记号（无内容可删）只清记号
        assert strip_reasoning_tags("hello </thinking>world") == "hello world"

    def test_no_tags_unchanged(self) -> None:
        assert strip_reasoning_tags("no tags here") == "no tags here"

    def test_reasoning_prefix_clears_all(self) -> None:
        result = strip_reasoning_tags("Reasoning:\nsome content")
        assert result.strip() == ""

    def test_hermes_reasoning_prepend_stripped(self) -> None:
        # Hermes show_reasoning 开启时最终 response 前置的推理块，
        # 完成卡片正文不应再渲染（💭 面板已有）
        text = "💭 **Reasoning:**\n```\nstep 1\nstep 2\n```\n\nHello world"
        assert strip_reasoning_tags(text) == "Hello world"

    def test_hermes_reasoning_prepend_only(self) -> None:
        text = "💭 **Reasoning:**\n```\nonly reasoning\n```\n\n"
        assert strip_reasoning_tags(text).strip() == ""
