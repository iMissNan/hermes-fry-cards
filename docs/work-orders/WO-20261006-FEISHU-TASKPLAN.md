# 项目级重构工单：飞书流式卡片 TaskPlanTracker 任务计划正本清源改造

- **工单编号**：`WO-20261006-FEISHU-TASKPLAN`
- **任务分级**：T2（标准工程单 · 核心功能重构与协议加固）
- **负责人**：小兔 (Antigravity Operations Agent)
- **立项时间**：2026-10-06
- **代码仓库**：`/home/linxuan/hermes-fry-cards`
- **当前状态**：`S1 设计完成 -> 进入 S2 施工阶段`

---

## 一、 背景与根因剖析

### 1. 现象与老板痛点
在飞书流式卡片执行复杂任务时，顶部计划卡片被刷成微观工具流水账：
```text
✅ Terminal (336 ms)
✅ Terminal (269 ms)
✅ Terminal (3.7 s)
✅ Aidumem remember (36.3 s)
```
老板完全看不出宏观业务进展到哪一阶段。

### 2. 代码级根因定位
在 `hermes-fry-cards/hermes_fry_cards/streaming/taskplan.py` 中的 `sync_from_tool_use()` 以及 `controller.py` 第 353 行中，代码将底层实际工具调用的名称（`Terminal`、`Aidumem remember`）粗暴映射成任务步骤，强行篡夺了任务计划看板的语义。
Hermes Studio 原生体验中，任务卡是模型的**宏观业务阶段规划**（通过 `ekko_studio_update_plan` 驱动），而微观命令属于底层的 `Tool Activity` 折叠面板。

---

## 二、 重构目标与范围

### 1. 核心目标
1. **正本清源**：彻底剥离将工具流机械伪装成任务计划的 `sync_from_tool_use` 篡位逻辑；
2. **规范对齐**：只消费显式下发的宏观任务计划（`update_plan` / `ekko_studio_update_plan`）；
3. **分层注脚**：大步骤展示宏观里程碑，正在进行的步骤下方动态展示微观动作注脚（如 `└─ 正在执行: ...`）；
4. **CardKit 稳固**：加固动态插入锚点（不硬依赖 `tool_panel`），支持飞书 `_i18n` 规范化标题与安全截断；
5. **单测覆盖**：重构并新增测试用例，确保 100% 通过。

### 2. 文件变更白名单（严格限制）
- `hermes_fry_cards/streaming/taskplan.py`（剥离伪工具流，保留注脚状态）
- `hermes_fry_cards/streaming/segment_helper.py`（动态锚点与 CardKit update 契约）
- `hermes_fry_cards/cardkit/builder.py`（国际化抽取与步骤文本截断）
- `hermes_fry_cards/cardkit/i18n.py`（补充任务卡双语词条）
- `hermes_fry_cards/controller.py`（移除 `sync_from_tool_use` 调用，理顺注脚同步）
- `tests/test_taskplan.py`（更新与补充单测用例）

---

## 三、 验收标准（S4 门禁条目）

1. [ ] **业务语义纯正**：在没有显式调用 `update_plan` 时，卡片绝不再出现 `Terminal (...)` 伪装成的任务卡，卡片清爽无杂音；
2. [ ] **宏观规划 + 微观注脚**：当接收到显式 `update_plan` 且步骤 ≥ 3 时，顶部展示宏观阶段；当前进行中步骤带动态动作小注脚；
3. [ ] **CardKit 锚点容错**：即使卡片未启用 `tool_panel`（`show_tool_use: false`），任务卡也能安全插入卡片顶部，不报 `300305`；
4. [ ] **全量测试通过**：`$HERMES_PYTHON -m pytest tests/test_taskplan.py` 必须全绿无警告。

---

## 四、 回滚锚点
- Git Commit 基线：`04a8ce2 fix(config): 允许默认 profile 安全回落读取 .env 凭据以兼容单 profile 网关`
- 出现异常时可通过 `git checkout .` 瞬时恢复。
