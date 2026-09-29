"""TaskPlanTracker 核心状态模型与 PlanStep 单元测试."""

from hermes_fry_cards.streaming.taskplan import PlanStep, StepStatus, TaskPlanTracker


def test_task_plan_tracker_lifecycle():
    tracker = TaskPlanTracker(min_steps=3, default_collapsed=True)
    assert not tracker.should_display()

    # 注入少于3步 -> 不显示
    tracker.update_plan([
        {"id": "1", "step": "步骤一", "status": "in_progress"},
        {"id": "2", "step": "步骤二", "status": "pending"},
    ])
    assert not tracker.should_display()

    # 注入3步 -> 达到门槛
    tracker.update_plan([
        {"id": "1", "step": "步骤一", "status": "completed"},
        {"id": "2", "step": "步骤二", "status": "in_progress"},
        {"id": "3", "step": "步骤三", "status": "pending"},
    ])
    assert tracker.should_display()
    assert tracker.completed_count == 1
    assert tracker.total_count == 3
    assert not tracker.is_all_completed
    assert tracker.current_active_step == "步骤二"

    # 注脚设置
    tracker.set_active_sub_note("正在执行: pytest tests/")
    assert tracker.latest_sub_note == "正在执行: pytest tests/"

    # 全部完成
    tracker.update_plan([
        {"id": "1", "step": "步骤一", "status": "completed"},
        {"id": "2", "step": "步骤二", "status": "completed"},
        {"id": "3", "step": "步骤三", "status": "completed"},
    ])
    assert tracker.is_all_completed
    assert tracker.completed_count == 3


def test_build_task_plan_panel_elements():
    from hermes_fry_cards.cardkit.builder import build_task_plan_panel

    tracker = TaskPlanTracker(min_steps=3, default_collapsed=True)
    tracker.update_plan([
        {"id": "1", "step": "第一步", "status": "completed"},
        {"id": "2", "step": "第二步", "status": "in_progress"},
        {"id": "3", "step": "第三步", "status": "pending"},
    ])
    tracker.set_active_sub_note("正在执行: curl 127.0.0.1")
    panel = build_task_plan_panel(tracker)
    assert panel is not None
    assert panel["tag"] == "collapsible_panel"
    assert panel["expanded"] is False  # default_collapsed=True -> not expanded
    assert "1/3" in str(panel["header"])
    # 检查注脚是否存在
    body_md = str(panel["elements"])
    assert "正在执行: curl 127.0.0.1" in body_md

    # 测试全部完成时状态
    tracker.update_plan([
        {"id": "1", "step": "第一步", "status": "completed"},
        {"id": "2", "step": "第二步", "status": "completed"},
        {"id": "3", "step": "第三步", "status": "completed"},
    ])
    panel_done = build_task_plan_panel(tracker)
    assert panel_done is not None
    assert panel_done["expanded"] is False  # auto_collapse_on_done=True
    assert "全量达成" in str(panel_done["header"])
    assert "3/3" in str(panel_done["header"])


def test_controller_plan_interception():
    import asyncio
    from hermes_fry_cards.streaming.session import CardSession

    loop = asyncio.new_event_loop()
    try:
        session = CardSession(message_id="msg_test_01", chat_id="chat_01", loop=loop)
        assert session.task_plan is not None

        # 模拟 update_plan 工具调用
        tool_detail = '{"plan": [{"id": "1", "step": "查配置", "status": "completed"}, {"id": "2", "step": "改代码", "status": "in_progress"}, {"id": "3", "step": "跑验证", "status": "pending"}]}'
        session.handle_plan_update(tool_detail)
        assert session.task_plan.should_display()
        assert session.task_plan.completed_count == 1

        # 模拟子工具执行注脚联动
        session.update_tool_sub_note("terminal", "cat /etc/nginx/nginx.conf")
        assert "cat /etc/nginx" in session.task_plan.latest_sub_note
    finally:
        loop.close()


def test_task_plan_config_defaults():
    from hermes_fry_cards.config import load_task_plan_config

    cfg = load_task_plan_config({})
    assert cfg["enabled"] is True
    assert cfg["min_steps"] == 3
    assert cfg["default_collapsed"] is True
    assert cfg["auto_collapse_on_done"] is True
    assert cfg["show_sub_note"] is True

    custom = load_task_plan_config({
        "task_plan": {
            "enabled": False,
            "min_steps": 5,
            "default_collapsed": False,
            "auto_collapse_on_done": False,
            "show_sub_note": False,
        }
    })
    assert custom["enabled"] is False
    assert custom["min_steps"] == 5
    assert custom["default_collapsed"] is False
    assert custom["auto_collapse_on_done"] is False
    assert custom["show_sub_note"] is False



