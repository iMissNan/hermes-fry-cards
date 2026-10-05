"""hermes-fry-cards — 飞书流式卡片插件."""

# 与 pyproject.toml 的 version 保持同步（0.3.2/0.3.3 发版时曾漏同步，勿再漂移）
__version__ = "0.4.7"


def register(ctx) -> None:
    """插件系统注册：接 post_api_request 钩子，记录真实应答模型（卡片头部穿透显示）."""
    try:
        from .model_tracker import record as _record

        def _on_post_api_request(**kwargs) -> None:
            try:
                actual = kwargs.get("response_model")
                if actual:
                    _record(
                        str(kwargs.get("model") or ""),
                        str(actual),
                        str(kwargs.get("session_id") or ""),
                    )
            except Exception:
                pass

        ctx.register_hook("post_api_request", _on_post_api_request)
    except Exception:
        pass
