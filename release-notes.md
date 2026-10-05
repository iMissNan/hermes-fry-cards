## 🍟 hermes-fry-cards v0.4.7

> Studio 图标全面 **SVG 化**：字段调序箭头（↑↓）、主题切换（月亮/太阳）、GitHub 顶栏图标
> 全部替换为内联 SVG，随主题色渲染，暗色下不再出现彩色 emoji 割裂感。纯前端改动。

### 🎨 视觉

- 字段列表 ↑↓ 调序按钮 → SVG chevron（`stroke: currentColor`，双主题自动适配）
- 主题切换按钮月亮 / 太阳 → SVG（`applyTheme` 动态切换内联 SVG）
- GitHub 顶栏 ⭐ → octocat SVG；操作按钮补 `aria-label` 无障碍标签

### ✅ 验证

浏览器亮 / 暗截图核对 SVG 渲染与箭头功能（调序 / 主题切换 / 图标随主题变色）。

### 📦 升级

**PyPI（推荐）**：

```bash
HERMES_PYTHON=~/.hermes/hermes-agent/venv/bin/python3
$HERMES_PYTHON -m pip install -U hermes-fry-cards
$HERMES_PYTHON -m hermes_fry_cards uninstall
$HERMES_PYTHON -m hermes_fry_cards install
hermes gateway restart
```

**源码方式**：

```bash
cd ~/projects/hermes-fry-cards && git pull
HERMES_PYTHON=~/.hermes/hermes-agent/venv/bin/python3
$HERMES_PYTHON -m pip install -U .
$HERMES_PYTHON -m hermes_fry_cards uninstall
$HERMES_PYTHON -m hermes_fry_cards install
hermes gateway restart
```

> ✅ 纯前端改动：**无需重跑 `uninstall` + `install`，无需重启网关**，更新包后浏览器强刷（Ctrl+F5）Studio 页面即可。

---

完整明细见 [CHANGELOG.md](https://github.com/techysy/hermes-fry-cards/blob/main/CHANGELOG.md)。

**Full Changelog**: [v0.4.6...v0.4.7](https://github.com/techysy/hermes-fry-cards/compare/v0.4.6...v0.4.7)

## 🍟 hermes-fry-cards v0.4.6

> footer 与统一面板的**字段 chips 支持拖动排序**：按住拖到目标位置松手即可，保存按拖拽后的顺序写入配置，重新打开 Studio 按已保存顺序回填。纯前端改动。

### ✨ 新增

- **字段 chips 拖动排序**（footer + 统一面板两组）
  - 原生 HTML5 Drag & Drop，无任何依赖；拖动中半透明占位，松手即落位
  - 保存按容器内实际顺序写入 `streaming.footer.fields` / `display.platforms.feishu.panel_fields`（替代原先固定字段表排序——此前只能勾选，顺序不可调）
  - 重新打开 Studio 按已保存顺序回填重排 chips，未选字段保持相对顺序跟在后面
  - 多行 fields 配置下 chips 仍整体禁用（不可点也不可拖）

### ✅ 验证

浏览器端到端：拖拽 DOM 重排 → 保存 → config.yaml 字段顺序断言一致 → 刷新回填重排，footer 与面板两组全通过。

### 📦 升级

**PyPI（推荐）**：

```bash
HERMES_PYTHON=~/.hermes/hermes-agent/venv/bin/python3
$HERMES_PYTHON -m pip install -U hermes-fry-cards
$HERMES_PYTHON -m hermes_fry_cards uninstall
$HERMES_PYTHON -m hermes_fry_cards install
hermes gateway restart
```

**源码方式**：

```bash
cd ~/projects/hermes-fry-cards && git pull
HERMES_PYTHON=~/.hermes/hermes-agent/venv/bin/python3
$HERMES_PYTHON -m pip install -U .
$HERMES_PYTHON -m hermes_fry_cards uninstall
$HERMES_PYTHON -m hermes_fry_cards install
hermes gateway restart
```

> ✅ 纯前端改动：**无需重跑 `uninstall` + `install`，无需重启网关**，更新包后浏览器强刷（Ctrl+F5）Studio 页面即可。

---

完整明细见 [CHANGELOG.md](https://github.com/techysy/hermes-fry-cards/blob/main/CHANGELOG.md)。

**Full Changelog**: [v0.4.5...v0.4.6](https://github.com/techysy/hermes-fry-cards/compare/v0.4.5...v0.4.6)

## 🍟 hermes-fry-cards v0.4.5

> 0.4.4 的纯黑主操作色对比过冲、观感生硬——本版柔化为**石墨蓝灰**并给激活元素加轻阴影，保留 CreditDaddy 的深色激活语言；同版**包首发 PyPI**，`pip install hermes-fry-cards` 即可安装。纯 CSS 变量调整，无功能变化。

### ✨ 新增

- **包首发 PyPI**：[pypi.org/project/hermes-fry-cards](https://pypi.org/project/hermes-fry-cards) — `pip install hermes-fry-cards` 直接安装（升级加 `-U`）；装完仍需 `verify` → `install` 注入并重启网关

### 🎨 视觉

- **主色柔化**：`--ink` 纯黑 `#1b1c1f` → 石墨蓝灰 `#39404a`（暗色反白 `#f2f3f4` → 柔白 `#e7e8ea`），降低与浅灰背景的对比过冲
- **轻阴影**：激活 tab / 选中 chip / 主按钮增加同色系轻阴影（`--ink-soft`），视觉上融入卡片而非硬贴
- checkbox、toast、hover 全部随 CSS 变量自动过渡

### ✅ 验证

浏览器亮 / 暗双主题截图逐屏核对；生产部署后以全新会话核验服务端真实返回（`fry_version` / served CSS / 双服务 active）。

### 📦 升级

**PyPI（本版起上架，推荐）**：

```bash
HERMES_PYTHON=~/.hermes/hermes-agent/venv/bin/python3
$HERMES_PYTHON -m pip install -U hermes-fry-cards
$HERMES_PYTHON -m hermes_fry_cards uninstall
$HERMES_PYTHON -m hermes_fry_cards install
hermes gateway restart
```

**源码方式**：

```bash
cd ~/projects/hermes-fry-cards && git pull
HERMES_PYTHON=~/.hermes/hermes-agent/venv/bin/python3
$HERMES_PYTHON -m pip install -U .
$HERMES_PYTHON -m hermes_fry_cards uninstall
$HERMES_PYTHON -m hermes_fry_cards install
hermes gateway restart
```

> ✅ 纯 CSS 变量调整：**无需重跑 `uninstall` + `install`，无需重启网关**，更新包后浏览器强刷（Ctrl+F5）Studio 页面即可。

---

完整明细见 [CHANGELOG.md](https://github.com/techysy/hermes-fry-cards/blob/main/CHANGELOG.md)。

**Full Changelog**: [v0.4.4...v0.4.5](https://github.com/techysy/hermes-fry-cards/compare/v0.4.4...v0.4.5)

## 🍟 hermes-fry-cards v0.4.4

> Studio 前端整体换装，对齐 [CreditDaddy](https://github.com/techysy/CreditDaddy) 的设计语言：**黑白主色 + 胶囊导航 + 卡片化布局**，并新增**亮 / 暗双主题**（右上角 🌙 一键切换，自动记忆）。纯前端改动，配置键与功能完全不变。

### 🎨 视觉

- **顶栏重构**：🍟 logo + 大标题 + `v版本 · 配置路径` 副行；右侧 GitHub 与主题切换图标按钮
- **胶囊式导航条**：配置 / 预览 / 状态改为独立白底圆角容器 + 激活黑胶囊，与 CreditDaddy 的产品 tab 条同构
- **卡片化布局**：设置分组去边框，改为大圆角 + 浅阴影卡片；顶部警告条同步；chips 选中态与主按钮同色系
- **亮 / 暗双主题**
  - `data-theme` 属性驱动全量 CSS 变量（表单、模型别名编辑器、状态卡、toast 全套适配）
  - localStorage 记忆 + `<head>` 内联预设，刷新不闪白
  - 暗色下主操作色自动反白

### ✅ 验证

浏览器亮 / 暗双主题与状态页截图逐屏核对；ruff / mypy 与基线持平。

### 📦 升级

```bash
cd ~/projects/hermes-fry-cards && git pull
HERMES_PYTHON=~/.hermes/hermes-agent/venv/bin/python3
$HERMES_PYTHON -m pip install -U .
```

> ✅ 纯前端改动：**无需重跑 `uninstall` + `install`，无需重启网关**，更新包后浏览器强刷（Ctrl+F5）Studio 页面即可。

---

完整明细见 [CHANGELOG.md](https://github.com/techysy/hermes-fry-cards/blob/main/CHANGELOG.md)。

**Full Changelog**: [v0.4.3...v0.4.4](https://github.com/techysy/hermes-fry-cards/compare/v0.4.3...v0.4.4)

## 🍟 hermes-fry-cards v0.4.3

> 本版修复 0.4.2 引入的 Studio「面板 header 字段」chips **点击无反应**（漏绑 click 事件）。纯前端修复，更新包后强刷 Studio 页面即可。

### 🐛 修复

- **面板字段 chips 点击无反应**
  - 症状：0.4.2 新增的统一面板字段选择区点击 chip 无法切换选中态（footer 字段区正常）
  - 根因：新增区块时漏绑 click 事件监听（footer 区的绑定没有同步复制到面板区）
  - 修法：`#f-panel-fields .chip` 补齐 click 绑定；保存链路不变（`PANEL_FIELD_ORDER` 排序写入 `display.platforms.feishu.panel_fields`）

### ✅ 验证

浏览器实测：9 个 chips 渲染、`fillForm` 默认布局回填、点击切换与保存链路全部通过；CardKit / 配置 / Studio 测试套件 **336 passed**。

### 📦 升级

```bash
cd ~/projects/hermes-fry-cards && git pull
HERMES_PYTHON=~/.hermes/hermes-agent/venv/bin/python3
$HERMES_PYTHON -m pip install -U .
```

> ✅ 纯前端修复：**无需重跑 `uninstall` + `install`，无需重启网关**，更新包后浏览器强刷（Ctrl+F5）Studio 页面即可。

---

完整明细见 [CHANGELOG.md](https://github.com/techysy/hermes-fry-cards/blob/main/CHANGELOG.md)。

**Full Changelog**: [v0.4.2...v0.4.3](https://github.com/techysy/hermes-fry-cards/compare/v0.4.2...v0.4.3)

## 🍟 hermes-fry-cards v0.4.2

> 完成卡片对齐主流编程客户端的统计展示：footer 新增 **速度（tok/s）** 与 **缓存命中率**（口径与 Hermes CLI 状态栏一致），统一面板 header 字段化并与 footer **共用字段池**，两处元数据栏均可在 Studio 自由勾选组合。

### ✨ 新增

- **footer `speed` / `cache` 字段**
  - 速度 = 滚动近 10 次 API 调用 `sum(output) / sum(latency)` 纯生成吞吐（剔除工具执行时间，同 Hermes 状态栏 "true throughput"）
  - 命中率 = `cache_read / prompt_tokens`（prompt 已含缓存，同 `turn_usage.py` 归一化口径）；零读取时隐藏（无数据 ≠ 0%）
  - `patch.collect_stream_stats` 从 gateway 活跃 agent（`_running_agents` → `_agent_cache`）best-effort 采集，任一数据不可得即省略
  - 默认 footer 布局变为 `[status, elapsed, speed, cache, context, model]`
- **统一面板 header 字段化，与 footer 共用字段池**
  - 新增 `display.platforms.feishu.panel_fields`（有序一维列表，默认 `[model, reasoning, tools, context, elapsed]` 与历史布局逐字一致，老用户无感）
  - 面板专属字段 `reasoning`（💭 推理轮数）/ `tools`（🔧 工具步数）零计数自动隐藏；共享字段经 footer 渲染器回落；面板标题补 i18n（`Cache hit {}%` / `缓存命中 {}%`）
- **Studio 字段自由组合** — footer 与统一面板各一组 chip 开关，勾选即组合、保存排序；预览（真实 builder）样例带 `208 tok/s` / `缓存命中 54%`

### 🐛 修复

- **Studio footer 字段白名单缺 `speed`/`cache`** — GUI 勾选新字段保存会被 400 拒绝；`_FOOTER_FIELDS` 校验白名单补齐（含测试回归）

### ✅ 验证

全量 **766 passed**（新增面板 header 组合、config `panel_fields` 优先级/容错、Studio 校验三组用例）；ruff / mypy 与基线持平；端到端验证注入钩子在真实 gateway 作用域下的 stats 流转与 agent 缺失时优雅降级。

### 📦 升级

```bash
cd ~/projects/hermes-fry-cards && git pull
HERMES_PYTHON=~/.hermes/hermes-agent/venv/bin/python3
$HERMES_PYTHON -m pip install -U .
$HERMES_PYTHON -m hermes_fry_cards uninstall
$HERMES_PYTHON -m hermes_fry_cards install
hermes gateway restart
```

> ⚠️ 本版变更完成钩子 / 排队 follow-up 钩子注入模板（新增 stats 采集），**必须重跑 `uninstall` + `install`**；旧模板不传新键，controller 侧向后兼容（字段自动隐藏）。

---

完整明细见 [CHANGELOG.md](https://github.com/techysy/hermes-fry-cards/blob/main/CHANGELOG.md)。

**Full Changelog**: [v0.4.1...v0.4.2](https://github.com/techysy/hermes-fry-cards/compare/v0.4.1...v0.4.2)

## 🍟 hermes-fry-cards v0.4.1

> 本版让 **Studio 支持开机自启与异常保活**（systemd 服务模板）并**默认绑 `0.0.0.0`**（局域网直达）；修好 **完成态卡片丢失最终答案**、**cron 投递 230001**、**clarify 拖爆插件加载预算** 三个生产问题，新增 **完成通知**（[#16](https://github.com/techysy/hermes-fry-cards/issues/16)）。

### ✨ 新增

- **Studio systemd 用户服务模板**（`systemd/hermes-fry-cards-studio.service`）
  - 开机 / 登录后自动启动，`Restart=on-failure` + 3 秒退避异常自动拉起，日志进 `journalctl`
  - 以 Hermes venv Python `--no-browser` 常驻 `0.0.0.0:8765`
- **完成通知**（[#16](https://github.com/techysy/hermes-fry-cards/issues/16)）
  - `streaming.completion_notice` / `completion_notice_text`（默认关）：卡片收尾后以回复形式发送「回答结束 · 耗时」短通知（CardKit 更新不触发飞书提醒的兜底）
  - 通知会回复在卡片消息下，仅在卡片成功收尾后发送；错误会附带「出错」
- Studio 正文大字号 `heading` 档（[#16](https://github.com/techysy/hermes-fry-cards/issues/16) 部分）

### 🌐 变更

- **Studio 默认监听 `0.0.0.0:8765`**（原 `127.0.0.1`）— `_cmd_studio` / `run_studio_server` / systemd 模板三处同步；本机仍打印/打开 `http://127.0.0.1:8765`（新增 `_display_host` 回落通配地址）
- **Host 门白名单可配置** `studio.allowed_hosts`（附加网段前缀或完整主机，默认仅 loopback）— 取代硬编码网段，非白名单来源照旧 403（防 DNS rebinding）

### 🐛 修复

- **完成态卡片丢失最终答案**（[#13](https://github.com/techysy/hermes-fry-cards/issues/13)）
  - 症状：多工具回合中工具间旁白形成 ANSWER 段后，完成态注入被旧 guard 整体跳过
  - 修法：完成态答案追加为新 ANSWER 段（保住交错时间线），`endswith` 去重 + 完成重试防重放
- **cron 投递 230001 invalid receive_id**（[#14](https://github.com/techysy/hermes-fry-cards/issues/14)）
  - 根因：Hermes 0.21.0 起部分调度布局的 delivery 是 dict，旧钩子仅走 `getattr` 取不到 `chat_id`
  - 修法：dict/attr 双路径 + `delivery → locals → target` 三级优先，跨调度布局解析投递身份
- **clarify toast 导入拖爆 adapter 10s 加载预算**（[#15](https://github.com/techysy/hermes-fry-cards/issues/15)）
  - 根因：`apply_patch` 在 adapter 导入期执行，toast 类的 lark_oapi 导入等效顶层导入（冷进程 9–16s）
  - 修法：首次回调需要时惰性加载（哨兵缓存，旧 SDK 缺失静默降级），adapter 导入不再触碰 SDK

### ✅ 验证

全量 pytest 回归通过（含 #13 / #14 / #15 的复现与回归用例，`TestWildcardBindDefaults` 守护三处默认绑定）。

### 📦 升级

```bash
cd ~/projects/hermes-fry-cards && git pull
HERMES_PYTHON=~/.hermes/hermes-agent/venv/bin/python3
$HERMES_PYTHON -m pip install -U .
$HERMES_PYTHON -m hermes_fry_cards uninstall
$HERMES_PYTHON -m hermes_fry_cards install
hermes gateway restart
```

> ⚠️ 本版变更 cron / 完成钩子注入模板，**必须重跑 `uninstall` + `install`**。
> Studio 可写 `config.yaml` 与飞书凭据——别做端口转发/公网暴露；只想本机用就 `--host 127.0.0.1`。

---

完整明细见 [CHANGELOG.md](https://github.com/techysy/hermes-fry-cards/blob/main/CHANGELOG.md)。

**Full Changelog**: [v0.4.0...v0.4.1](https://github.com/techysy/hermes-fry-cards/compare/v0.4.0...v0.4.1)

## 🍟 hermes-fry-cards v0.4.0

> 本版是**算法与架构大改版**：新增 **Markdown 防爆引擎**、**Studio 可视化配置工作坊** 与 **模型别名时段人设**，完成态卡片按真实工作流交错渲染（[#10](https://github.com/techysy/hermes-fry-cards/pull/10)）。**配置 schema 向后兼容**——升级无需修改任何现有配置。

### ✨ 新增

- **Markdown 防爆引擎**（借鉴 [aiduPOP](https://github.com/monkey2jack/aiduPOP) 贝氏降级引擎）
  - **无损表格压缩**：超限表格（>5）压缩为「Table N · Row M」字段列表，内容完整保留；fence 感知扫描，inline code 竖线与未闭合代码围栏均正确处理，引擎异常自动回退旧代码块方案
  - **字节级内容预算 `clamp_utf8`**（18KB ≈ 6000 汉字）：流式渐进截断 + 完成态首 60% / 尾 40% 双保（结论不丢），覆盖完成态 / cron / background 卡片与流式 answer flush，杜绝 ~30KB 卡片 JSON 溢出断屏
- **Studio 可视化配置工作坊**（`python -m hermes_fry_cards studio`，借鉴 aiduPOP studio）
  - 三页签：**配置**（白名单键表单，按流式卡片 / 状态栏 / 统一面板 / 模型别名 / 🛡️ 群聊安全边界分组）/ **预览**（服务端调**真实 builder** 渲染，与线上卡片同一代码路径，4 场景 × 流式·完成·出错态）/ **状态**（hook 注入 markers、三目标 verify 兼容性、凭据、一键重启网关）
  - 写回安全五件套：严格校验 400 / 解析失败拒写 409（保护凭证）/ 写前备份轮转 20 份 / 白名单深合并（手写键存活）/ tmp+fsync+rename 原子落盘
  - 安全面：仅 loopback、Host 门防 DNS rebinding、无 CORS、body ≤1MB、`nosniff`
- **模型别名时段人设**（参考 [claw-fry-cards](https://github.com/techysy/claw-fry-cards)，格式逐字兼容，同一份 JSON 两边通用）
  - `model_aliases.json` 值支持时段对象：按**北京时间（固定 UTC+8）** HH:MM + 星期自动切换显示名（DeepSeek 峰谷：峰段梁文锋⚡️ / 谷段梁文谷⚡️），跨午夜 / 起止相等=全天 / 首中即返
  - 总开关 `display.model_aliases_enabled`（默认开，热更新）；Studio 内可视化编辑（星期芯片 + 工作日/周末快捷选择）
- **内容层文案双语** `streaming.content_lang`（zh/en）——正文内嵌提示语（表格转换引导、截断提示）按部署偏好定死
- **瞬态错误码扩充**：频控 `230020`、开放平台频率限制 `99991400` 纳入短退避重试

### 🎨 优化

- **统一面板按真实工作流交错渲染**（[#10](https://github.com/techysy/hermes-fry-cards/pull/10)，感谢 @JasonXX89）— 从「所有思考集中在前、所有工具堆在末尾」改为 `💭 思考1 → 🔧 工具组1 → 💭 思考2 → 🔧 工具组2 …` 时间线交错
- **工具面板标题状态感知**：流式「🔧 工具执行中 · N 步」/ 完成态「🔧 工具执行 · N 步 (Xs)」
- **群聊安全边界可视化**：Studio 直接开关 + 编辑豁免群白名单；手写自定义 `text` 与 gateway 兄弟键原样保留

### ✅ 验证

全量 pytest 回归通过；Studio 写回安全（拒写 / 备份轮转 / 白名单合并）与预览渲染均有用例覆盖。

### 📦 升级

```bash
cd ~/projects/hermes-fry-cards && git pull
HERMES_PYTHON=~/.hermes/hermes-agent/venv/bin/python3
$HERMES_PYTHON -m pip install -U .
$HERMES_PYTHON -m hermes_fry_cards uninstall
$HERMES_PYTHON -m hermes_fry_cards install
hermes gateway restart
```

> ⚠️ 本版重构注入模板，**必须重跑 `uninstall` + `install`** 才能生效。配置 schema 向后兼容，无需改现有配置。

---

完整明细见 [CHANGELOG.md](https://github.com/techysy/hermes-fry-cards/blob/main/CHANGELOG.md)。

**Full Changelog**: [v0.3.3...v0.4.0](https://github.com/techysy/hermes-fry-cards/compare/v0.3.3...v0.4.0)

## 🍟 hermes-fry-cards v0.1.1（首个正式版本）

> 灵感来自 [hermes-lark-streaming](https://github.com/Cheerwhy/hermes-lark-streaming)，独立开发版本。

经过 rc2–rc7 七轮预览版迭代，插件核心链路趋于稳定，正式发布 🎉

### 🛡️ 本次更新：内部稳定性优化

对照 OPTIMIZATION_PLAN 差距分析，落地全部 P0 三项与 P1 补齐。**配置项与卡片样式零变化**，升级无需改任何配置。

**session 生命周期统一**

- 新增 `_register_session` / `_dispose_session` 单一入口，清理幂等（重复执行不报错）
- 中断接管后旧 session 清理不再误删新 session 映射
- 同 message_id 旧会话已终态时允许重建（原先永久拒新直到重启网关）

**FlushController 竞态修复**

- 完成标记与重刷请求交叉时，不再对已完成卡片发起多余的 CardKit API 调用
- 消除「timer 触发 + 立即路径」双刷同一份数据的问题

**失败分类与结构化日志**

- 失败原因随 session 记录且不被后续覆盖，排障可直接定位首次失败点
- 建卡失败区分飞书 API 错误码与未知错误
- 日志事件标准化：`session_created` / `card_created` / `card_reply_failed` / `fallback_to_text` / `session_disposed`

**质量保障**

- 新增 9 个回归测试：499 通过 / 仅剩 4 个基线遗留失败
- 自 rc7 起默认值已对齐推荐配置，新装开箱即用

### 🚀 安装

```bash
curl https://raw.githubusercontent.com/techysy/hermes-fry-cards/main/INSTALL.md
```

### 手动安装

```bash
git clone https://github.com/techysy/hermes-fry-cards.git
cd hermes-fry-cards
HERMES_PYTHON=~/.hermes/hermes-agent/venv/bin/python3
$HERMES_PYTHON -m pip install -e .
$HERMES_PYTHON -m hermes_fry_cards verify
$HERMES_PYTHON -m hermes_fry_cards install
```

然后重启 gateway（在外部终端执行）：

```bash
hermes gateway restart
```

### 卸载

```bash
HERMES_PYTHON=~/.hermes/hermes-agent/venv/bin/python3
$HERMES_PYTHON -m hermes_fry_cards uninstall
$HERMES_PYTHON -m pip uninstall hermes-fry-cards
```

---

[MIT License](LICENSE) · [安装文档](INSTALL.md) · [English](README.en.md)
