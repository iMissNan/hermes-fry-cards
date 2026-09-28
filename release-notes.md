## 🍟 hermes-fry-cards v0.4.2（速度 / 缓存命中率 · 字段自由组合）

> 完成卡片对齐主流编程客户端的统计展示：footer 与统一面板 header 新增**速度（tok/s）**与
> **缓存命中率**，口径与 Hermes CLI 状态栏完全一致；两处元数据栏的字段全部可在 Studio
> 自由勾选组合。

**⚡ 统计字段**

- footer 新增 `speed`（tok/s）与 `cache`（缓存命中 %）：速度 = 近 10 次 API 调用
  `sum(output)/sum(latency)` 纯生成吞吐（剔除工具耗时）；命中率 = `cache_read / prompt_tokens`
  （prompt 已含缓存，同 Hermes 归一化口径）；零读取/无数据自动隐藏（无数据 ≠ 0%）
- 默认 footer 布局：`[status, elapsed, speed, cache, context, model]`

**🧩 字段自由组合**

- 统一面板 header 字段化：`display.platforms.feishu.panel_fields` 与 footer 共用字段池
  （status/elapsed/speed/cache/tokens/context/model）+ 面板专属 `reasoning`/`tools` 计数
- 默认 `[model, reasoning, tools, context, elapsed]`，与历史布局逐字一致，老用户无感
- Studio chip 开关式勾选（参考 CreditDaddy 仪表盘组件交互），预览实时渲染新字段

**🛠️ 修复**

- Studio footer 字段白名单缺 `speed`/`cache`：GUI 勾选新字段保存 400 的坑（已补测试回归）

**⬆️ 升级注意**

- 注入模板变更：已装环境重跑 `hermes_fry_cards uninstall` + `install` 后重启网关即可；
  旧模板不传新键，向后兼容（字段自动隐藏）

---

## 🍟 hermes-fry-cards v0.4.1（Studio 自启与保活 · 默认绑 0.0.0.0）

> 新增 systemd 用户服务模板，让 Studio 支持开机/登录自启、异常退出自动重启、日志交给 `journalctl`；
> 并把 Studio 默认监听从 `127.0.0.1` 改为 `0.0.0.0`——局域网设备直接 `http://<本机IP>:8765` 就能用。

**⚙️ Studio 自启 / 保活**

- 新增 `systemd/hermes-fry-cards-studio.service`
- 默认使用 Hermes venv Python，以 `--no-browser` 常驻运行 `0.0.0.0:8765`（本机 `http://127.0.0.1:8765`）
- `Restart=on-failure` + 3 秒退避，Studio 异常退出后自动拉起
- 文档补充安装、启用、状态检查和日志查看命令

**🌐 默认绑 0.0.0.0（局域网可达）**

- `_cmd_studio` / `run_studio_server` / systemd 模板 `ExecStart` 三处默认 host 统一为 `0.0.0.0`
- 本机打印与自动打开的 URL 回落 `127.0.0.1`（新增 `_display_host`），另打印一行 LAN 地址提示
- Host 门白名单可配置：`studio.allowed_hosts` 附加网段/主机（默认仅 loopback），非白名单 403（防 DNS rebinding）

**🛠️ 修复**（[#13](https://github.com/techysy/hermes-fry-cards/issues/13) / [#14](https://github.com/techysy/hermes-fry-cards/issues/14) / [#15](https://github.com/techysy/hermes-fry-cards/issues/15)）

- 完成态卡片丢失最终答案：多工具回合的旁白 ANSWER 段不再吞掉完成态注入，答案按交错时间线追加
- cron 投递 230001 invalid receive_id：兼容 0.21.0 起的 dict 形 delivery，跨调度布局解析投递身份
- clarify toast SDK 惰性加载：adapter 导入不再触碰 lark_oapi，10s 插件预算不再被拖爆

**🔔 完成通知**（[#16](https://github.com/techysy/hermes-fry-cards/issues/16)）

- `streaming.completion_notice` / `completion_notice_text`（默认关）：卡片收尾后回复一条「回答结束 · 耗时」短通知
- Studio 正文大字号选项（`heading` 档）
- ⚠️ Studio 可写 `config.yaml` 与飞书凭据——别做端口转发/公网暴露；只想本机用就 `--host 127.0.0.1`
- 新增 `TestWildcardBindDefaults` 守住三处默认值

升级后执行：

```bash
mkdir -p ~/.config/systemd/user
cp systemd/hermes-fry-cards-studio.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now hermes-fry-cards-studio.service
```

---

## 🍟 hermes-fry-cards v0.4.0（算法与架构大改版）

> 配置 schema **向后兼容**——升级无需改任何现有配置，装完 `hermes gateway restart` 即可。

**🧱 Markdown 防爆引擎**

- 超限表格无损压缩为「Table N · Row M」字段列表（fence 感知扫描，inline code 竖线/未闭合围栏均正确处理）
- 字节级内容预算 `clamp_utf8`（18KB）：流式渐进截断 + 完成态首尾双保，杜绝 ~30KB 卡片 JSON 溢出断屏

**🎛️ Studio 可视化配置工作坊**（`python -m hermes_fry_cards studio`）

- 三页签：配置（白名单键表单 + 群聊安全边界）/ 预览（**服务端真实 builder** 渲染，4 场景 × 三态）/ 状态（hook 注入、兼容性、版本号、一键重启）
- 写回安全五件套：严格校验 / 解析失败拒写 / 备份轮转 20 份 / 白名单深合并 / 原子落盘
- 仅监听 127.0.0.1，Host 门防 DNS rebinding；宽屏三列响应式布局

**🏷️ 模型别名时段人设**（与 openclaw/claw-fry-cards 格式逐字兼容）

- `model_aliases.json` 值支持时段对象：按北京时间 HH:MM + 星期自动切换显示名（DeepSeek 峰谷：峰段梁文锋⚡️ / 谷段梁文谷⚡️）
- 总开关 `display.model_aliases_enabled`；Studio 内可视化编辑（星期芯片 + 工作日/周末快捷选择）

**🛡️ 群聊安全边界可视化**

- Studio 直接开关 + 编辑豁免群白名单；手写自定义 `text` 与 gateway 兄弟键原样保留

**🔀 工作流交错渲染**（[#10](https://github.com/techysy/hermes-fry-cards/pull/10)，感谢 @JasonXX89）

- 完成态统一面板按真实发生顺序交错展现：`💭 思考1 → 🔧 工具组1 → 💭 思考2 → 🔧 工具组2 …`
- 工具面板标题状态感知：流式「🔧 工具执行中 · N 步」/ 完成态「🔧 工具执行 · N 步 (Xs)」

**其他**：瞬态错误码扩充（频控 230020 / 99991400）、内容层文案双语（`streaming.content_lang`）、星期芯片周一起始、状态页与顶栏版本号显示。

---

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
