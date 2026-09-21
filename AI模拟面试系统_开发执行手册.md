# AI 模拟面试系统开发执行手册

> **文档性质**：后续开发时使用的内部施工手册。
>
> **配套文档**：[赛题三解析与四区域项目实施指南.md](./赛题三解析与四区域项目实施指南.md) 负责解释赛题和专业名词；本文负责规定代码应该怎样一步一步完成。
>
> **目标**：在不跳步骤的前提下，完成一个可运行、可演示、可解释、可继续扩展的 AI 模拟面试系统。

## 0. 开发总规则

### 0.1 产品边界：业务上只能有四个区域

用户看到的业务区域固定为四个，不能因为新增功能再添加第五个区域：

1. **面试准备区**：简历、岗位、难度、面试配置。
2. **智能面试区**：主 AI 面试官、记忆管家、题库检索、工具和语音。
3. **评估成长区**：评分报告、图表、改进建议、知识图谱。
4. **记录交付区**：历史会话、报告详情、导出、删除和权限。

语音、题库、记忆管家、知识图谱都是这四个区域里的能力，不单独变成一个新区域。

### 0.2 技术边界：本地优先，先文字后进阶

推荐首版固定使用：

```text
前端：Vue 3
后端：FastAPI + Uvicorn
AI 编排：LangChain（只负责连接模型、记忆、检索和工具）
模型：阿里云百炼兼容接口
关系数据：SQLite
向量检索：ChromaDB
图表：ECharts
```

不使用 Docker 作为首版前置条件。先完成文字版闭环，再加入语音、工具、情绪分析和知识图谱。

### 0.3 技术目录边界

业务区域与技术目录是两个角度，不互相混淆：

```text
frontend/   # 页面和交互，内部展示四个业务区域
backend/    # HTTP/WebSocket 接口、权限、数据库访问
ai/         # 提示词、主面试官、记忆管家、检索、报告
data/       # SQLite、上传文件、向量库、导出文件
```

这四个技术目录只是代码责任边界，不代表新增业务区域。

### 0.4 不可违反的安全规则

- API 密钥只通过环境变量读取，例如 `DASHSCOPE_API_KEY`；不得写入代码、前端、Markdown 示例或 Git。
- `.env`、SQLite 文件、上传简历、ChromaDB、音频和导出文件加入 `.gitignore`。
- 所有会话查询必须校验当前用户 ID，不能只相信前端传来的会话 ID。
- 模型输出必须经过后端校验，不能直接执行模型返回的系统命令或任意 URL。
- 日志只记录请求 ID、耗时、状态和错误类型，不记录完整简历、密码、API Key 或音频原文。

## 1. 完成定义（Definition of Done）

只有同时满足以下条件，才可以说“一个阶段完成”：

- 页面能操作，不是只有后端接口或静态按钮。
- 上传、新建会话、发送回答、结束面试、删除、导出都连接真实后端。
- 数据写入 SQLite 后，刷新页面或重启后端仍然存在。
- 主 AI 的追问能引用用户当前或之前回答中的具体关键词。
- 副 AI 记忆管家能生成摘要，但原始问答仍然保留。
- 每个报告维度都有可追溯的回答轮次。
- 失败时有可理解的提示，并且不会丢失已经保存的用户回答。
- 至少完成构建检查、Python 编译检查和人工端到端场景检查。

## 2. 推荐目录和文件职责

```text
project/
├─ frontend/
│  ├─ src/
│  │  ├─ areas/
│  │  │  ├─ preparation/      # 区域一页面
│  │  │  ├─ interview/        # 区域二页面
│  │  │  ├─ growth/           # 区域三页面
│  │  │  └─ records/          # 区域四页面
│  │  ├─ api/                 # 对后端接口的封装
│  │  ├─ components/          # 可复用展示组件，不新增业务区域
│  │  └─ router/
│  ├─ package.json
│  └─ .env.example
├─ backend/
│  ├─ app/
│  │  ├─ main.py              # FastAPI 入口
│  │  ├─ routers/             # HTTP 路由
│  │  ├─ models/              # 数据库模型
│  │  ├─ schemas/             # 请求/响应 JSON 格式
│  │  ├─ services/            # 业务服务
│  │  └─ core/                # 配置、登录、日志、错误处理
│  ├─ requirements.txt
│  └─ .env.example
├─ ai/
│  ├─ interviewer.py          # 主 AI 面试官
│  ├─ secretary.py            # 副 AI 记忆管家
│  ├─ question_bank.py        # 题库导入和向量检索
│  ├─ keyword_probe.py        # 关键词提取和深入追问
│  ├─ termination.py          # 结束控制器
│  ├─ report.py               # 报告生成和校验
│  ├─ prompts/                # 提示词模板
│  └─ providers/              # 百炼、语音等外部服务适配器
├─ data/
│  ├─ uploads/                # 简历和用户文件，不提交 Git
│  ├─ chroma_db/              # 向量索引，不提交 Git
│  ├─ exports/                # PDF/Excel 临时或生成文件
│  └─ app.db                  # SQLite 数据库，不提交 Git
├─ docs/
└─ .gitignore
```

不要把模型调用散落在 Vue 组件中；不要让路由文件直接拼接复杂提示词；不要把数据库文件当成代码提交。

## 3. 核心数据模型

### 3.1 用户和准备数据

```text
users
  id, username, password_hash, created_at

resumes
  id, user_id, original_filename, storage_path,
  parsed_json, confirmed_json, parse_status, created_at, updated_at

interview_configs
  id, user_id, resume_id, target_role, difficulty,
  question_limit, time_limit_seconds, focus_skills,
  voice_enabled, status, created_at
```

`parsed_json` 是程序刚解析的草稿，`confirmed_json` 是用户检查和修改后真正用于面试的版本。

### 3.2 会话和记忆

```text
sessions
  id, user_id, config_id, status,
  current_stage, turn_count, started_at, ended_at

messages
  id, session_id, turn_no, role, content,
  question_id, citations_json, tool_calls_json, created_at

memory_summaries
  id, session_id, version, covered_turn,
  summary_json, created_at

session_topics
  id, session_id, skill, status,
  probe_depth, evidence_json, updated_at
```

`messages` 永远保存原文；`memory_summaries` 只用于帮助主 AI 快速理解上下文，不能代替原文。

### 3.3 题库、报告和操作记录

```text
question_bank
  id, question, role, skill, difficulty, question_type,
  tags_json, followups_json, rubric_json,
  reference_answer, source, embedding_status, created_at

reports
  id, session_id, version, report_json,
  generation_status, created_at

audit_logs
  id, user_id, action, target_type, target_id,
  request_id, created_at
```

题库原文和向量索引分开管理：SQLite 保存题目、标签和评分标准，ChromaDB 保存向量和检索所需的文本。

## 4. 接口契约（先定格式，再写页面）

### 4.1 健康检查和准备区

| 方法 | 路径 | 成功返回 |
|---|---|---|
| `GET` | `/api/health` | `{ "status": "ok" }` |
| `POST` | `/api/resumes/parse` | 简历解析草稿和字段状态 |
| `PUT` | `/api/resumes/{resume_id}` | 用户确认后的简历 |
| `POST` | `/api/interview-configs` | 配置 ID |
| `POST` | `/api/sessions` | 会话 ID和首问 |

### 4.1.1 账号与身份

除健康检查、题库搜索和题库向量化外，业务接口都要求请求头携带 `Authorization: Bearer <token>`。

| 方法 | 路径 | 作用 |
|---|---|---|
| `POST` | `/api/auth/register` | 创建本地账号并立即返回登录令牌 |
| `POST` | `/api/auth/login` | 校验密码并返回 JWT |
| `GET` | `/api/auth/me` | 读取当前登录用户 |

白话理解：JWT 就像后端签发的临时门票；前端每次办事都带上门票，后端据此只返回这个账号自己的数据。

### 4.2 面试区

| 方法 | 路径 | 成功返回 |
|---|---|---|
| `GET` | `/api/sessions/{session_id}` | 会话状态、摘要版本、当前阶段 |
| `GET` | `/api/sessions/{session_id}/messages` | 分页消息 |
| `POST` | `/api/sessions/{session_id}/messages` | 保存回答、下一问、结束建议 |
| `POST` | `/api/sessions/{session_id}/end` | 结束确认和报告任务状态 |
| `POST` | `/api/sessions/{session_id}/voice/transcribe` | 转写文字 |
| `POST` | `/api/sessions/{session_id}/voice/synthesize` | 音频地址或音频流 |
| `WS` | `/api/ws/sessions/{session_id}` | 进阶实时语音通信 |

`POST /messages` 的响应建议固定为：

```json
{
  "message": {
    "id": "m_12",
    "role": "assistant",
    "content": "你刚才提到使用 Redis 做缓存，具体如何处理缓存击穿？"
  },
  "citations": [],
  "tool_results": [],
  "memory": {
    "summary_version": 2,
    "compressed": true
  },
  "termination": {
    "recommend_end": false,
    "reason": null,
    "missing_topics": ["故障处理"]
  }
}
```

### 4.3 评估和记录区

| 方法 | 路径 | 作用 |
|---|---|---|
| `POST` | `/api/sessions/{session_id}/report` | 生成或重新生成报告 |
| `GET` | `/api/reports/{report_id}` | 查看结构化报告 |
| `GET` | `/api/sessions/{session_id}/report.pdf` | 导出 PDF |
| `GET` | `/api/sessions/{session_id}/report.xlsx` | 导出 Excel |
| `GET` | `/api/history` | 分页读取自己的历史 |
| `DELETE` | `/api/sessions/{session_id}` | 删除会话及其关联数据 |

接口错误统一返回：

```json
{
  "error": {
    "code": "MODEL_TIMEOUT",
    "message": "模型响应超时，请重试；你的回答已经保存。",
    "request_id": "req_20260915_001"
  }
}
```

## 5. AI 引擎执行规则

### 5.1 主 AI 面试官

主 AI 每次调用只允许输出一个自然的下一步动作：

```json
{
  "action": "ask_question",
  "question": "你刚才提到接口响应速度提升了 40%，这个数字是如何测量的？",
  "target_skill": "性能优化",
  "question_id": "performance-004",
  "reason": "用户给出了量化结果，但没有说明测量方法"
}
```

系统提示词必须包含：

- 面试官身份和目标岗位；
- 用户确认后的简历；
- 当前阶段和已覆盖技能；
- 记忆管家摘要；
- 最近 2～3 轮原始问答；
- 相关题库候选；
- 已问问题 ID，禁止重复；
- 只能问一个问题；
- 必须优先抓住用户回答中的具体技术、数字、经历或异常点；
- 不得编造用户简历内容。

主 AI 不负责决定数据库写入，也不负责直接删除会话。

### 5.2 副 AI 记忆管家

副 AI 触发条件：

```text
完成 5 轮问答
或最近上下文超过 Token 阈值
或面试主题切换
```

输入只包括：上一次摘要 + 最近 5 轮原始问答。

输出必须是结构化 JSON，至少包含：

```json
{
  "confirmed_facts": [],
  "project_details": [],
  "skills_covered": [],
  "keywords": [],
  "asked_question_ids": [],
  "unresolved_points": [],
  "score_evidence": [],
  "next_focus": ""
}
```

摘要失败时：保存错误日志，继续使用旧摘要 + 最近消息；不能阻塞用户继续面试。

建议给记忆管家使用较快、成本较低的模型。副 AI 的调用成本和耗时必须通过日志实际测量，不能假设“增加一个 AI 一定节省成本”。

### 5.3 题库检索

检索条件：

```text
target_role
+ current_stage
+ current_answer_keywords
+ difficulty
+ uncovered_skills
- asked_question_ids
```

每次只向主 AI 提供前 3～5 道候选题，不把整个题库放入提示词。

检索结果必须保存：题目 ID、来源、相似度、使用时间。这样可以检查 AI 是否真的使用了题库，而不是题库只存在于后台。

### 5.4 关键词深入追问

关键词来源可以分两层：

1. 低成本规则：技术词典、数字、百分比、框架名、数据库名和明显的模糊词。
2. 模型抽取：把回答转成关键词、事实、数字、风险点和待确认点 JSON。

每个关键词最多追问 2～3 层，追问方向按以下顺序选择：

```text
概念 → 实现 → 设计理由 → 故障/边界 → 替代方案
```

达到深度上限后必须切换到其他核心技能，避免一场面试只围绕一个词。

### 5.5 结束控制器

结束控制器由后端规则和 AI 建议共同组成。

硬规则：

- 用户点击结束或明确表达结束意愿，立即允许结束；
- 未达到最低轮数时，AI 可以提示补充，但不能阻止用户强制结束；
- 达到最大轮数或最长时间，必须进入结束流程；
- 报告只对已锁定的问答版本生成。

软规则：

- 核心技能覆盖率达到配置阈值；
- 连续两次回答没有新增信息；
- 每个评价维度已有足够证据；
- AI 建议结束且没有明显缺失主题。

推荐状态：

```text
ACTIVE
  → END_RECOMMENDED
  → WAITING_USER_CONFIRM
  → COMPLETED
  → REPORT_GENERATING
  → REPORT_READY / REPORT_FAILED
```

主 AI 只能提出 `recommend_end`，不能直接把会话写成 `COMPLETED`。

## 6. 四个业务区域的实现顺序

### 6.1 区域一：面试准备区

第一版必须完成：

- 上传 PDF/DOCX/TXT；
- 解析教育、实习、项目、技能和技术栈；
- 用户修改并确认解析结果；
- 配置岗位、难度、题数、时间和重点技能；
- 创建会话并显示第一问。

验收：换一份简历或岗位后，第一问明显变化。

### 6.2 区域二：智能面试区

第一版必须完成：

- 文字问答；
- 原始消息持久化；
- 主 AI 根据回答关键词追问；
- 记忆管家五轮摘要；
- 题库候选检索；
- 用户主动结束；
- 自动结束建议。

进阶再加入：Function Call、HTTP 语音、TTS、WebSocket 实时音频。

验收：准备两份明显不同的回答，确认下一问分别引用对应的技术、数字或项目细节；不能只看后台评分变化。

### 6.3 区域三：评估成长区

第一版必须完成：

- 总体评分；
- 专业能力、逻辑结构、表达沟通至少三个维度；
- 亮点、问题、改进建议；
- 每个维度的证据轮次；
- 前端 SVG 能力雷达图（当前实现不额外引入图表库）。

进阶再加入：文本/音频情绪辅助分析和知识图谱。

验收：修改一轮回答后重新生成报告，相关维度和证据会变化，而不是固定硬编码。

### 6.4 区域四：记录交付区

第一版必须完成：

- 历史列表；
- 报告详情；
- PDF 或 Excel 至少一种导出；
- 删除会话；
- 用户数据隔离。

验收：重启后端后仍能看到历史；用户 A 无法读取用户 B 的会话；未登录请求返回 401；错误密码不能登录。

## 7. 分阶段执行计划

### P0：项目初始化

产出：目录、环境变量模板、`/api/health`、前端入口、四区空页面、`.gitignore`。

门槛：前端能启动，后端能启动，浏览器访问根路径和健康检查都成功。

### P1：文字闭环

产出：简历确认、配置、会话、文字问答、结束按钮、SQLite 持久化。

门槛：新建 → 提问 → 回答 → 结束 → 刷新恢复，完整走通。

### P2：真实 answer-driven 面试

产出：主 AI 提示词、关键词追问、已问问题去重、至少两个不同回答的端到端验证。

门槛：下一问必须引用用户回答中的具体内容，不能只是固定模板换词。

### P3：记忆管家

产出：五轮摘要、结构化 JSON、摘要版本、失败降级、Token/耗时日志。

门槛：主 AI 不再携带全部历史，但连续 10 轮仍能保持上下文；原始消息仍完整保存。

### P4：题库和 RAG

产出：题库导入、元数据过滤、向量化、Top-k 检索、引用记录。

门槛：不同岗位/难度能取到不同候选题；已问问题不会反复出现。

### P5：报告、可视化和历史

产出：结构化报告、证据链、SVG 能力雷达图、历史列表、PDF/Excel 导出。

门槛：报告不是固定模板分数；每个分数都能回到消息轮次。

### P5.1：账号与数据隔离（已完成）

产出：SQLite `users` 表、PBKDF2 密码哈希、JWT 登录、前端 token 自动携带、会话/简历/报告按 `user_id` 过滤。

门槛：A 创建的会话不出现在 B 的历史；B 读取、下载或删除 A 的会话均失败；重启后用户和历史仍可登录读取。

### P6：浏览器语音基础版（已完成）与语音进阶

产出：智能面试区的可选浏览器语音输入、AI 问题单条朗读、自动朗读开关，以及不支持语音时的文字降级。后续再接入 HTTP 语音、服务端 TTS、WebSocket、情绪辅助和知识图谱。

门槛：语音或进阶服务失败时，文字版面试仍然可用；浏览器需要在首次使用时获得麦克风授权。

## 8. 测试和验收剧本

### 8.1 基础场景

1. 创建用户并登录。
2. 上传正常简历并确认字段。
3. 上传不可解析文件，确认有错误提示。
4. 选择岗位和难度，创建会话。
5. 连续回答至少 10 轮。
6. 刷新页面并重新读取消息。
7. 点击结束并生成报告。
8. 查看图表、证据、历史。
9. 导出文件并打开检查中文和数据。
10. 删除会话，再次访问应返回无权限或不存在。
11. 在智能面试区点击“语音输入”，确认识别文字会回填回答框且仍可编辑。
12. 点击“朗读当前问题”和单条“朗读这条”，确认可以停止朗读；打开“自动朗读”后发送回答，确认下一问自动播放。

### 8.2 answer-driven 验证

准备两条差异明显的回答：

```text
回答 A：我主要做了 Redis 缓存和接口性能优化，响应速度提升约 40%。
回答 B：我主要负责 MySQL 表结构设计和事务问题排查，没有做缓存。
```

验证：

- A 的下一问应围绕测量方法、缓存策略或性能变化；
- B 的下一问应围绕表结构、事务、索引或故障排查；
- 两者不能只返回同一条固定追问。

### 8.3 失败场景

- 模型超时：回答已经保存，可重试。
- 摘要失败：使用旧摘要和最近消息继续。
- 题库不可用：可以继续文字面试，但标注未检索到题库。
- 报告生成失败：保留面试，允许重新生成。
- 语音失败：切换到文字输入。
- 非法会话 ID：不能读取别人的数据。

### 8.4 每次改动后的固定检查

```text
1. 查看改动文件和当前运行状态
2. 使用 apply_patch 修改
3. Python compileall
4. 前端 build
5. 启动后端并检查 /api/health
6. 手工走受影响的页面流程
7. 记录成功证据和未验证内容
```

没有正式测试文件时，要明确报告“暂无自动化测试”，不能把手工验证写成单元测试通过。

## 9. 运行、配置和故障排查

### 9.1 Windows 本地运行

后端：

```powershell
cd backend
.\.venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8000
```

前端：

```powershell
cd frontend
npm run dev
```

真实运行时必须检查：进程、端口、`/api/health`、首页 HTTP 状态，而不是只看安装命令是否结束。

### 9.2 配置项

```text
DASHSCOPE_API_KEY=只存在于本机环境
MODEL_NAME=qwen-plus
DATABASE_URL=sqlite:///./data/app.db
CHROMA_DIR=./data/chroma_db
UPLOAD_DIR=./data/uploads
MAX_TURNS=15
MIN_TURNS=6
SUMMARY_EVERY_TURNS=5
```

没有 API Key 时保留 Mock 模式，让界面和数据流程仍可开发；Mock 模式也必须模拟不同回答产生不同追问，不能永远返回固定文本。

### 9.3 常见问题

- 连接被拒绝：先查后端进程和 `/api/health`，不要先修改前端地址。
- 端口占用：确认占用 PID，只停止确定是旧项目的进程，然后重新启动。
- 中文乱码：统一使用 UTF-8，PowerShell 输出必要时设置 `PYTHONIOENCODING=utf-8`。
- 百炼调用失败：检查环境变量、模型名、请求地址和响应 JSON；不要把密钥写入日志。
- 页面白屏：确认使用开发服务器访问，不要直接双击 `index.html`。

## 10. 开发决策记录规则

每完成一个阶段，在本文末尾或单独变更日志记录：

```text
日期：
阶段：
完成内容：
验证命令：
验证结果：
未验证/风险：
下一步：
```

如果后续想替换模型、数据库或语音服务，先记录原因、收益、代价和迁移影响，再改代码。不要因为一个接口暂时报错就整体更换技术路线。

## 11. 当前执行起点

当前不直接开发进阶功能，按以下顺序开始：

```text
P0 项目初始化
→ P1 文字闭环
→ P2 真实 answer-driven 追问
→ P3 记忆管家
→ P4 题库和 RAG
→ P5 报告/可视化/历史
→ P6 语音和进阶
```

下一次真正开始编码时，第一批只创建 P0 所需的目录、健康检查、环境变量模板和四个空页面；确认能启动后再进入 P1。

## 12. 变更记录（按第 10 节规则补记）

```text
日期：2026-09-21
阶段：P1/P2/P3/P4/P5 手册契约补齐
完成内容：
  - P1 数据模型补齐：resumes 增加 confirmed_json/updated_at（确认后简历才是面试用版本）；
    sessions 增加 config_id；新增 interview_configs 表与 POST /api/interview-configs；
    简历流程改为 DRAFT → 用户编辑确认（PUT /api/resumes/{id}）→ CONFIRMED。
  - P2 主 AI 结构化输出：next_question 返回 {action, question, target_skill, question_id, reason}，
    已问题目 ID 从消息与摘要两处合并去重；模型未按格式返回时降级为纯文本追问，不中断面试。
  - P3 Token/耗时日志：model_client 每次调用记录 caller、耗时毫秒、prompt/completion/total tokens，
    失败只记录错误类型；不记录任何文本内容（符合 0.4 安全规则）。
  - P4 检索使用记录：新增 question_retrievals 表（题目 ID、来源、相似度、使用时间），
    assistant 消息新增 question_id 与 citations_json 字段并返回 citations。
  - P5 状态机与统一错误：会话状态支持 ACTIVE → END_RECOMMENDED → COMPLETED
    （建议结束时用户仍可继续回答）；错误响应统一为 {error: {code, message, request_id}}。
  - 安全：新增 audit_logs 表，记录注册后的关键动作（简历解析/确认、配置创建、会话创建/结束/删除）。
  - 前端：简历确认编辑卡片、消息上的考察技能与题库引用标签、END_RECOMMENDED 提示与历史状态兼容。
验证命令：
  backend: .venv\Scripts\python.exe -m compileall app
  frontend: npm run build
  端到端：临时库启动 8001 端口冒烟脚本，18 项断言全通过
    （注册/统一 401/简历草稿/确认/空内容拒绝/配置/会话/确认简历生效/回答/结构化元数据/
     citations/消息字段/结束/报告/统一 404/用户隔离）。
  状态流：limit=8 会话 8 轮自动 COMPLETED；第 7 轮出现 END_RECOMMENDED 且可继续回答。
  数据库：audit_logs 记录 5 类动作；question_retrievals 记录向量检索来源与相似度。
验证结果：全部通过（真实百炼模型调用）。
未验证/风险：
  - PDF/Excel 导出未随本次改动重新人工核对（报告结构未变，风险低）。
  - 语音输入/朗读与新增消息标签同屏显示未在真实浏览器手工走查。
  - WAITING_USER_CONFIRM / REPORT_GENERATING / REPORT_FAILED 状态暂未启用
    （报告为同步生成，异步状态暂无必要）。
下一步：
  - P6 语音进阶（HTTP 语音、服务端 TTS、WebSocket）与 Function Call。
  - 情绪辅助分析与知识图谱（手册 6.3 进阶）。
```

```text
日期：2026-09-21
阶段：P6 进阶（6.2 Function Call、6.3 情绪辅助分析、知识图谱）+ 题库扩充
完成内容：
  - 6.3 情绪辅助分析：新增 ai/emotion.py，中文确定性信号规则（自信表述、不确定词、
    量化数据、回答长度），本地运行不消耗模型额度；每轮回答写入消息元数据，
    面试区显示情绪徽章，报告内含时间线/平均分/主导状态/趋势，PDF 增加情绪节。
  - 6.3 知识图谱：新增 ai/knowledge_graph.py，从用户回答提取技能节点（提及次数、
    证据轮次、分类），同一回答内共现构成边；报告内持久化 + 独立端点
    GET /api/sessions/{id}/knowledge-graph；前端 SVG 环形布局渲染，悬停看证据轮次。
  - 6.2 Function Call：model_client 新增 invoke_with_tools 工具循环（最多 2 轮）；
    主面试官可调用 search_question_bank 工具按自选关键词检索题库；失败自动回退
    普通调用，再失败回退规则追问，面试永不中断；metadata 记录 mode 与 tool_calls。
  - 题库扩充：种子题 6 → 30 题，覆盖 Python 后端、后端架构、AI 应用、前端、测试、
    运维、安全等岗位与基础/中等/困难三档。
验证命令：
  backend: .venv\Scripts\python.exe -m compileall app
  frontend: npm run build
  端到端：临时库 8001 端口冒烟 9 项断言全通过（题库扩充、情绪响应与元数据、
    报告含 emotion 与 knowledge_graph、重点覆盖统计、图谱端点、主 AI 模式记录）。
验证结果：全部通过（真实百炼模型调用）。
未验证/风险：
  - 情绪分为文本规则启发式，不能替代真实心理评估（已在报告与页面标注）。
  - Function Call 依赖 qwen-plus 工具调用能力；不支持时走回退路径，回退本身已验证。
  - 知识图谱为共现图，技能归类基于内置词典，冷门技术栈可能归入"其他"。
  - Excel 导出未重新人工核对（报告结构仅追加字段，风险低）。
下一步：
  - P6 语音进阶：HTTP 语音转写、服务端 TTS、WebSocket 实时音频。
  - 记忆管家建议切换更快模型并实测成本（手册 5.2 提示）。
```

```text
日期：2026-09-21
阶段：P6 语音进阶（4.2 HTTP 语音、服务端 TTS、WebSocket 通道）
完成内容：
  - ai/voice.py：qwen3-omni-flash 兼容接口实现服务端转写（≤15MB，多格式）与服务端
    语音合成（流式收集音频分片，裸 PCM 自补 WAV 头，无新增依赖）；失败统一抛
    VoiceError 转为 503，前端自动降级。
  - 接口（手册 4.2）：POST /sessions/{id}/voice/transcribe、
    POST /sessions/{id}/voice/synthesize、GET /sessions/{id}/voice/audio/{audio_id}；
    音频 ID 做路径注入校验，下载接口鉴权并校验会话归属（用户隔离）。
  - WebSocket /api/ws/sessions/{id}：握手携带 token 鉴权；transcribe 模式分片上传
    音频、stop 触发转写；speak 模式文本合成返回音频地址；失败返回 error 帧不断开。
  - 前端：语音输入双通道（浏览器识别 / 服务端识别 MediaRecorder）可切换；
    AI 朗读双引擎（浏览器 TTS / 服务端合成音频播放）可切换；服务端失败自动降级
    浏览器方案并提示；偏好持久化 localStorage。
验证命令：
  backend: .venv\Scripts\python.exe -m compileall app
  frontend: npm run build
  端到端：临时库 8001 端口冒烟 9 项断言全通过（真实调用百炼）：
    会话创建、服务端转写（正弦波正确识别"无人声"）、未授权 401、服务端合成、
    WAV 下载（校验 RIFF 头）、他人音频 404 隔离、WS speak 合成、WS 分片转写、
    WS 坏 token 被关闭。
验证结果：全部通过。
未验证/风险：
  - MediaRecorder 产出 webm/opus 交给模型转写已在接口层支持格式透传，但真实
    浏览器录音走查尚未执行（需人工麦克风测试）。
  - qwen3-omni-flash 与 qwen-plus 为不同计费模型，语音调用的 Token 成本已通过
    日志可观测，尚未做正式成本评估。
  - WebSocket 模式未启用鉴权 token 轮换；长连接未做心跳超时强制断开。
下一步：
  - 人工浏览器走查双通道语音全流程（8.1 剧本 11/12 步）。
  - 记忆管家换用更快模型实测成本与延迟（手册 5.2）。
```
