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

        # 模拟 todo_list 工具调用 (支持 tool_call 嵌套)
        todo_detail = '{"calls": [{"name": "todo_list", "arguments": {"todos": [{"id": "10", "content": "第一阶段", "status": "completed"}, {"id": "20", "content": "第二阶段", "status": "in_progress"}, {"id": "30", "content": "第三阶段", "status": "pending"}]}}]}'
        session.handle_plan_update(todo_detail)
        assert session.task_plan.should_display()
        assert session.task_plan.steps[0].step == "第一阶段"
        assert session.task_plan.current_active_step == "第二阶段"

        # 模拟流式 action 构建
        from hermes_fry_cards.streaming.segment_helper import build_task_plan_update_action
        from hermes_fry_cards.cardkit.builder import TASK_PLAN_ELEMENT_ID
        plan_act = build_task_plan_update_action(element_id=TASK_PLAN_ELEMENT_ID, tracker=session.task_plan)
        assert plan_act is not None
        assert plan_act["action"] == "partial_update_element"
        assert plan_act["params"]["element_id"] == TASK_PLAN_ELEMENT_ID

        # 模拟子工具执行注脚联动
        session.update_tool_sub_note("terminal", "cat /etc/nginx/nginx.conf")
        assert "cat /etc/nginx" in session.task_plan.latest_sub_note
    finally:
        loop.close()


def test_task_plan_config_defaults():
    from hermes_fry_cards.config import load_task_plan_config

    cfg = load_task_plan_config({})
    assert cfg["enabled"] is False
    assert cfg["min_steps"] == 3
    assert cfg["default_collapsed"] is True
    assert cfg["auto_collapse_on_done"] is True
    assert cfg["show_sub_note"] is True

    custom = load_task_plan_config({
        "task_plan": {
            "enabled": True,
            "min_steps": 5,
            "default_collapsed": False,
            "auto_collapse_on_done": False,
            "show_sub_note": False,
        }
    })
    assert custom["enabled"] is True
    assert custom["min_steps"] == 5
    assert custom["default_collapsed"] is False
    assert custom["auto_collapse_on_done"] is False
    assert custom["show_sub_note"] is False


def test_card_structure_with_task_plan():
    """验证方案 A 架构收拢：飞书流式卡片保持纯净轻量，首位为正文或工具面板，不强插任务计划面板."""
    from hermes_fry_cards.cardkit.builder import (
        TASK_PLAN_ELEMENT_ID,
        build_complete_card,
        build_streaming_card_v2,
    )
    from hermes_fry_cards.streaming.segments import Segment, SegmentType

    tracker = TaskPlanTracker(min_steps=3, default_collapsed=True)
    tracker.update_plan([
        {"id": "1", "step": "步骤一", "status": "completed"},
        {"id": "2", "step": "步骤二", "status": "in_progress"},
        {"id": "3", "step": "步骤三", "status": "pending"},
    ])

    # 流式卡片：保持轻量纯净
    stream_card = build_streaming_card_v2(task_plan=tracker)
    elements = stream_card["body"]["elements"]
    assert len(elements) > 0
    # 方案 A：首位不再被 task_plan_panel 挤占
    assert all(e.get("element_id") != TASK_PLAN_ELEMENT_ID for e in elements)

    # 完成态卡片：同样保持纯净
    seg = Segment(SegmentType.ANSWER, "answer_0")
    seg.text = "任务执行完毕！"
    complete_card = build_complete_card(
        segments=[seg],
        all_tool_steps=[],
        task_plan=tracker,
    )
    c_elements = complete_card["body"]["elements"]
    assert len(c_elements) > 0
    assert all(e.get("element_id") != TASK_PLAN_ELEMENT_ID for e in c_elements)


def test_task_plan_no_auto_synthesis_from_tools():
    """验证工具调用不会篡位伪装成任务计划：只有显式调用 update_plan 才会展示阶段规划."""
    tracker = TaskPlanTracker(min_steps=3, default_collapsed=True)
    assert not tracker.should_display()

    # 模拟显式调用 update_plan 规划
    explicit_plan = [
        {"id": "A", "step": "排查根因", "status": "completed"},
        {"id": "B", "step": "修复代码", "status": "in_progress"},
        {"id": "C", "step": "测试验收", "status": "pending"},
    ]
    tracker.update_plan(explicit_plan)
    assert tracker.should_display()
    assert tracker.total_count == 3
    assert tracker.completed_count == 1
    assert tracker.current_active_step == "修复代码"

    # 验证动态动作小注脚
    tracker.set_active_sub_note("terminal: pytest tests/")
    assert tracker.latest_sub_note == "terminal: pytest tests/"

    # 验证 CardKit 生成的面板组件
    from hermes_fry_cards.cardkit.builder import build_task_plan_panel
    panel = build_task_plan_panel(tracker)
    assert panel is not None
    assert panel["tag"] == "collapsible_panel"
    assert "1/3" in str(panel["header"])
    assert "pytest tests/" in panel["elements"][0]["content"]





