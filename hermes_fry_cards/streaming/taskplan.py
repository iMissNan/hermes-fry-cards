"""任务计划状态机与数据模型 (TaskPlanTracker).

对标 Studio update_plan 原生体验，支持飞书流式卡片顶部的多步骤任务进度跟踪。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class StepStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


@dataclass
class PlanStep:
    id: str
    step: str
    status: StepStatus
    sub_note: str = ""


class TaskPlanTracker:
    """任务计划跟踪器."""

    def __init__(
        self,
        min_steps: int = 3,
        default_collapsed: bool = True,
        auto_collapse_on_done: bool = True,
        show_sub_note: bool = True,
    ) -> None:
        self.min_steps = min_steps
        self.default_collapsed = default_collapsed
        self.auto_collapse_on_done = auto_collapse_on_done
        self.show_sub_note = show_sub_note
        self.steps: list[PlanStep] = []
        self.explanation: str = ""
        self.latest_sub_note: str = ""
        self.dirty: bool = False
        self.created: bool = False
        self.is_auto_synthesized: bool = False

    def update_plan(self, raw_steps: list[dict[str, Any]], explanation: str = "") -> bool:
        if not isinstance(raw_steps, list):
            return False
        parsed: list[PlanStep] = []
        for s in raw_steps:
            if not isinstance(s, dict):
                continue
            sid = str(s.get("id", ""))
            title = str(s.get("step", ""))
            status_str = str(s.get("status", "pending")).lower()
            try:
                st = StepStatus(status_str)
            except ValueError:
                st = StepStatus.PENDING
            parsed.append(PlanStep(id=sid, step=title, status=st))
        self.steps = parsed
        self.explanation = explanation
        self.is_auto_synthesized = False
        self.dirty = True
        return True

    def set_active_sub_note(self, note: str) -> None:
        if self.latest_sub_note != note:
            self.latest_sub_note = note
            self.dirty = True


    def sync_from_tool_use(self, display_steps: Any) -> bool:
        """从底层实际工具调用 (ToolUseTracker) 自动合成/聚合成任务计划看板.

        当且仅当未显式收到 update_plan 规划时生效，真正做到像「工具执行中」一样天生自带！
        """
        # 如果已经有显式的计划（模型自己调了 update_plan），优先尊重显式计划
        if not self.is_auto_synthesized and len(self.steps) > 0:
            return False

        if not display_steps or len(display_steps) < self.min_steps:
            # 动作尚少于门槛 (默认3步)，保持静默
            if self.is_auto_synthesized:
                self.steps = []
                self.dirty = True
            return False

        self.is_auto_synthesized = True
        new_steps: list[PlanStep] = []
        for idx, s in enumerate(display_steps, 1):
            title = s.get("title", s.get("name", f"步骤 {idx}"))
            status_val = s.get("status", "running")
            # 格式化状态
            if status_val in ("success", "completed"):
                st = StepStatus.COMPLETED
            elif status_val in ("running", "started"):
                st = StepStatus.IN_PROGRESS
            else:
                st = StepStatus.PENDING
            new_steps.append(PlanStep(id=str(idx), step=title, status=st))

        self.steps = new_steps
        self.dirty = True
        return True

    def should_display(self) -> bool:
        return len(self.steps) >= self.min_steps

    @property
    def total_count(self) -> int:
        return len(self.steps)

    @property
    def completed_count(self) -> int:
        return sum(1 for s in self.steps if s.status == StepStatus.COMPLETED)

    @property
    def is_all_completed(self) -> bool:
        return self.total_count > 0 and self.completed_count == self.total_count

    @property
    def current_active_step(self) -> str:
        for s in self.steps:
            if s.status == StepStatus.IN_PROGRESS:
                return s.step
        return ""
