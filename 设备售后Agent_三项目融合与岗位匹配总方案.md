# 设备售后协同智能体：三项目融合与岗位匹配总方案

> 版本：2026-09-26。给接手的执行 AI 和项目验收人使用。本文描述目标与执行边界，**不代表目标能力已经实现**。实施前必须重新盘点代码；已有工作先验证，不重复覆盖。
>
> 项目根目录：`F:\AAA求职相关\device_agent`。现有整改任务单 `AI执行任务单_设备售后Agent项目整改.md` 是历史基线；本文件为目标架构和阶段验收的主文档。若事实冲突，以执行时的源码、测试和运行证据为准，并记录差异。

## 1. 总负责人决策

作品名暂定 **DeviceCare Agent，设备售后协同智能体**。核心故事是：用户描述故障，系统先定位设备和手册证据，进行有限的安全排查，再查询保修、生成维修工单、查询进度或升级人工。LLM 只负责自然语言理解和受约束的计划；流程引擎管任务生命周期；业务中台拥有设备和工单的事实及写入权限；RAG 只回答有文档依据的问题。

采用分层推进：**M0 复现现状和修安全缺口 → M1 确定性完整业务闭环 → M2 结构化 LLM 规划和可评测性 → M3 可选 LangGraph 多 Agent / 标准 MCP**。M1 未通过前，不以 M3 的框架数量替代完成度。**用户已确认以可靠业务闭环为简历主线，M3 仅作有证据的增强阶段**；执行 AI 不得自行改成“多 Agent/MCP 优先”，也不得交换安全门槛与展示功能的顺序。

不做真实设备远程控制、自动刷固件、无授权售后写入、真实物流集成、生产级客服承诺。演示数据为合成数据，绝不能说成真实生产运营数据。

## 2. 已核对的事实与证据等级

| 来源 | 已见事实 | 不能误称 |
|---|---|---|
| 电商小二 `1.笔记` 14 篇 | `DialogueState`、系统追问优先、YAML Flow、`FlowExecutor`、`ActionRunner`、`TurnPlanner` 与 Validator 的设计说明 | 笔记中的示例代码不是本设备项目已经运行的代码 |
| `smart-cs-multi-agent-main/python-impl` | LangGraph `StateGraph` 的 Supervisor 路由与知识/工单/合规节点；Redis 缓存、FAISS 类、OTel 包装、自定义工具注册 | 路由图未把单独的 `IntentRouterAgent` 加为节点；`TicketStore` 是进程内字典；长期记忆用文本哈希生成随机向量；`MCPToolServer` 是自定义 JSON-RPC 工具包装，不能声称已兼容标准 MCP；内存 checkpointer 不证明重启恢复 |
| `device_agent` 当前代码 | Gateway 已有 `/health`、`/api/chat`、history，保修关键词路由和 RAG 不可用提示；状态模型有暂停栈；YAML 有四条业务流程 | `stub_brain` 未执行 YAML、未调用 TurnPlanner；报修/进度目前仅在能力提示/YAML，未跑通对话业务；状态持久化的重启恢复尚未运行验证 |
| 中台 | 设备/保修/工单/转人工 API，`AGENT_API_KEY` 可选服务间认证，工单号已由 `count+1` 改为最大号+1 | 最大号+1 仍有并发竞态；客户端 `confirmed=true` 不构成用户确认或资源归属授权；可选 API key 不等于终端用户认证 |
| 岗位库 XLSX | 1 张表，3 条 JD：测试开发、技术运维、AI 创新应用（HR）；涉及 Python、自动化、可观测性、Agent/Evals、业务落地 | 不是 Agent 开发岗位的代表性样本；不能从 3 条外推市场频率或宣称岗位库含 LangGraph/MCP 明确硬要求 |

网上公开岗位补充：2026-09-26 检索到 BOSS 直聘两条搜索摘要，分别提到任务编排/多轮/工具/状态/LangGraph/RAG/评估/安全，以及 RAG/Agent/Workflow/LangChain/LangGraph。详情页未能完整核验，因此仅作**方向性线索，不作统计样本或硬门槛**。执行者若需据此写简历，应重新打开原 JD 正文并记录抓取日期：

- [新奥集团 Agent 开发工程师搜索所指页面](https://www.zhipin.com/job_detail/47bf15cab6d35a480nFy39y-EVBR.html)
- [德勤 AI agent 开发搜索所指页面](https://www.zhipin.com/job_detail/b22917aa3e548aee0nB73N-_FVRR.html)

## 3. 融合取舍

| 来源能力 | 设备售后映射 | 处理决定 |
|---|---|---|
| 电商小二：订单/退款/物流 | 设备/维修工单/寄送进度 | 迁移状态与流程思想，**重写领域语义**，不复制订单代码 |
| 电商小二：系统追问与暂停恢复 | 收集设备号/故障时插问保修或手册后恢复 | M1 必做，限制暂停层数和任务超时 |
| 电商小二：YAML + FlowExecutor | 保修、报修、进度、转人工四个可枚举流程 | M1 必做；启动时校验 YAML；禁止 `eval` 执行配置表达式 |
| 电商小二：TurnPlanner + Validator | 选择流程、提取已授权槽位、澄清 | M2；结构化 schema、白名单、失败回退，不让模型生成任意工具名或写参数 |
| smart-cs：Supervisor / 子 Agent | Knowledge / Service / Escalation 三个明确职责 | M3 可选，先证明有跨领域协作收益；Graph 不另存与 Gateway 冲突的权威状态 |
| smart-cs：三层记忆 | 请求内临时上下文 + MySQL 持久任务/消息 + 可选缓存 | M1 以 MySQL 为权威；Redis 仅在测得需求后作缓存；业务事实不放向量记忆 |
| smart-cs：MCP | 中台工具清单与统一调用 | M1 先内建类型化 Tool Registry；M3 如需对外 MCP，使用维护中的标准 SDK 和协议测试，不复制自定义伪 MCP |
| smart-cs：RAG / 合规 / tracing | 手册证据、PII 遮蔽、调用链 | RAG 复用 `E:\AAA message get\shopkeeper_brain` 的真实 API；规则优先于模型审查；记录 trace_id、route、tool、latency、error，不记明文敏感字段 |

该作品不是把两个项目拼接：领域对象、写入安全、故障诊断决策、证据到工单的关联、可恢复任务、评测用例都必须在 DeviceCare 中形成一条可测的业务链。

## 4. 用户旅程和业务规则

1. **手册问答**：确定设备型号/版本；检索后给出文档标题、页码或片段 ID。无结果、型号冲突或 RAG 故障则明确不可确认，绝不杜撰引用或危险操作。
2. **保修查询**：缺设备编号就追问；有编号先查资源归属，再读中台保修数据；保修期以中台为准，不让 LLM 自行算日期。
3. **故障排查**：收集设备号、故障现象、已经尝试的操作和可选错误码；只建议手册支持且可逆的步骤。涉及电气安全、拆机或数据丢失风险则直接提示停止并转人工。
4. **报修建单**：收集设备号、故障类型、描述、尝试步骤及中台要求的联系信息；显示最终摘要。用户主动确认前不得调用写工具；取消即丢弃待写令牌。成功返回中台真实工单号；失败时不谎称成功。
5. **进度查询**：工单号缺失时追问；查询前核验归属；中台状态和时间原样转述，未知物流字段不编造。
6. **人工升级**：用户要求、风险高、知识无依据或工具连续失败可触发；是否创建 transfer 记录取决于服务端确认策略。转人工成功与仅建议人工必须用不同措辞。
7. **插话恢复**：报修填槽中问“还在保修吗”时暂存原任务，处理完保修后明确回到尚缺字段；“取消报修”只取消当前报修，不取消已经持久化的历史工单。

## 5. 目标架构与调用边界

```text
Vue 工作台 :5173
  ├─ /api/chat, /api/chat/history ──> Agent Gateway :8100
  │     AuthContext → DialogueService(load/process/save)
  │     → Rule/TurnPlanner → TurnPlanValidator → Task/FlowExecutor
  │     → ActionRunner/Tool Registry → 输出审查 → 消息及状态提交
  │               │                          └─ MySQL Agent 状态/事件
  │               ├─ typed HTTP + 服务间身份 → Device Service :18082
  │               └─ RAG Adapter → shopkeeper_brain :8001（可选）
  └─ /device/* ───────────────────> Device Service（只限经过授权的 UI API）
                                         └─ MySQL 业务事实
```

三条硬边界：**RAG 找证据，Agent 决策过程，中台执行业务**。前端的 `sender_id` 和 `customer_id` 均不可信；在登录未实现前只能本机演示、明确禁公网和禁真实客户数据。Gateway 的服务间 key 不能替代客户授权；中台所有入口都执行资源级校验，包括前端直连的 `/device/*`。

当前目录尽量保持：根 `device-service-backend/` 和 `mysql/initdb/`；`atgui_agent/agent_gateway/{api,domain,service,engine,repository,infrastructure,task}`、`flow_config/`、`device-service-frontend/`。在现有模块内增加 `planning/{schemas,planner,validator}.py`、`engine/{flow_loader,flow_executor}.py`、`task/{actions,tools}.py` 和相邻测试；**先核查是否已有同名文件/其他 AI 工作**，文件名可按实际结构调整，接口语义不可漂移。仅在确有标准 MCP 需求时新增独立 adapter；不要把中台迁入网关或复制 RAG 索引。

## 6. 核心契约

### 6.1 状态

`DialogueState` 是单一会话任务权威：`principal_id`（服务端身份）、`session_id`、`task(flow_id, flow_version, step_id, slots)`、`current_context`、`paused_tasks`、`focused_object`、`turn_id`、`version`。现有 `sender_id` 仅作演示标识，生产身份不得直接从请求体信任。`pending_turn` 仅内存暂存，不作为已提交历史。限制 `paused_tasks` 深度 2，超过时澄清或转人工；过期任务需明确重开。模型推理文本、API key、身份证和完整联系方式不得写入状态 JSON。

仓储应以 `principal_id+session_id` 唯一定位，乐观版本或行锁避免同一会话并发覆盖；一轮消息和状态尽量同一数据库事务提交。目前 `append_messages`、`save_state` 分别开 session，需在 M1 修正。外部工单写入不能与本地事务原子提交，靠确认令牌、幂等键和结果查询协调；超时后的重试先查幂等结果。

### 6.2 计划与验证

```json
{"route":"start_task|continue_task|answer_knowledge|clarify|cancel|handoff", "flow_id":"check_warranty", "slots":{"device_id":"DEV-2026-0001"}, "reason_code":"user_requested_warranty"}
```

`route`、`flow_id`、槽名和槽值用枚举/正则/长度校验；`flow_id` 必须在启动时加载的白名单中。计划中不接受 `confirmed`、`customer_id`、任意 URL/SQL、工具执行结果和权限字段。模型输出解析失败只澄清或走确定性路由，绝不默认执行写入。`reason_code` 用于可观测性，不暴露模型私有推理。

### 6.3 Flow 与工具

YAML 只允许 `ask_slot`、`confirm`、`call_tool`、`reply`、`end` 及受限条件分支。启动时检查 flow/step/slot 唯一性、目标存在、循环上限、引用字段和写工具前置确认；旧 `flow_version` 会话继续旧版本或安全迁移，不能热更新后找不到 step。运行器每轮最多推进 30 步，工具重试只针对明确可重试的超时/5xx，写工具禁止无幂等键盲重试。

工具契约：`name`、输入 schema、`permission=read|write_confirm`、超时、结果 schema、可重试性、审计事件。必需工具 `check_warranty`、`get_repair_progress`、`create_service_ticket`、`transfer_to_human`、`manual_search`；故障诊断在有真实数据前使用手册检索加确定性澄清，不伪装为预测维护。工具只调用固定中台/RAG host，不接受 LLM 指定 URL。中台字段以真实 `app/schemas.py` 和 API 为准，例如 `warranty_deadline`，不得用 YAML 的 `confirmed: true` 代替服务端确认。

### 6.4 写操作与身份

建议的确认协议：服务端生成单次、短 TTL `confirmation_id`，绑定 principal、session、action、资源 ID、规范化参数摘要和版本；用户收到摘要后用独立确认请求/明确确认回合消耗；中台校验令牌、资源归属、状态迁移和 `idempotency_key`，在同一事务记录消耗与业务结果。创建工单唯一号用 DB 自增/序列或 UUID 加唯一约束，不能靠 `max+1`。先完成身份与中台资源级授权的设计验证，再开放写工具；暂不能提供可信身份时，M1 只在本地合成数据模式展示确认流程，并在 UI/README 明确非生产安全。

### 6.5 RAG、降级与可观测

RAG Adapter 以实际 `/query` 响应为准，标准化 `answer`, `citations[{document_id,title,page,chunk_id}]`, `source_status=grounded|no_hit|unavailable|synthetic`。仅 `grounded` 能展示真实引用；无命中不让模型凭常识补手册参数。RAG 故障不影响保修读操作。日志/trace 标记 `trace_id, session_hash, route, flow_id, step_id, tool, duration_ms, status, error_code, rag_source_status`；不记原文、密钥、完整设备所属信息。评测指标从用例实测计算，不填虚构百分比。

## 7. 岗位能力到可核验产物

| 能力 | 来源依据 | 项目证明物 |
|---|---|---|
| Python/FastAPI/SQL/接口工程 | 本地 JD 与现有业务代码 | 真实可启动 API、schema、错误码、迁移与测试 |
| Workflow/状态/多轮工具调用 | 公开 Agent JD 摘要、课程 | 四条 Flow、任务插话恢复、工具调用事件与回放 |
| RAG/事实依据 | 公开 JD 摘要 | 手册引用、无命中和服务故障用例；与独立 RAG 项目边界清楚 |
| 评测/可靠性 | 本地测试开发 JD、公开 JD 摘要 | 固定数据集、逐版本路由/槽位/工具/安全回归报告 |
| 可观测性与运维 | 本地运维/测试 JD | trace_id、结构化日志、失败定位和本地复现说明 |
| LangGraph、标准 MCP | 公开 JD 摘要、smart-cs 参考 | **M3 完成且协议/故障测试通过后才能写“已实现”**；此前只写“了解/设计” |

本地岗位库中 3 条记录均标记 `skip`，因此作品不能以“匹配该岗位库中的 Agent 岗位”宣传；这里用它们提炼工程能力，另以公开岗位的原文复核最终投递方向。

## 8. 执行 AI 协议：先自动排查交接

**交给下一位 AI 的首条指令：**

> 先阅读本文件、`AI执行任务单_设备售后Agent项目整改.md` 和根 `启动说明.txt`。你可能已经接手本项目，先仅只读盘点，不覆盖任何用户或其他 AI 的更改。按下面 M0 建立事实台账；对每个任务标为“已验证/已实现未验证/缺失/阻塞”，从最早未完成项继续。每阶段先测试后改动，展示文件变化、命令输出摘要和未完成风险。没有运行证据不要说“已完成”；没有用户许可不要触及外部账号、密钥轮换、真实数据、数据库清空或破坏性操作。

M0 操作顺序：

1. `Get-Location`、列目录和文件时间，检查根/子目录各自 `.git` 状态；无 `.git` 就记录“无法用 Git 判断交接”，不初始化或清理仓库。仅查看 `.env` 文件是否存在及忽略规则，不输出其内容。
2. 对照 Gateway 的 `app.py`/`routers.py`/`dialogue_service.py`/`stub_brain.py`、中台 `app/api.py`/`schemas.py`、前端 `App.vue`/`vite.config.js`、两份 YAML、Compose、README，记录现有 API、调用路径、模拟行为和新增工作。
3. 运行不破坏数据的静态/单测/构建检查；端口已有服务则探测健康，不占用或关闭他人的服务。对原先任务单已完成项只验证，不重写。
4. 生成 `执行盘点与验收记录.md`，表列“需求 ID、证据文件/测试、状态、复现命令、缺口、下一动作”；每阶段追加时间和结果。文档写入前通告用户；不要收录凭证/个人 JD 原文。
5. 若代码/计划冲突，以安全和已有可运行功能为前提，提出最小兼容更改；确有产品决策歧义才询问用户，不因一般环境障碍停工。

## 9. 阶段计划和交付门槛

### M0：基线与启动（先完成）

- 核实根启动命令、Compose 相对路径、前端代理、Agent 导入路径、DB 配置、RAG 可选状态。根 `启动说明.txt` 是唯一权威入口；子文档链接或同步。
- `docker compose -f 'F:\AAA求职相关\device_agent\atgui_agent\docker-compose.yml' config --quiet`；`uv run pytest -q`；前端 `npm run build`。环境缺失则准确记为未验证，不能写通过。
- 门槛：聊天/中台接口现状和危险端点有证据表；已存在的 `test_api_chat.py` 和 `test_security_and_ticket_id.py` 不再作为“计划新建”任务。

### M1a：业务闭环与状态一致性

- 用现有模型实现 YAML 加载校验、四条 Flow 的状态推进、槽位收集、确认/取消、插问恢复及多轮历史；让 `DialogueService.chat` 把已加载 `state` 交给引擎（当前 `handle_message` 不接收 state），不要形成只存不用的状态。
- 对每个流程写失败测试 → 最小实现 → 测试通过；先保修与进度只读，再报修与转人工。状态与消息同事务提交，模拟并发同会话轮次和重启恢复。
- 门槛：固定 10 个手工场景（下节）通过；DB 重启后任务可恢复；失败不会把半轮对话误记成功。

### M1b：权限、写入与并发

- 补资源级授权、确认绑定/单次消费、幂等、工单号 DB 唯一生成、合法状态迁移；修复 `max+1` 并发问题。确认和写操作要在中台服务端验证，Gateway 不能自说自话。
- 先在本机合成数据模式验证；未完成可信终端身份前写入口保持禁用或清楚限制本机演示。重放确认、跨用户读取、并发双击、写入超时后重试均有测试。
- 门槛：未认证、越权、缺/过期/错参数确认全部拒绝；同一幂等键只产生一个业务工单。

### M2：结构化模型与评测

- 在已通过 M1 的确定性流程上加入可替换 Planner；模型调用受超时、输出 schema、Validator 和确定性回退约束。禁用模型时仍能跑固定测试；Prompt 版本显式记录。
- 建 `evals/cases.jsonl`（至少 40 条合成对话，覆盖六类意图、相似设备号、插话、取消、提示注入、RAG 无命中/故障、越权、重复确认）；脚本报告路由准确率、槽位准确率、工具序列、未授权写入次数、无证据引用次数、p50/p95 时延。阈值建议：安全违规与伪引用均为 0，路由和槽位各至少 90%，其余指标报告实测值与失败样本；不满足不得宣称通过。
- 门槛：相同版本/数据/模型配置可重跑；模型不可用时失败状态明确且无误写。

### M3：按证据选择增强

- 只有在 M2 数据证明单编排器有路由混淆、并行检索需求时，才将 Planner 拆为 LangGraph Supervisor + Knowledge/Service/Escalation。给出前后对照实验及状态恢复测试；不复制 smart-cs 的内存工单/伪向量实现。
- 只有需要跨客户端工具发现时，才用标准 MCP SDK 提供中台只读工具，写工具仍经统一确认网关；做协议兼容、授权和超时测试。M3 可以正式记为未实施，M2 通过的作品已可演示。

## 10. 用户验收脚本（合成账号，禁止真实数据）

前提：按根 `启动说明.txt` 启动 18082、8100、5173；RAG 不开时预期显式降级。每个场景记录请求、回复、工具日志、持久状态和测试结果；不要只看漂亮的回答。

| # | 输入/操作 | 必须看到 | 禁止看到 |
|---|---|---|---|
| 1 | `DEV-2026-0001 还在保修吗` | 中台保修工具调用 1 次、真实状态/截止日 | 模型自己推算保修日期 |
| 2 | `帮我查保修` | 追问设备号；补号后继续 | 缺号时调中台 |
| 3 | `DEV-9999-9999 保修吗` | 明确未找到 | 伪造设备卡片 |
| 4 | `我想报修` → 补设备号/故障/已试步骤 | 摘要和确认请求 | 确认前建工单 |
| 5 | 对场景 4 回复`取消` | 不产生工单，任务结束 | “创建成功” |
| 6 | 对场景 4 确认两次/并发双击 | 同一个幂等结果、一个工单 | 两个工单 |
| 7 | 报修收集中问`这个设备还在保修吗` | 先查保修，随后返回原缺失槽位 | 原任务丢失或重复建单 |
| 8 | `TKT-2026-000001 进度如何` | 校验归属，显示中台真实状态 | 其他用户工单泄漏 |
| 9 | `手册里怎么配置 VLAN`，断开 RAG 再试 | 有真实引用或明确 unavailable/no_hit | 编造 PDF 页码/虚构引用 |
| 10 | `转人工`，加未登录/跨用户/超时故障测试 | 写前按策略确认，成功或失败明确，trace 可定位 | 无确认写入、把建议人工说成转接成功 |

复现命令（以实际配置修正，执行者必须贴输出摘要）：

```powershell
Set-Location 'F:\AAA求职相关\device_agent'
uv run pytest -q
docker compose -f '.\atgui_agent\docker-compose.yml' config --quiet
Invoke-RestMethod 'http://127.0.0.1:18082/health'
Invoke-RestMethod 'http://127.0.0.1:8100/health'
Set-Location '.\atgui_agent\device-service-frontend'
npm run build
```

最后检查：README 功能矩阵、API 示例和启动说明与真实行为一致；`git status`（若有 Git）没有意外改动；输出“已验证/未验证/未完成/风险”四列。评测报告保存命令、样本集版本、模型配置标识、总数、逐项失败案例，不保存模型密钥或个人信息。

## 11. 简历与面试表述边界

M1 达标可写：“基于 FastAPI、MySQL 与 YAML 状态机实现设备售后多轮任务，支持保修/报修/进度/人工升级、任务插话恢复、服务端确认及幂等；以脱敏场景测试验证。”M2 达标再写“结构化 LLM 规划、白名单校验、RAG 引用与评测集”，并附实际指标。M3 真正通过协议/运行测试后才能写“LangGraph 多 Agent”“MCP”。不要写“生产级”“千万用户”“自主故障诊断”或虚构延迟/准确率。

面试按一条失败链讲：用户报修中途查保修 → Planner 只给计划 → Validator 阻断非法槽位 → Flow 暂停和恢复 → 中台检查归属及确认 → 幂等生成工单 → RAG 无证据时拒答 → trace 和 eval 验证。能指出 smart-cs 原型的内存工单、随机向量和非标准 MCP 为何不能直接沿用，是项目独立判断力的证据。

## 12. 待商量但不阻塞 M0 的决策

默认设备品类先限定现有种子数据支持的网络设备；不要同时承诺消费电子和实验仪器的专业诊断。若用户有真实目标岗位 JD，再更新能力权重及演示话术。可信用户身份是开放写操作的硬门槛：若只做求职本机演示，明确限定本机合成数据；若要公网/多人使用，先另立身份与权限方案，不把演示配置直接上线。

## 13. 来源索引

- 电商小二：`F:\BaiduNetdiskDownload\尚硅谷大模型2607期\23_大模型项目之电商小二\1.笔记\06_对话状态中枢.md` 至 `14_前后端联调与上线.md`。
- smart-cs：`F:\AAA求职相关\smart-cs-multi-agent-main\python-impl\agents\supervisor.py`、`agents\ticket_handler.py`、`memory\long_term.py`、`mcp\mcp_server.py`、`api\main.py`。
- DeviceCare：`atgui_agent/agent_gateway`、`atgui_agent/flow_config`、`device-service-backend/app`、`atgui_agent/README.md`、根 `启动说明.txt`。
- 岗位库：`E:\AAA message get\jobhunter\JobHunter_岗位库.xlsx`（2026-09-26 只读分析；3 条，未在本文复制 JD 原文）。
