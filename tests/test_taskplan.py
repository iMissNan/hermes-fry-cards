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

