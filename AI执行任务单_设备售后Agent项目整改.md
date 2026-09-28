# 设备售后 Agent 项目整改与自动排查任务单

> 用途：将本文交给另一个 AI 执行。本文是执行计划，不代表下列问题仍然全部存在。执行者必须先复查当前代码和运行状态，识别用户或其他 AI 已经完成的工作，再只处理未完成项。
>
> 工作区：`F:\AAA求职相关\device_agent`
> Agent 前端及网关：`F:\AAA求职相关\device_agent\atgui_agent`
> 业务中台：`F:\AAA求职相关\device_agent\device-service-backend`
> RAG 项目：`E:\AAA message get\shopkeeper_brain`

## 执行目标

把设备售后协同智能体项目整理到一个可复现、边界清楚、能自检的状态：文档与真实代码一致；中台、前端、Agent Gateway 的启动路径正确；Agent 至少可以完成一条可测试的对话闭环；写操作有可信的服务端授权/确认边界；关键业务行为有自动化测试。

首要目标不是一次性实现完整 Agent 平台。优先恢复并验证真实启动链路，再实现最小聊天闭环。Supervisor、多 Agent、MCP、Redis、SSE 流式生成、长期记忆和生产级部署不在本轮范围内，除非盘点证明它们已经存在且只需修复。

## 架构边界

```text
Vue 工作台（5173）
  ├── /api/*    → Agent Gateway（8100）：会话、路由、任务状态、工具调用
  └── /device/* → Device Service（18082）：确定性设备/保修/工单 API
                             └── /manual/search → shopkeeper_brain RAG（8001）
```

- Agent Gateway 负责理解用户意图、管理会话状态、决定是否调用工具，以及组织回复。
- Device Service 负责设备、保修、工单、维修进度和转人工等确定性业务，不负责自然语言规划。
- RAG 项目负责文档解析、检索和引用；Agent/中台只调用其 API，不复制其内部实现。
- 任何模型输出都必须经过白名单、参数和权限校验；模型不得直接访问数据库或生成任意 SQL。
- 演示数据必须标记为合成数据。stub 结果必须显式标记为模拟/降级结果，不能伪装成真实手册引用。

## 全局约束

- 开始前和每个阶段结束时检查工作区状态；不覆盖、不回滚、不删除用户或其他 AI 的修改。
- 当前路径可能不是 Git 仓库。不要假设可以用 Git diff 判断所有改动；先检查是否存在 `.git`，并用文件状态、时间戳和内容确认现状。
- 不读取、输出、复制或写入任何 `.env` 密钥值、数据库密码、令牌或个人数据到终端日志、报告、测试快照和文档中。
- 不自动撤销云端 Key、修改远程数据库密码或清空数据库。发现疑似有效凭证时，保持本地 `.env` 原样，修复忽略规则并提醒用户自行轮换；任何外部凭证操作需用户授权。
- 不运行 `docker compose down -v`、数据库重置、递归删除或任何会清除用户数据的操作。
- 先写/更新失败测试，再实现对应行为；每项改动都有可重复验收命令。
- 依赖和目录结构尽量沿用当前项目。不要为了“架构完整”引入新的框架或重写整个项目。
- 不把计划能力描述成已实现能力。README、导师手册、架构文档、启动说明和 API 文档必须彼此一致。

## 阶段 0：自动排查与交接去重

### 目标

确认当前项目状态、识别已交接工作，并建立可审计的执行基线。此阶段只做检查和报告，不先覆盖代码。

### 操作

1. 检查项目根目录、`atgui_agent`、中台目录和 RAG 目录。分别确认 Git 状态、目录结构、入口文件、配置模板、依赖文件、测试文件和最近修改时间。
2. 搜索前端实际请求路径、Vite 代理目标、中台 API 路由、Gateway 路由、Compose 服务、启动说明中的命令。把每个“声称存在的功能”与实现逐项核实。
3. 检查正在运行的本地服务和端口（5173、8100、18082、8001），只读探测 `/health`、`/docs` 或已知健康端点；不要因端口不可用就擅自启动长期后台服务。
4. 检查 `.env` 是否被忽略、是否有 `.env.example`。只检查变量名和是否为空，不打印值。项目当前若没有 Git 元数据，明确记录“无法验证是否曾被提交”。
5. 检查现有文档、代码和其他 AI 留下的 TODO/进度说明，生成阶段状态表：`已完成且验证`、`已实现未验证`、`未实现`、`阻塞`。
6. 输出一份简短盘点结果，指出本任务单中哪些项已完成、哪些仍需做，然后继续执行未完成项，不要停下来重复询问已经明确的目标。

### 验收

- 盘点报告不含任何密钥值或敏感个人数据。
- 报告明确区分“代码存在”与“行为已运行验证”。
- 已完成任务只运行验证，不重复实现或覆盖。

## 阶段 1：先修正文档和启动结构

### 目标

让新开发者只看一份入口说明，就能按实际目录启动中台、Agent、前端，并知道 RAG 是否可选以及当前 Agent 能力边界。

### 需要核查/修改的文件

- `F:\AAA求职相关\device_agent\启动说明.txt`
- `F:\AAA求职相关\device_agent\atgui_agent\启动说明.txt`
- `F:\AAA求职相关\device_agent\atgui_agent\README.md`
- `F:\AAA求职相关\device_agent\atgui_agent\VIBE_CODING_GUIDE.md`
- `F:\AAA求职相关\device_agent\atgui_agent\docker-compose.yml`
- `F:\AAA求职相关\device_agent\atgui_agent\device-service-frontend\vite.config.js`
- `F:\AAA求职相关\device_agent\atgui_agent\agent_gateway\api\app.py`
- 中台 Dockerfile、根目录 `pyproject.toml`、SQL 初始化脚本及对应配置模板

### 必须校准的事实

- 实际中台代码位于项目根目录 `device-service-backend`，不是 `atgui_agent/device-service-backend`。
- SQL 初始化目录目前位于项目根目录 `mysql/initdb`，Compose 的相对挂载路径必须从 Compose 文件所在目录正确解析。
- Agent 包目录叫 `agent_gateway`（下划线），不是 `agent-gateway`（连字符）。
- `agent_gateway/api/app.py` 当前可能为空；先复查后再决定它是未实现还是已经被接手补齐。
- 前端代理当前把中台地址配置为固定内网 IP；改为可配置的本机默认值，避免依赖某台机器的局域网地址。
- 当前 Compose 可能只定义 MySQL 和中台，不包含 Agent Gateway；文档不得宣称 `docker compose up` 已启动聊天 Agent，除非确实增加并验证了 Gateway 服务。
- 配置加载器的 `.env` 搜索路径应与文档一致；当前项目 `.env` 在 `atgui_agent/.env`，文档不能继续错误指向 `flow_config/.env`。
- Compose 数据库初始化库名、连接串库名及 SQL 建库名必须一致。若 Gateway 状态库与业务库分离，清楚说明两个库的用途和连接方式。

### 实施要求

1. 先决定采用一种可信的启动路径：本地进程启动（复用根目录 `.venv`）或 Compose 容器启动。两者可并存，但命令和配置不能互相矛盾。
2. 让 Compose 的 `build.context`、Dockerfile、SQL bind mount 都指向真实文件；添加 MySQL healthcheck，并让依赖数据库的应用等待健康状态。不要用 `depends_on` 的启动顺序代替健康检查。
3. 配置项采用环境变量；提交安全的 `.env.example`，包含键名和无凭证占位值，不包含任何现有 `.env` 内容。
4. 根目录 `.gitignore`（如确实不存在）至少忽略 `.env`、虚拟环境、Python 缓存、前端依赖/构建产物和本地运行日志。不要删除本地 `.env`。
5. 修改 `vite.config.js` 使用可配置 API 地址；本机开发默认可访问 `127.0.0.1:18082` 和 `127.0.0.1:8100`。若项目使用 Vite 环境变量，提供相应 `.env.example` 或明确默认值。
6. README 标注功能矩阵：已实现并验证、已有代码未验证、计划中。RAG 不可用时的降级也要说明。
7. 让根目录启动说明成为唯一权威入口，子目录说明链接回根说明或保持一致，避免维护三份冲突命令。

### 验收

- 在不依赖内网 IP 的干净本机配置下，Compose 配置检查通过：

```powershell
docker compose -f F:\AAA求职相关\device_agent\atgui_agent\docker-compose.yml config --quiet
```

- 对 Compose 中所有 build、Dockerfile、volume 路径做存在性核验；若路径未挂载或构建上下文不存在，验收失败。
- 按 README 的本地启动命令可启动中台；`GET /health` 返回成功。
- 若本阶段没有实现 Agent，README 明确写“聊天 Agent 尚未实现”，不再给出一个看似可用的 Gateway 启动命令。
- 前端构建成功；API 代理目标不再包含机器专属内网地址。

## 阶段 2：实现最小可运行 Agent 闭环

### 目标

实现一个范围明确、容易测试的同步 JSON MVP：用户通过前端发消息，Gateway 读取/保存会话状态，处理保修查询，调用中台，再返回回复和工具结果。先不实现 SSE、复杂多 Agent 或通用 YAML 执行器。

### 建议的最小接口

```text
GET  /health
POST /api/chat
GET  /api/chat/history?sender_id=...
```

请求与响应字段必须与 `device-service-frontend/src/App.vue` 当前使用方式对齐；如果修改协议，前后端及 API 文档要同时更新。

### 文件责任（按当前实现调整）

- `agent_gateway/api/app.py`：FastAPI app、lifespan、路由注册和依赖装配，不写业务决策。
- 新增 `agent_gateway/api/schemas.py`：请求/响应 Pydantic 模型。
- 新增 `agent_gateway/api/routers.py`：chat、history、health HTTP 路由。
- 新增 `agent_gateway/service/dialogue_service.py`：load → process → save 的事务边界。
- 新增 `agent_gateway/engine/dialogue_engine.py` 或更小的 `stub_brain.py`：第一版确定性路由；避免引入空泛的抽象层。
- `agent_gateway/domain/state.py`、`domain/messages.py`：复用现有领域模型；如需调整序列化，补单元测试。
- `agent_gateway/infrastructure/http_client.py`：复用中台客户端调用；确保生命周期中关闭连接。
- `agent_gateway/infrastructure/database.py`：持久化会话状态/消息。先确认当前 ORM 表和 schema 与启动数据库相符。
- `device-service-frontend/src/App.vue`：仅在协议或加载/错误行为需要时调整。

### MVP 行为

- 保修查询：识别设备编号；缺编号时询问；编号格式合法后调用中台保修 API；设备不存在时给出清晰错误，不伪造结果。
- 普通知识问题：若 Agent 尚未接 RAG，明确告知知识问答还不可用或返回显式 `not_configured`；不得把中台 stub 当成真实手册答案。
- 普通闲聊/未知请求：返回确定性能力提示，不调用任意工具。
- 每条用户消息和 Agent 回复可从 history 接口读回；状态跨进程重启是否保留需依实际 DB 持久化实现验收，不得只以内存变量冒充持久化。
- 初版可以不接 LLM。若已有其他 AI 实现了 LLM 计划，保留其工作并为计划输出增加严格 schema 与白名单测试，不要为了本计划重写。

### 测试要求

- 使用 FastAPI TestClient 或 `httpx.AsyncClient` 和依赖注入替身，不要求测试连接真实 MySQL、真实 LLM 或真实 RAG。
- 覆盖正常保修查询、缺少设备编号、未知设备、工具超时/5xx、历史读取、状态持久化和未知意图。
- 第一次先运行测试确认失败，再实现最小代码使其通过。

### 验收

- Gateway `/health` 正常。
- 前端聊天发出的请求得到结构化回复，不再因为 8100 无服务而报错。
- 对保修查询可以验证真实中台工具被调用一次，返回内容来自中台响应。
- 测试能够在不启动 MySQL/LLM/RAG 的情况下运行。

## 阶段 3：补齐授权与写操作安全边界

### 目标

避免把 `confirmed=true` 当作可信授权；阻止未认证访问其他客户数据；明确演示环境与真实业务环境的安全差异。

### 处理范围

- `device-service-backend/app/config.py`
- `device-service-backend/app/app.py`
- `device-service-backend/app/api.py`
- `device-service-backend/app/schemas.py`
- 必要时更新 ORM/SQL schema 与 API 文档

### 规则

1. 先定义 MVP 身份模型。若本地演示暂不做用户登录，至少用明确的开发模式开关限制服务只监听本机，并在文档声明不可公网部署；不能声称这是生产级安全。
2. 设备、工单、历史、客户列表等读 API 必须校验资源归属。客户端提交的 `customer_id` 不能单独作为可信身份。
3. `AGENT_API_KEY` 若作为服务间认证使用，必须以请求头校验并通过常量时间比较；密钥不得写日志。它只能认证 Agent 服务，不能替代终端用户授权。
4. 写工具权限应由中台服务端校验。创建、更新、取消和转人工接口统一有明确的授权策略；对需要用户确认的操作，确认记录要绑定到用户/会话、具体动作、目标资源和待提交参数摘要，并设置短有效期。不能只相信客户端传入 `confirmed: true`。
5. 更新接口只能接受允许变更的字段和合法状态迁移；拒绝任意状态字符串跳转。
6. 将 CORS 限制到实际前端 origin；本地开发和部署配置分开。不要同时使用通配 origin 与 credentials。
7. 若无法在本轮完成可靠用户认证，则把外部写接口默认关闭或仅允许受限本地模式，清楚报告剩余风险，不能静默保留为“安全已完成”。

### 测试要求

- 未认证请求拒绝。
- 认证 Agent 仍不能读取不属于该客户的设备/工单。
- 缺少确认、过期确认、确认绑定到其他设备/动作/参数时拒绝写操作。
- 正确确认后创建工单只提交一次；取消/更新遵循允许的状态转换。
- CORS 允许指定前端 origin，拒绝未授权 origin。

## 阶段 4：数据一致性、RAG 降级与可复现测试

### 目标

修复可预期的竞态和误导性降级行为，让关键业务可用自动化测试复现。

### 工单一致性

- 将 `device-service-backend/app/api.py` 中 `count()+1` 生成工单号替换为数据库生成的唯一 ID（例如自增主键后格式化，或独立序列表），保留数据库唯一约束。
- 重复提交使用幂等键，或通过事务/约束确保同一操作只创建一个工单。
- 活动工单判断和创建必须在并发条件下安全；不能只做“先查，再插入”。
- 时间计算检查保修月数的真实日历语义。若产品定义确实为“每月 30 天”，文档说明；否则按日历月计算并测试月末/闰年边界。

### RAG 降级

- RAG 不可用时记录不含密钥和个人信息的错误摘要。
- 返回值明确带 `source=stub` 或 `degraded=true`，并在 UI/README 中区分模拟内容。
- stub 不得返回看起来来自真实 PDF 的 citation；引用列表为空或明确标记为 synthetic。
- RAG 实际返回的响应结构和错误码要按 `shopkeeper_brain` 当前 API 重新核实，不要只依赖旧文档。

### 自动化测试

- 建立明确的 pytest 测试目录和可执行命令；测试依赖放入开发依赖组/开发依赖文件，不混为生产依赖。
- 至少覆盖 API schema、保修计算、工单幂等/竞态约束、授权、Agent 工具序列、RAG 降级和历史状态。
- Mock HTTP 和数据库依赖；允许另外提供可选的 Docker 集成测试，但默认测试不能依赖远程数据库、LLM key、特定局域网 IP 或实际用户数据。
- 修正 Flow YAML 与 API 字段名不一致的问题，例如核对 `warranty_until` 与实际 `warranty_deadline`；补联系人字段收集或明确使用标记为模拟的默认值。

## 阶段 5：文档同步与最终验收

### 文档清单

- 根目录 `启动说明.txt`
- `atgui_agent/README.md`
- `atgui_agent/VIBE_CODING_GUIDE.md`
- `atgui_agent/API.md`
- `atgui_agent/docs/agent-integration.md`
- `.env.example` 与 `.gitignore`

### 最终验收命令

执行者根据实际目录修正命令，但必须提供并运行等价验证：

```powershell
docker compose -f F:\AAA求职相关\device_agent\atgui_agent\docker-compose.yml config --quiet
```

```powershell
Set-Location 'F:\AAA求职相关\device_agent'
uv run pytest -q
```

```powershell
Set-Location 'F:\AAA求职相关\device_agent\atgui_agent\device-service-frontend'
npm run build
```

还要按文档实际启动后端并验证：

```powershell
Invoke-RestMethod 'http://127.0.0.1:18082/health'
Invoke-RestMethod 'http://127.0.0.1:8100/health'
```

如果某命令因环境缺少 Docker、Node、数据库或依赖而无法运行，报告确切阻塞和已完成的替代静态检查，不得写成“验收通过”。

### 完成条件

- [ ] 启动说明中的每条命令都与真实路径匹配。
- [ ] Compose 中的构建上下文、Dockerfile、数据库挂载和环境变量已逐一验证。
- [ ] Agent 当前已实现功能、未实现功能、模拟行为在 README 明确区分。
- [ ] 未认证/越权读取和写操作确认测试通过，或明确列出未关闭的风险。
- [ ] 默认 pytest 套件无需远程服务即可运行。
- [ ] 前端生产构建通过。
- [ ] `.env` 值未在日志、文档、测试结果或最终回复中泄露。
- [ ] 最终回复列出改动文件、测试命令及结果、未完成项和用户需要手工处理的外部事项（例如轮换有效密钥）。

## 给执行 AI 的首条指令

请先按“阶段 0：自动排查与交接去重”检查当前工作区，并阅读项目现有指导文档。你可能已经与用户或其他 AI 交接过本项目：不要假设历史审查结论仍成立，也不要覆盖已完成工作。先列出已完成/未完成/无法验证项，再从最早的未完成阶段继续实施。涉及密钥、删除数据、清空卷、远程数据库或外部账号的操作不得擅自执行；需要用户操作时只提供具体、脱敏的说明。每个阶段完成后运行相应验收，并更新本任务单中的复选状态或在最终报告中逐项说明。
