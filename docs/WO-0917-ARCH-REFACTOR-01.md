# 任务工单 · 飞书流式卡片原生架构重构 (WO-0917-ARCH-REFACTOR-01)

> 派单：小兔（督导）· 模式：方案 B 官方原生架构内生重构  
> 参考来源：SkillHub 安全重构方法论 (`@clawhub_wangzhiming1999/refactor-safely`) + 任务运转手册 (`task-operations-manual`)  
> 核心原则：小步安全、行为不变、零外挂脚本、测试全绿、白名单硬锁。

---

## 一、一句话目标
严格遵循 `techysy/hermes-fry-cards` 官方分层架构规范，对底层网络自愈（300315/429）、状态机生命周期（CAS锁/30s超时/幂等关流）、渲染排版（短思考合并/Cron卡多态折叠）进行系统性内生重构，清理工作区临时残留，新增回归契约测试。

---

## 二、范围白名单（严格锁定 5+1 个文件）

| 序号 | 文件绝对路径 | 负责层级 | 重构范围 |
|---|---|---|---|
| 1 | `/home/linxuan/hermes-fry-cards/hermes_fry_cards/feishu.py` | 底层网络驱动层 | 300315 `not find elementID` 幂等自愈；`99991400` 频控加入瞬态重试 |
| 2 | `/home/linxuan/hermes-fry-cards/hermes_fry_cards/streaming/session.py` | 会话状态机 | `CardSession` 增加 `_completion_dispatched` CAS 标志 |
| 3 | `/home/linxuan/hermes-fry-cards/hermes_fry_cards/controller.py` | 总控调度层 | `_complete_session` CAS 原子防重拦截；2x TTL 僵尸会话熔断 |
| 4 | `/home/linxuan/hermes-fry-cards/hermes_fry_cards/streaming/controller.py` | 流式运行时 | 封卡 `asyncio.wait_for(timeout=30.0)` 硬超时保护；`close_streaming` 幂等调用 |
| 5 | `/home/linxuan/hermes-fry-cards/hermes_fry_cards/cardkit/builder.py` | 渲染引擎层 | `MERGE_THRESHOLD = 30` 短思考合并；`build_cron_card` 动态配色与折叠 |
| 6 | `/home/linxuan/hermes-fry-cards/tests/test_harden_b_features.py` | 契约测试层 | 新增专项测试套件（新文件） |

> ⚠️ **红线**：白名单外多改一个文件即违规整单退回；严禁改动 `config.yaml`。

---

## 三、基线固化与备份锚点

### 开工前基线哈希表 (SHA-256)
- `feishu.py`: `32809b41f9cfc7d09d5e1e4696954b9f8edecf47c51f7e5f0e1f9ee36250bd31`
- `controller.py`: `8f96a990167c0d609086cda2cb89d9b7318ea9bebdf70cc84a0ae5bad96625ea`
- `streaming/session.py`: `286bec075cbcbf31ae276e69d77a5ad3cb306aa7284f451db5e188b82762b550`
- `streaming/controller.py`: `a0a27a8ce02d52a8afa8a1173a36e22c11421749504dfe753c7bf4cecae40384`
- `cardkit/builder.py`: `05e9a1766559751501c302a5fd21999cd4428aad97a96cc677af1e3c0cf79b91`

### 备份指令与锚点
```bash
cp hermes_fry_cards/feishu.py hermes_fry_cards/feishu.py.bak-WO-REFACTOR
cp hermes_fry_cards/controller.py hermes_fry_cards/controller.py.bak-WO-REFACTOR
cp hermes_fry_cards/streaming/session.py hermes_fry_cards/streaming/session.py.bak-WO-REFACTOR
cp hermes_fry_cards/streaming/controller.py hermes_fry_cards/streaming/controller.py.bak-WO-REFACTOR
cp hermes_fry_cards/cardkit/builder.py hermes_fry_cards/cardkit/builder.py.bak-WO-REFACTOR
```

---

## 四、施工步骤与顺序锁（①→②→③→④，禁抢跑）

### 步骤①：底层协议驱动加固 (`feishu.py`)
- **改动**：
  1. 引入常量 `CARDKIT_RATE_LIMIT = 99991400`，纳入 `CARDKIT_TRANSIENT_ERROR_CODES`；
  2. 在 `cardkit_batch_update` 和 `_cardkit_retry` 中增加 300315 识别逻辑：若 `e.code == 300315` 且 `not find elementID` 在 `str(e)` 中，视为已被前序操作清理，视为幂等成功放行。
- **停手条件**：若现有重试逻辑包含未被测试覆盖的魔改结构，立即停手。

### 步骤②：生命周期与状态机重构 (`session.py` + `controller.py` + `streaming/controller.py`)
- **改动**：
  1. `session.py`: `CardSession.__slots__` 增加 `_completion_dispatched`，初始化为 `False`；
  2. `controller.py`: `_complete_session` 入口增加 CAS 防重判断：若已 `_completion_dispatched` 则直接返回；
  3. `streaming/controller.py`: `_do_complete_card` 增加 `asyncio.wait_for(timeout=30.0)` 全局防死锁；无论 `streaming_closed` 标记为何，封卡时执行一次幂等关闭。
- **停手条件**：现有多线程锁调用发生死锁阻断，立即停手。

### 步骤③：渲染引擎层排版精炼 (`cardkit/builder.py`)
- **改动**：
  1. `_build_reasoning_panel` / `unified_children` 组装：连续低于 30 字符的推理轮次自动合并为单块，消除碎片化；
  2. `build_cron_card`: 支持 `status` 状态机判断，成功=绿色，超时/失败=红色；超 5 行内容自动收进折叠面板。
- **停手条件**：现有的 `split_complete_card` 拆卡契约受影响，立即停手。

### 步骤④：工作区卫生清理与全量回归测试
- **改动**：
  1. 清理工作区历史临时残余文件 (`*.bak-0917-penetrate`, `*.bak-0917-fix` 等)；
  2. 编写 `tests/test_harden_b_features.py`，全量运行 660+ 测试。

---

## 五、验收标准（DoD）
1. [ ] 白名单内 5 个文件重构完成，零白名单外文件被改动；
2. [ ] 工作区无悬挂的临时垃圾文件；
3. [ ] 新增 `test_harden_b_features.py` 测试全绿通过；
4. [ ] 既有 663 个回归测试 100% 保持通过，零破坏性回退；
5. [ ] 提供完整的指纹哈希表与回滚指令。
