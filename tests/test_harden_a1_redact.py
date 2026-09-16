"""WO-0916-HARDEN-01 A1 核对补缺 — 工具面板脱敏接入面补缺测试.

基线 318cd76 已有 redact_inline_secrets/_redact_paths 等函数（与 aiduPOP 同源），
本文件只钉死本次补缺的两个接入点行为：
1. _sanitize_detail 所有 sanitizer 分支出口统一脱敏（此前仅 command 分支脱敏）；
2. _build_display_block 的 result/error block 内容统一脱敏（覆盖代码块内漏网）。
"""

from __future__ import annotations

from hermes_fry_cards.streaming.tooluse import (
    ToolUseTracker,
    _build_display_block,
    _sanitize_detail,
    redact_inline_secrets,
)


class TestSanitizeDetailUniformRedaction:
    """缺口①：非 command sanitizer 的 detail 出卡前也要脱敏（宁可误杀）."""

    def test_search_detail_redacts_bearer(self) -> None:
        """整改令 R-5（N-2）二审收尾：输入必须真实携带密钥值，断言值来自输入本身。"""
        secret = "sk-" + "test" + "-90ab7cdef"  # 运行时拼接，防管线占位符污染
        detail = "query Authorization: Bearer " + secret
        result = _sanitize_detail(detail, "search")
        assert secret not in result
        assert "[redacted]" in result

    def test_url_detail_redacts_token_param_value(self) -> None:
        result = _sanitize_detail("https://example.com fetch with api_key=abcd1234efgh", "url")
        assert "abcd1234efgh" not in result

    def test_path_detail_redacts_token_assignment(self) -> None:
        result = _sanitize_detail("token=supersecret99 /home/user/file.py", "path")
        assert "supersecret99" not in result

    def test_plain_detail_untouched(self) -> None:
        text = "just a normal detail line"
        assert _sanitize_detail(text, "search") == text

    def test_url_query_string_secrets_redacted(self) -> None:
        """整改令 R-5（M-4）：反向规格改正向——敏感 query 参数值必须打码，良性参数不动。"""
        text = "https://api.example.com/v1?access_token=abc123XYZ456&user=42&page=2"
        result = redact_inline_secrets(text)
        assert "abc123XYZ456" not in result
        assert "user=42" in result and "page=2" in result  # 良性参数零误伤

    def test_url_query_token_and_password(self) -> None:
        token = "tk_" + "live" + "_9f8e7d"  # 运行时拼接，断言值真实进输入
        text = "curl 'https://h.example/x?token=" + token + "&password=hunter99z'"
        result = redact_inline_secrets(text)
        assert token not in result
        assert "hunter99z" not in result

    def test_url_query_benign_value_untouched(self) -> None:
        """?q=secret 的 secret 是值不是键——不脱敏（防误伤搜索词）。"""
        text = "https://example.com/search?q=secret&page=2"
        assert redact_inline_secrets(text) == text

    def test_code_block_inside_output_redacted(self) -> None:
        """缺口②：工具 output 代码块内的密钥也要脱敏（执行证据，宁可误杀）."""
        output = "结果:\n```bash\ncurl -H 'Authorization: Bearer sk-real-abc123' https://api.example.com\n```\n"
        block = _build_display_block(output)
        assert block is not None
        assert "sk-real-abc123" not in block["content"]
        assert "sk-real-abc123" not in block["fenced"]
        assert "[redacted]" in block["fenced"]

    def test_json_block_dict_value_redacted(self) -> None:
        """dict/list 输入经 json.dumps 后，值内嵌的 Bearer 也要脱敏."""
        block = _build_display_block({"note": "use Authorization: Bearer sk-nested-777"})
        assert block is not None
        assert "sk-nested-777" not in block["content"]

    def test_json_colon_pair_api_key_value_redacted(self) -> None:
        """整改令 R-5（M-3）：JSON 冒号形态 "api_key": "***" 的值必须打码。"""
        text = '{"api_key": "AIzaSyD-Xy9zRealKEY01", "model": "gpt-x"}'
        result = redact_inline_secrets(text)
        assert "AIzaSyD-Xy9zRealKEY01" not in result
        assert '"model": "gpt-x"' in result  # 非敏感键零误伤

    def test_json_colon_pair_token_secret_password(self) -> None:
        result = redact_inline_secrets(
            '{"token": "tok_aaa111", "client_secret": "cs_bbb222", "password": "hunter99z", "name": "fry"}'
        )
        for leak in ("tok_aaa111", "cs_bbb222", "hunter99z"):
            assert leak not in result
        assert '"name": "fry"' in result

    def test_json_colon_benign_values_untouched(self) -> None:
        """普通 JSON 键值不命中敏感名 → 零误伤（防脱敏正则乱吃）。"""
        text = '{"name": "value", "count": 42, "timeout_sec": 30}'
        assert redact_inline_secrets(text) == text

    def test_url_query_string_secrets_redacted_via_tooluse(self) -> None:
        """整改令 R-5（M-4）端到端：工具 detail 里的 URL query 密钥也不出卡。"""
        result = _sanitize_detail(
            "GET https://api.example.com/v1?access_token=abc123XYZ456&user=42", "url"
        )
        assert "abc123XYZ456" not in result
        assert "user=42" in result

    def test_normal_json_block_untouched(self) -> None:
        """普通 JSON 键值（冒号格式）不受脱敏正则影响，零误伤."""
        block = _build_display_block({"name": "value", "count": 42})
        assert block is not None
        assert '"name": "value"' in block["content"]

    def test_error_block_redacted(self) -> None:
        block = _build_display_block("failed: token=leaky-secret-777", "text")
        assert block is not None
        assert "leaky-secret-777" not in block["content"]

    def test_tracker_display_error_field_not_leaked_via_block(self) -> None:
        """端到端：tracker error → display step 的 error_block 必须已脱敏."""
        tracker = ToolUseTracker()
        tracker.record_start("custom_tool", "run")
        tracker.record_end("custom_tool", error="boom: password=hunter2-xyz")
        steps = tracker.build_display_steps()
        assert steps[0]["error_block"] is not None
        assert "hunter2-xyz" not in steps[0]["error_block"]["content"]
