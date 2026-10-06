# 施工验收回执：飞书流式卡片 TaskPlanTracker 任务计划正本清源改造

- **工单编号**：`WO-20261006-FEISHU-TASKPLAN`
- **对应阶段**：S4 验收与交付
- **执行时间**：2026-10-06
- **责任人**：小兔 (Antigravity Operations Agent)

---

## 一、 证据五件套

### 1. 指纹/变更对拍
本次改造严格限定在白名单内的 6 个核心文件，无任何越权改动：
- `hermes_fry_cards/streaming/taskplan.py`：彻底移除 `sync_from_tool_use`，终结工具流机械伪装成任务计划；
- `hermes_fry_cards/controller.py`：移除对 `sync_from_tool_use` 的调度调用，保持工具流与任务规划正交隔离；
- `hermes_fry_cards/cardkit/i18n.py`：新增任务计划中英双语词条规范 `task_plan_title` 与 `task_plan_all_done`；
- `hermes_fry_cards/cardkit/builder.py`：使用 `_i18n` 规范化标题呈现，杜绝硬编码；
- `hermes_fry_cards/streaming/segment_helper.py`：增加动态锚点 `target_element_id` 参数与安全兜底；
- `hermes_fry_cards/streaming/controller.py`：当未启用 `tool_panel` 时动态以 `LOADING_ELEMENT_ID` 为顶部插入锚点，消除报错；
- `tests/test_taskplan.py`：更新单测用例，验证“仅显式调用生效”及“动作小注脚正常”。

### 2. 原始终端输出（真实测试运行）
```text
$ /home/linxuan/.hermes/hermes-agent/venv/bin/python3 -m pytest /home/linxuan/hermes-fry-cards/tests/test_taskplan.py -v
============================= test session starts ==============================
platform linux -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/linxuan/hermes-fry-cards
configfile: pyproject.toml
collected 6 items

../../hermes-fry-cards/tests/test_taskplan.py::test_task_plan_tracker_lifecycle PASSED [ 16%]
../../hermes-fry-cards/tests/test_taskplan.py::test_build_task_plan_panel_elements PASSED [ 33%]
../../hermes-fry-cards/tests/test_taskplan.py::test_controller_plan_interception PASSED [ 50%]
../../hermes-fry-cards/tests/test_taskplan.py::test_task_plan_config_defaults PASSED [ 66%]
../../hermes-fry-cards/tests/test_taskplan.py::test_card_structure_with_task_plan PASSED [ 83%]
../../hermes-fry-cards/tests/test_taskplan.py::test_task_plan_no_auto_synthesis_from_tools PASSED [100%]

============================== 6 passed in 8.08s ===============================
```

### 3. 反向验证（红→绿演练）
- **改造前**：底层调用 `Terminal (1.2 s)`、`Patch (0.3 s)` 时，会通过 `sync_from_tool_use` 强行升格为任务计划步骤，导致顶部出现大串工具流水账（测试用例曾断言 `tracker.is_auto_synthesized is True`）；
- **改造后**：测试用例 `test_task_plan_no_auto_synthesis_from_tools` 证实，在未收到模型显式 `update_plan` 规划前，`tracker.should_display()` 严格保持 `False`；一旦收到显式规划，立即正确呈现阶段目标与动态动作注脚。

### 4. 备份与回滚锚点
- 基线 Commit：`04a8ce2 fix(config): 允许默认 profile 安全回落读取 .env 凭据以兼容单 profile 网关`
- 随时可通过 `git checkout .` 瞬时恢复。

### 5. 沙盒零污染自查
- 无临时调试文件残留在仓库目录中。
