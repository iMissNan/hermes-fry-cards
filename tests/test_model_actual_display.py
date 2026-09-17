"""契约：飞书卡片头部显示「组合名/真实应答模型」（老板 2026-09-17 要求穿透一层）。

- 插件注册的 post_api_request 钩子把 response_model 记进 model_tracker；
- 卡片收尾时 resolve_actual() 取最后一口应答的真实模型（串台/过期保守不显示）；
- builder 渲染 _display_model_pair 为「my-com1/GLM-5.3」；无穿透信息时行为与旧版一致。
"""

import pytest

from hermes_fry_cards import model_tracker
from hermes_fry_cards.cardkit.builder import _display_model_pair, _pretty_actual_model


@pytest.fixture(autouse=True)
def _reset_tracker():
    model_tracker._latest = {}
    yield
    model_tracker._latest = {}


@pytest.fixture(autouse=True)
def _no_alias(monkeypatch):
    """默认关掉别名文件（宿主 ~/.hermes/model_aliases.json 是真实环境，测试要确定性）。"""
    from hermes_fry_cards.config import Config

    monkeypatch.setattr(Config, "model_aliases", lambda self: {})


def test_record_and_resolve_roundtrip():
    model_tracker.record("my-com1", "z-ai/glm-5.3", "sess-1")
    assert model_tracker.resolve_actual("my-com1") == "z-ai/glm-5.3"


def test_resolve_rejects_requested_mismatch():
    model_tracker.record("my-com1", "z-ai/glm-5.3")
    assert model_tracker.resolve_actual("yangmao") == ""


def test_resolve_rejects_empty_actual():
    model_tracker.record("my-com1", "")
    assert model_tracker.resolve_actual("my-com1") == ""


def test_resolve_rejects_stale_record():
    model_tracker.record("my-com1", "z-ai/glm-5.3")
    model_tracker._latest["ts"] = model_tracker._latest["ts"] - model_tracker._MAX_AGE_S - 1
    assert model_tracker.resolve_actual("my-com1") == ""


def test_pair_display_combines():
    footer = {"model": "my-com1", "model_actual": "z-ai/glm-5.3"}
    assert _display_model_pair(footer) == "my-com1/glm-5.3"


def test_pair_display_no_actual_unchanged():
    assert _display_model_pair({"model": "my-com1"}) == "my-com1"
    assert _display_model_pair({}) == ""
    assert _display_model_pair(None) == ""


def test_pair_display_dedupes_identical():
    footer = {"model": "Antigravity", "model_actual": "Antigravity"}
    assert _display_model_pair(footer) == "Antigravity"


def test_pair_display_alias_prettifies_actual(monkeypatch):
    from hermes_fry_cards.config import Config

    monkeypatch.setattr(Config, "model_aliases", lambda self: {"glm-5.3": "GLM-5.3"})
    footer = {"model": "my-com1", "model_actual": "z-ai/glm-5.3"}
    assert _display_model_pair(footer) == "my-com1/GLM-5.3"


def test_pretty_actual_takes_last_path_segment():
    assert _pretty_actual_model("z-ai/glm-5.3") == "glm-5.3"
    assert _pretty_actual_model("mimo-x-flash-preview") == "mimo-x-flash-preview"
