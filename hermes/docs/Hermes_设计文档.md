# Hermes — AI 编程信使系统 设计文档

## 1. 项目概述

### 1.1 背景
开发者日常面临大量编程任务：修复 Bug、添加功能、重构代码、编写测试等。这些工作通常需要打开 IDE、切换到专用工具才能执行。**Hermes** 旨在打破这一限制——通过即时通讯工具（飞书/微信）直接与 AI 编程助手对话，让编程任务像聊天一样简单。

### 1.2 名字由来
**赫尔墨斯（Hermes）** 是希腊神话中的信使神，负责传递信息与指令、引导旅人。本项目以此为名，寓意：
- **信使**：在用户与 AI 编程引擎之间传递指令与结果
- **引导**：帮助用户将模糊需求转化为可执行的编程任务
- **迅捷**：消息即达，任务即启

### 1.3 核心价值

| 维度 | 说明 |
|------|------|
| **随时随地编程** | 手机/电脑上通过聊天即可驱动代码任务 |
| **多引擎统一入口** | 一个接口同时对接 opencode 和 Claude Code |
| **异步长任务** | 大型重构/生成任务后台执行，完成后通知 |
| **自我进化** | 系统越用越聪明，指令理解、知识库、工作流、工具自供应、性能全方位优化 |

---

## 2. 总体架构

### 2.1 分层架构

```
┌──────────────────────────────────────────────────────────────┐
│                      IM Layer                                │
│  ┌───────────────────┐  ┌──────────────────────────────┐     │
│  │    飞书 Bot       │  │    微信 Bot (预留)            │     │
│  │  (lark-oapi)      │  │  (AutoWX / Wechaty)          │     │
│  └────────┬──────────┘  └──────────┬───────────────────┘     │
└───────────┼────────────────────────┼──────────────────────────┘
            │                        │
            ▼                        ▼
┌──────────────────────────────────────────────────────────────┐
│                   Message Bus Layer                          │
│  ┌──────────────────────────────────────────────────────┐    │
│  │    消息路由 & 统一消息格式                              │    │
│  │    Raw → NormalizedMessage { user, content, im }     │    │
│  └──────────────────────┬───────────────────────────────┘    │
└─────────────────────────┼────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────┐
│                   Processing Layer                           │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐    │
│  │ 指令解析器   │  │ 上下文管理器  │  │ 会话状态管理      │    │
│  │ (意图+参数)  │  │ (三级架构)   │  │ (Session Store)  │    │
│  └──────┬──────┘  └──────┬───────┘  └───────┬──────────┘    │
└─────────┼────────────────┼──────────────────┼────────────────┘
          │                │                  │
          ▼                ▼                  ▼
┌──────────────────────────────────────────────────────────────┐
│                Task Orchestration Layer                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐    │
│  │ 任务规划器    │  │ 任务队列      │  │ 进度管理器        │    │
│  │ (Plan)       │  │ (Queue/RDB)  │  │ (Progress Push)  │    │
│  └──────┬───────┘  └──────┬───────┘  └───────┬──────────┘    │
└─────────┼─────────────────┼──────────────────┼────────────────┘
          │                 │                  │
          ▼                 ▼                  ▼
┌──────────────────────────────────────────────────────────────┐
│                  Execution Engine Layer                      │
│  ┌────────────────────┐    ┌────────────────────┐            │
│  │   opencode CLI     │    │  Claude Code CLI   │            │
│  │    执行器           │    │    执行器           │            │
│  └──────┬─────────────┘    └──────┬─────────────┘            │
│         │                        │                           │
│         └────────────┬───────────┘                           │
│                      ▼                                       │
│         ┌──────────────────────────┐                         │
│         │   Sandbox Environment    │                         │
│         │   (Workspace 隔离)       │                         │
│         └──────────────────────────┘                         │
└──────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────┐
│                 Self-Evolution Layer                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐   │
│  │ 指令学习  │  │ 知识库   │  │ 工作流   │  │ 工具      │   │
│  │ Engine   │  │ VectorDB │  │ 自动生成  │  │ 自供应    │   │
│  └──────────┘  └──────────┘  └──────────┘  └───────────┘   │
│  ┌──────────┐                                                │
│  │ 性能分析  │                                                │
│  │ 闭环      │                                                │
│  └──────────┘                                                │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 核心数据流

```
用户发消息 → 飞书/微信 → IM Gateway → 统一消息格式
→ 上下文检索 (Level 3 向量库) → 指令解析 (LLM 意图识别)
→ 上下文组装 (Level1+2+3 → System Prompt)
→ 工具供应规划 (自动安装缺失的 MCP/Skill)
→ 任务规划 → 任务队列 → 执行引擎 (opencode/claude-code)
→ 结果汇总 → 上下文更新 (Level2 更新 + Level3 向量化)
→ 反馈消息 → IM Gateway → 用户收到通知
```

### 2.3 关键设计原则

1. **分层解耦**：每一层可独立替换/升级
2. **异步非阻塞**：长时间任务不阻塞消息处理
3. **幂等设计**：消息去重，避免重复执行
4. **可观测性**：全链路日志追踪，每个任务有唯一 Trace ID
5. **安全优先**：敏感操作需用户确认，沙箱隔离执行环境

---

## 3. IM 接入设计 (飞书优先)

### 3.1 飞书 Bot 接入

#### 3.1.1 技术选型
- **SDK**: `lark-oapi` (飞书官方 Python SDK)
- **运行模式**: Webhook 事件订阅 + WebSocket 长连接

#### 3.1.2 架构设计

```
飞书服务器
    │
    ├── 事件回调 (HTTP POST) ──→ Hermes Webhook Server (:9000)
    │     ├── im.message.receive_v1  (接收用户消息)
    │     └── event_callback         (飞书事件验证)
    │
    └── 主动推送 ──→ 飞书开放 API
          └── 发送消息、消息卡片、更新卡片
```

#### 3.1.3 消息处理流程

```
1. 用户向 Bot 发送消息
2. 飞书服务器调用 Hermes Webhook
3. Hermes 验证事件签名 → 解析消息 → 统一格式化
4. 送入 Message Bus → Processing Layer
5. 任务完成后，通过飞书 API 发送结果通知
```

#### 3.1.4 消息类型支持

| 类型 | 支持 | 说明 |
|------|------|------|
| 文本消息 | ✅ | 主要交互方式 |
| 图片消息 | ✅ | 截图/需求图发送 |
| 消息卡片 | ✅ | 交互式确认、进度展示 |
| 富文本 | ✅ | 代码块、结构化输出 |

### 3.2 统一 IMAdapter 接口

后续可通过 AutoWX 或 Wechaty 无缝扩展微信支持：

```python
class IMAdapter(ABC):
    @abstractmethod
    async def send_message(self, user_id: str, content: str): ...

    @abstractmethod
    async def send_card(self, user_id: str, card: Card): ...

    @abstractmethod
    async def on_message(self, handler: Callable): ...
```

---

## 4. 上下文管理体系

### 4.1 三级上下文架构

```
┌──────────────────────────────────────────────────────────────┐
│  Level 1: 短期上下文 (会话级)                                │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ 当前对话轮次 (Sliding Window, 最近 N 轮)               │  │
│  │ 消息量: ~4K tokens                                    │  │
│  │ 存储: 内存 (LRU Cache)                                │  │
│  └──────────────────────┬─────────────────────────────────┘  │
│                         │ 窗口溢出时                         │
│                         ▼                                    │
├──────────────────────────────────────────────────────────────┤
│  Level 2: 中期上下文 (任务级)                                │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ 当前任务的完整上下文                                    │  │
│  │ - 原始需求 + 所有交互轮次                               │  │
│  │ - 生成的代码 / 修改的文件                               │  │
│  │ - 执行结果与错误                                        │  │
│  │ 消息量: ~16K tokens (含摘要压缩)                       │  │
│  │ 存储: 本地文件 / SQLite                                 │  │
│  └──────────────────────┬─────────────────────────────────┘  │
│                         │ 任务完成时                         │
│                         ▼                                    │
├──────────────────────────────────────────────────────────────┤
│  Level 3: 长期上下文 (项目级 + 用户级)                      │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ 向量数据库 (ChromaDB / Qdrant)                        │  │
│  │ ┌────────────┐ ┌────────────┐ ┌──────────────────┐   │  │
│  │ │ 项目结构   │ │ 技术决策   │ │ 用户偏好 & 模式   │   │  │
│  │ │ (代码语义) │ │ (架构记录) │ │ (行为模式)       │   │  │
│  │ └────────────┘ └────────────┘ └──────────────────┘   │  │
│  │ 检索策略: Hybrid Search (Vector + Keyword)           │  │
│  │ Top-K 召回 → Re-rank → 注入 System Prompt           │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 上下文压缩策略

#### 4.2.1 多级压缩管道

```
原始消息流
    │
    ▼
┌────────────────────────────┐
│ Step 1: 去重 & 过滤         │  ← 移除系统消息、重复消息、心跳
└────────────┬───────────────┘
             │
             ▼
┌────────────────────────────┐
│ Step 2: Token 裁剪          │  ← 超出窗口上限时触发
│  策略:                     │
│  - 优先保留系统指令         │
│  - 其次保留用户最新 N 轮    │
│  - 最旧轮次 → LLM 摘要压缩  │
└────────────┬───────────────┘
             │
             ▼
┌────────────────────────────┐
│ Step 3: 语义摘要            │  ← 对"已滑出窗口"的历史
│  用 LLM 对旧对话执行：      │     生成结构化摘要
│  "用户要求: ...             │
│   已完成的步骤: ...         │
│   当前状态: ...             │
│   待办事项: ..."            │
└────────────┬───────────────┘
             │
             ▼
┌────────────────────────────┐
│ Step 4: 向量化存储          │  ← 摘要 + 关键信息 → Embedding
│  存入 Level 3 知识库        │     → VectorDB
└────────────────────────────┘
```

#### 4.2.2 压缩策略配置

```python
class ContextCompressor:
    strategies = {
        "sliding_window": SlidingWindowStrategy(window_size=20),
        "summary": SummaryCompressionStrategy(),
        "hierarchical": HierarchicalCompressionStrategy(),
        "hybrid": HybridStrategy(),
    }

    async def compress(self, context: Context, budget: int) -> CompressedContext:
        """
        budget: 目标 token 数
        1. 系统指令 (固定保留)
        2. 最近 N 轮对话 (完整保留)
        3. 中间轮次 → 摘要压缩
        4. 最旧轮次 → 仅保留摘要
        """
```

### 4.3 向量检索增强上下文

#### 4.3.1 检索流程

```
用户新指令
    │
    ▼
┌──────────────────────────────┐
│ Query Embedding              │  ← 当前问题转向量
└────────────┬─────────────────┘
             │
             ▼
┌──────────────────────────────┐
│ 向量检索 (ANN)               │  ← 从知识库中检索 Top-K
│  - 项目代码语义              │
│  - 历史任务上下文             │
│  - 用户偏好                  │
└────────────┬─────────────────┘
             │
             ▼
┌──────────────────────────────┐
│ Re-rank                      │
│  - 时间衰减权重               │
│  - 任务相关性评分             │
│  - 用户反馈信号               │
└────────────┬─────────────────┘
             │
             ▼
┌──────────────────────────────┐
│ Context Injection             │  ← 组装到 System Prompt
│ "以下是该项目的相关知识：     │
│  [检索结果]                   │
│  当前任务状态：               │
│  [Level 2 上下文]"            │
└──────────────────────────────┘
```

#### 4.3.2 检索触发时机

| 场景 | 检索范围 | Top-K |
|------|---------|-------|
| 新任务开始 | 项目结构 + 用户偏好 | 5 |
| 代码修改 | 相关文件 + 历史修改 | 3 |
| Bug 修复 | 相似 Bug 记录 + 修复方案 | 3 |
| 需求延续 | 同一任务完整上下文 | 全量 |

---

## 5. 指令系统

### 5.1 指令格式

Hermes 采用 **自然语言优先** 的指令设计，同时支持结构化命令。

#### 5.1.1 自由对话模式

```
用户: 帮我写一个 Python 函数，计算斐波那契数列
Hermes: 好的，我来生成... [执行结果]

用户: 给这个函数加上缓存机制
Hermes: 基于之前的代码，我来添加 lru_cache...
```

#### 5.1.2 快捷命令

```
/task 给 user-service 添加健康检查接口
/review src/main.py
/fix 修复登录页面的 CSRF 漏洞
/explain src/services/auth.py
```

#### 5.1.3 结构化指令

```
需求: 实现用户注册功能
技术栈: FastAPI + PostgreSQL
约束: 使用 JWT 认证
```

### 5.2 指令解析机制

```
输入文本
    │
    ▼
┌────────────────────────┐
│ LLM 意图识别            │ ← 识别：开发/审查/修复/解释/对话
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│ 参数提取                │ ← 项目路径、文件范围、技术约束
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│ 任务构建                │ ← 组装为结构化 Task 对象
└───────────┬────────────┘
            │
            ▼
       Task Queue
```

### 5.3 指令路由

| 意图 | 路由 | 说明 |
|------|------|------|
| `code_generation` | opencode | 新建代码文件/模块 |
| `code_modification` | opencode / Claude Code | 修改现有代码 |
| `code_review` | Claude Code | 审查代码质量 |
| `bug_fix` | opencode / Claude Code | 修复 Bug |
| `explain` | Claude Code | 代码解释 |
| `test_write` | opencode | 编写测试 |
| `refactor` | opencode | 重构代码 |
| `chat` | 直接 LLM | 普通对话 |

---

## 6. 执行引擎

### 6.1 统一执行器接口

```python
class ExecutionEngine(ABC):
    @abstractmethod
    async def execute(self, task: Task) -> ExecutionResult: ...

    @abstractmethod
    async def cancel(self, task_id: str): ...

    @property
    @abstractmethod
    def supported_tasks(self) -> list[TaskType]: ...
```

### 6.2 opencode 集成

```python
result = await asyncio.create_subprocess_exec(
    "opencode",
    task.instruction,
    cwd=task.workspace,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
```

配置：
```yaml
opencode:
  executable_path: "opencode"
  default_model: "deepseek-v4-flash"
  timeout: 600
  workspace: "./workspaces"
  env:
    OPENCODE_API_KEY: "${OPENCODE_API_KEY}"
```

### 6.3 Claude Code 集成

```python
result = await asyncio.create_subprocess_exec(
    "claude",
    "-p", task.instruction,
    cwd=task.workspace,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
```

配置：
```yaml
claude_code:
  executable_path: "claude"
  model: "claude-sonnet-4-20250514"
  timeout: 600
  workspace: "./workspaces"
```

### 6.4 任务生命周期

```
PENDING → QUEUED → RUNNING → COMPLETED
                      │
                      ├ → FAILED (可重试)
                      ├ → CANCELLED (用户取消)
                      └ → NEED_REVIEW (需用户确认)
```

### 6.5 沙箱与隔离

每个任务在独立的临时工作目录中执行：
- **文件隔离**：任务之间不互相干扰
- **安全执行**：限制执行权限
- **清理机制**：任务完成后可选清理工作区

---

## 7. Hermes 核心优势

### 7.1 聊天驱动的开发范式 (Chat-Driven Development)
- 告别上下文切换：飞书/微信 → 编程工具 → 飞书/微信
- 自然语言即代码：用最自然的方式表达需求
- 渐进式构建：从一句话需求开始，逐步细化

### 7.2 多平台统一入口
- 一个 Hermes 实例同时服务飞书和微信用户
- 统一的消息格式和指令系统
- 跨平台一致的交互体验

### 7.3 异步长任务支持
- 大任务后台执行，不阻塞即时通讯
- 实时进度推送（如"正在生成代码... 45%"）
- 完成通知，用户在手机上一键查看结果

### 7.4 交互式确认

```
用户: 删除 users 表中的所有测试数据
Hermes: ⚠️ 这条操作将删除 1,234 条记录，确认执行？[确认/取消]
用户: 确认
Hermes: ✅ 已删除 1,234 条测试数据
```

### 7.5 上下文记忆
- 会话内上下文保持（同一对话内的多次指令是关联的）
- 跨会话长期记忆（记住用户的代码风格偏好、常用配置）
- 项目级上下文（自动读取项目结构、技术栈信息）

---

## 8. 自我进化

Hermes 的核心竞争力——系统在持续使用中从五个维度不断自我优化。

### 8.1 指令学习与 Prompt 优化

#### 8.1.1 自动优化闭环

```
[用户原始指令] → [LLM 翻译] → [实际执行] → [结果评估]
                                                   │
                                          ┌────────┘
                                          ▼
                                   ┌──────────────┐
                                   │ Prompt 模板库  │ ← 自动优化
                                   └──────────────┘
```

- 记录每次执行的成功/失败
- 自动聚类相似指令，生成更精准的 prompt 模板
- 对频繁出现的任务类型，建立专用处理管道

#### 8.1.2 核心实现

```python
class InstructionLearner:
    def __init__(self):
        self.prompt_templates: dict[str, str] = {}
        self.execution_history: list[ExecutionRecord] = []

    async def learn_from_execution(self, record: ExecutionRecord):
        if record.success:
            self._reinforce_pattern(record)
        else:
            self._adjust_pattern(record)

    def suggest_template(self, user_input: str) -> str | None:
        return self._match_best_template(user_input)
```

### 8.2 知识库构建

#### 8.2.1 架构

```
执行结果
    │
    ▼
┌────────────────────────────┐
│  知识提取器                 │
│  - 提取关键代码片段         │
│  - 提取架构决策             │
│  - 提取问题解决方案         │
└────────────┬───────────────┘
             │
             ▼
┌────────────────────────────┐
│  向量化存储                 │
│  - Embedding → VectorDB    │
│  - 元数据索引 + 全文检索    │
└────────────┬───────────────┘
             │
             ▼
┌────────────────────────────┐
│  知识检索                   │
│  - 新任务自动检索相关历史    │
│  - 注入上下文到 prompt      │
└────────────────────────────┘
```

#### 8.2.2 存储内容

| 类型 | 说明 | 用途 |
|------|------|------|
| 代码片段 | 生成/修改的代码 | 复用模式 |
| 架构决策 | 技术选型、设计方案 | 避免重复决策 |
| 问题修复 | Bug 根因与修复方案 | 同类问题快速修复 |
| 工作流记录 | 多步骤任务流程 | 工作流自动生成 |
| 工具记忆 | 任务类型 → 所用工具链映射 | 工具自供应参考 |

### 8.3 工作流自动生成

#### 8.3.1 模式识别

```
观察：用户连续 3 次执行 "添加新 API 接口" 任务
识别模式：
  1. 创建路由文件
  2. 实现 Controller
  3. 实现 Service
  4. 实现 Repository
  5. 编写测试
生成：`create-api` 工作流模板
```

#### 8.3.2 工作流 DSL

```yaml
name: create-api
steps:
  - name: generate_controller
    engine: opencode
    prompt_template: "在 {module} 模块中创建 {name} 控制器，使用 {framework}"
  - name: generate_service
    engine: opencode
    prompt_template: "为 {name} 创建 Service 层..."
  - name: generate_test
    engine: opencode
    prompt_template: "为 {name} 编写单元测试..."
```

### 8.4 工具与环境自供应

Hermes 能够根据任务需求，**自动分析、安装、配置**所需的 MCP 服务器、Skills 和依赖工具。

#### 8.4.1 核心流程

```
任务指令
    │
    ▼
┌──────────────────────────────┐
│ 需求分析器                    │
│ "这是一个 Node.js 项目       │
│  需要代码审查 + 测试覆盖"    │
└────────────┬─────────────────┘
             │
             ▼
┌──────────────────────────────┐
│ 供应规划器                    │
│ → 需要: code-review-graph    │
│ → 需要: jest MCP server      │
│ → 需要: backend-review skill │
└────────────┬─────────────────┘
             │
             ▼
┌──────────────────────────────┐
│ 自动安装器                    │
│ 1. 检查本地是否已有          │
│ 2. 如无则自动安装            │
│ 3. 配置并启用                │
│ 4. 注入到执行上下文          │
└────────────┬─────────────────┘
             │
             ▼
┌──────────────────────────────┐
│ 执行任务                      │
└────────────┬─────────────────┘
             │
             ▼
┌──────────────────────────────┐
│ 工具记忆                      │
│ "Node.js + 审查类任务        │
│  → 自动加载 code-review      │
│    graph + backend-review"   │
└──────────────────────────────┘
```

#### 8.4.2 供应能力范围

| 类型 | 示例 | 来源 |
|------|------|------|
| **MCP Servers** | `code-review-graph`, `filesystem`, `puppeteer` | MCP 市场 / GitHub |
| **Skills** | `backend-code-review`, `graphify` | 本地注册 / 远程加载 |
| **NPM/Pip 包** | `jest`, `eslint`, `pytest` | 包管理器 |
| **CLI 工具** | `opencode`, `claude`, `gh` | 系统环境 / 自动下载 |
| **Docker 环境** | 数据库、消息队列 | Docker Hub |
| **配置文件** | `.opencode.json`, `AGENTS.md`, MCP 配置 | 模板自动生成 |

#### 8.4.3 核心实现

```python
class ToolProvisioner:
    def __init__(self):
        self.tool_registry = ToolRegistry()
        self.installed_tools = {}
        self.installation_log = []

    async def plan_for_task(self, task: Task) -> ProvisionPlan:
        requirements = await self._analyze_requirements(task)
        needed_tools = self.tool_registry.match(requirements)
        to_install = [
            t for t in needed_tools
            if not self._is_available(t)
        ]
        return ProvisionPlan(requirements=requirements, to_install=to_install)

    async def execute_plan(self, plan: ProvisionPlan):
        for tool in plan.to_install:
            match tool.type:
                case ToolType.MCP_SERVER:
                    await self._install_mcp_server(tool)
                case ToolType.SKILL:
                    await self._install_skill(tool)
                case ToolType.NPM_PACKAGE:
                    await self._install_npm(tool)
            self.installation_log.append({
                "tool": tool.name,
                "task_id": plan.task_id,
                "timestamp": now(),
                "success": True
            })
```

#### 8.4.4 MCP Server 动态管理

**运行时 MCP 配置注入：**
```json
{
  "mcpServers": {
    "code-review-graph": {
      "command": "node",
      "args": ["mcp-server-code-review-graph"]
    }
  }
}
```

**自动发现与安装流程：**
```
1. 任务需要 "代码审查 + 依赖分析"
2. 查询工具注册表 → 发现 code-review-graph MCP
3. 检查本地 → 未安装
4. npm install -g @org/mcp-server-code-review-graph
5. 动态注册到 opencode/Claude Code 配置
6. 注入 AGENTS.md 指示词
7. 执行任务
```

#### 8.4.5 Skill 动态管理

```
<workspace>/
  ├── skills/                    # Skill 仓库
  │   ├── backend-code-review/   # 后端审查技能
  │   │   └── SKILL.md
  │   └── graphify/              # 知识图谱技能
  │       └── SKILL.md
  └── AGENTS.md                  # 自动注入技能引用
```

**自动注入 AGENTS.md：**
```markdown
## 自动加载的技能
<!-- hermes-auto-generated -->
- backend-code-review: 后端代码审查
- graphify: 代码知识图谱分析
```

### 8.5 性能分析闭环

```python
class PerformanceAnalyzer:
    metrics = {
        "avg_execution_time": 0,
        "success_rate": 0.0,
        "user_satisfaction": 0.0,
        "retry_rate": 0.0,
    }

    def optimize(self):
        # 自动调整：
        # - 执行引擎选择策略（慢的引擎少用）
        # - 超时设置
        # - 重试策略
        pass
```

---

## 9. 目录结构规划

```
hermes/
├── README.md
├── pyproject.toml              # 项目配置与依赖管理
├── .env.example                # 环境变量模板
├── config/
│   ├── default.yaml            # 默认配置
│   └── production.yaml         # 生产环境配置
│
├── src/
│   ├── __init__.py
│   ├── main.py                 # 应用入口
│   │
│   ├── im_gateway/
│   │   ├── __init__.py
│   │   ├── base.py             # IMAdapter 抽象基类
│   │   ├── feishu/
│   │   │   ├── __init__.py
│   │   │   ├── adapter.py      # 飞书适配器
│   │   │   ├── card_builder.py # 消息卡片构建器
│   │   │   └── handler.py      # 事件处理器
│   │   └── wechat/
│   │       ├── __init__.py
│   │       └── adapter.py
│   │
│   ├── message_bus/
│   │   ├── __init__.py
│   │   ├── router.py           # 消息路由
│   │   ├── models.py           # 统一消息模型
│   │   └── queue.py            # 消息队列
│   │
│   ├── processor/
│   │   ├── __init__.py
│   │   ├── intent_recognizer.py  # 意图识别
│   │   ├── param_extractor.py    # 参数提取
│   │   ├── context_manager.py    # 上下文管理 (三级架构)
│   │   ├── context_compressor.py # 上下文压缩策略
│   │   ├── vector_store.py       # 向量存储检索适配
│   │   └── session_store.py      # 持久化存储
│   │
│   ├── orchestrator/
│   │   ├── __init__.py
│   │   ├── task_planner.py      # 任务规划
│   │   ├── task_queue.py        # 任务队列
│   │   ├── task_store.py        # 任务持久化
│   │   └── progress_tracker.py  # 进度跟踪
│   │
│   ├── engines/
│   │   ├── __init__.py
│   │   ├── base.py              # ExecutionEngine 抽象基类
│   │   ├── opencode_engine.py   # opencode 执行器
│   │   ├── claude_code_engine.py# Claude Code 执行器
│   │   └── sandbox.py           # 沙箱环境
│   │
│   └── evolution/
│       ├── __init__.py
│       ├── instruction_learner.py  # 指令学习引擎
│       ├── knowledge_base.py       # 知识库管理
│       ├── workflow_generator.py   # 工作流自动生成
│       ├── tool_provisioner.py     # 工具与环境自供应
│       ├── performance_analyzer.py # 性能分析
│       └── vector_store.py         # 向量存储适配
│
├── data/
│   ├── sessions/               # 会话数据
│   ├── knowledge/              # 知识库数据
│   └── workspaces/             # 任务执行工作区
│
├── tests/
│   ├── test_im_gateway/
│   ├── test_processor/
│   ├── test_orchestrator/
│   ├── test_engines/
│   └── test_evolution/
│
└── docs/
    └── Hermes_设计文档.md       # 本文档
```

---

## 10. 实现路线图

### Phase 1：核心闭环 (2-3周)

| 任务 | 说明 |
|------|------|
| 基础框架搭建 | 项目结构、配置系统、日志系统 |
| 飞书 Bot 接入 | 消息接收/发送、事件订阅 |
| 指令解析 | LLM 意图识别 + 参数提取 |
| opencode 引擎 | subprocess 调用、结果回传 |
| 任务管理 | 队列、状态、进度通知 |
| **里程碑** | ⚡ 用户可在飞书发消息 → Hermes 调用 opencode 执行 → 返回结果 |

### Phase 2：体验增强 (2-3周)

| 任务 | 说明 |
|------|------|
| Claude Code 引擎 | 双引擎支持，可配置切换 |
| 交互式卡片 | 确认/取消、进度展示、选择引擎 |
| 三级上下文 | Sliding Window + 摘要压缩 + 向量检索 |
| 指令学习基础 | 记录执行历史，模板匹配 |
| **里程碑** | 🚀 双引擎可用，上下文记忆完整 |

### Phase 3：自我进化 (3-4周)

| 任务 | 说明 |
|------|------|
| 向量知识库 | Embedding + Hybrid Search |
| 指令学习引擎 | Prompt 模板自动优化 |
| 工具自供应 | MCP/Skill 自动安装与配置 |
| 工作流自动生成 | 模式识别 → DSL 生成 |
| 性能分析闭环 | 指标采集 → 自动调优 |
| **里程碑** | 🔄 Hermes 在持续使用中越变越聪明 |

### Phase 4：生态扩展

- 微信接入支持
- 更多执行引擎（如 Cursor CLI、Copilot）
- Web 管理面板
- 团队共享知识库

---

## 11. 系统操作与数据库接入

### 11.1 IDE 启动

Hermes 能够自动检测本地安装的 IDE 并打开项目：

| 命令 | 对应 IDE | 检测方式 |
|------|----------|---------|
| `idea` | IntelliJ IDEA | PATH / 默认安装路径 |
| `code` | VS Code | PATH / 默认安装路径 |
| `pycharm` | PyCharm | PATH / 默认安装路径 |
| `webstorm` | WebStorm | PATH / 默认安装路径 |

用户只需说：
```
用 idea 打开 agent 项目
用 vscode 打开 huihuoke
```

Hermes 自动匹配项目路径 → `cmd /c "idea D:\project\agent"` → 启动 IDE。

### 11.2 数据库查询

Hermes 通过 `config/databases.yaml` 管理数据库连接，支持：

| 类型 | 驱动 | 连接方式 |
|------|------|---------|
| MySQL | `asyncmy` | host:port/user/pass |
| PostgreSQL | `asyncpg` | host:port/user/pass |
| SQLite | `aiosqlite` | 本地文件路径 |
| SQL Server | 预留 | - |

用户只需说：
```
查一下 local_mysql 的 users 表数据
看看 orders 表结构
查询最近 10 条订单记录
```

Hermes 自动解析 SQL 意图 → 连接数据库 → 执行查询 → 格式化返回结果。

**安全机制**：默认只允许 SELECT/SHOW/DESC/EXPLAIN，修改操作需显式配置。

### 11.3 系统操作

| 操作 | 示例 | 实现 |
|------|------|------|
| 打开文件 | `打开 src/main.py` | `code src/main.py` 或默认程序 |
| 运行命令 | `运行 npm install` | `subprocess`（Windows 下走 cmd.exe） |
| 打开目录 | `打开 agent 项目目录` | 资源管理器 / Finder |

---

## 12. 自升级与自配置系统

Hermes 具备 **自我进化** 的终极能力——根据需求自动安装依赖、注册 MCP 服务、配置 Skills、甚至自我重启。

### 12.1 自升级架构

```
用户说 "安装 pandas"
    │
    ▼
SelfUpgradeEngine.ensure_dependencies(["pandas"])
    │
    ├─ pip install pandas           ← 自动安装 pip 包
    ├─ 记录到 events.jsonl          ← 安装历史追踪
    └─ 返回安装结果
```

### 12.2 五种自升级能力

#### 12.2.1 依赖自动安装
```
你: 安装 asyncmy
🤖: ✅ asyncmy: installed

你: 帮我查一下数据库
🤖: asyncmy 未安装，正在自动安装... ✅ 安装完成，继续执行查询
```

#### 12.2.2 MCP Server 自动注册
```
Hermes 启动时自动检测并注册 MCP 服务到:
  - .opencode.json  → mcpServers 节点
  - %USERPROFILE%\.claude\settings.json
  - .cursor\mcp.json

支持运行时动态注册新的 MCP Server
```

#### 12.2.3 Skill 自动注册到 AGENTS.md
```markdown
<!-- hermes-auto-generated -->
- backend-code-review: 后端代码审查
- graphify: 知识图谱生成
- Task: code_modification at D:\project\agent: Auto-recorded execution result
```

#### 12.2.4 Config 热加载
```
修改 config/default.yaml 后无需重启
Hermes 支持运行时 hot-reload 配置
```

#### 12.2.5 优雅自重启
```
Hermes 检测到需要重启时:
  1. 记录重启标志到 .upgrade_state.json
  2. 完成当前任务
  3. os.execl 重新启动进程
  4. 启动时检测到升级标志 → 执行升级后初始化
```

### 12.3 使用场景

| 用户需求 | Hermes 自动行为 |
|---------|---------------|
| `查一下数据库` | 检查 `asyncmy` 是否安装 → 未安装则自动 pip install → 执行查询 |
| `审查代码` | 检查 MCP server 是否注册 → 自动注册到 `.opencode.json` |
| `帮我重构` | 检查是否有 `refactor` 相关 skill → 自动注册到 `AGENTS.md` |
| `安装 pandas` | 直接 `pip install pandas` → 记录安装历史 |
| 启动时 | 检查版本号 → 如果是新版本记录升级事件 |

---

## 13. Windows 平台兼容性

Hermes 原生支持 Windows，所有关键路径做了适配：

### 13.1 路径处理

| 场景 | 处理方式 |
|------|---------|
| 项目路径 | 使用 `pathlib.Path` 跨平台兼容 |
| 默认工作区 | 自动检测 `D:\project` 或当前目录 |
| IDE 路径 | `C:\Program Files\JetBrains\...` + `%USERPROFILE%` 动态解析 |
| 文件路径正则 | 同时匹配 `src/main.py` 和 `src\main.py` |

### 13.2 Shell 执行

```
Windows: cd /d "{project_dir}" && opencode "{instruction}"
Linux:   cd "{project_dir}" && opencode '{instruction}'
```

关键处理：
- **shlex.quote() 不可用** — Windows 的 cmd.exe 不认识单引号，改用双引号包裹并转义内部双引号
- **cd /d** — 跨盘符切换目录 (Windows 特有)
- **asyncio.create_subprocess_shell** — 使用 cmd.exe 作为 shell

### 13.3 平台检测

```python
import sys
if sys.platform == "win32":
    # Windows 特有的 cmd 调用
else:
    # POSIX 兼容
```

### 13.4 IDE 检测

自动扫描 `PATH` 环境和常见安装路径：
```
IntelliJ IDEA: C:\Program Files\JetBrains\IntelliJ IDEA*\bin\idea64.exe
VS Code:       %USERPROFILE%\AppData\Local\Programs\Microsoft VS Code\Code.exe
PyCharm:       C:\Program Files\JetBrains\PyCharm*\bin\pycharm64.exe
```

### 13.5 文件/文件夹打开

```
Windows: os.startfile(path)
macOS:   open path
Linux:   xdg-open path
```

---

## 14. 附录

### 14.1 Hermes 自身 AI 配置说明

Hermes 内部有两套 AI 体系，需要区分：

```
Hermes 自身 AI ("大脑")               执行引擎 ("双手")
─────────────────────────────────────────────────────
用途: 意图识别 / 摘要压缩             用途: 实际编程任务
      指令学习 / 工作流生成                  code generation
                                            code review
模型: 轻量 + 廉价                       模型: 由引擎决定
      gpt-4o-mini / claude-haiku              opencode → deepseek
                                               Claude Code → claude-sonnet
配置: config/default.yaml → ai:           config/default.yaml → engines:
```

**推荐配置方案：**

| 场景 | Provider | Model | 月费估算 |
|------|----------|-------|---------|
| 日常开发 | `openai` | `gpt-4o-mini` | ~$2-5 |
| 国内优先 | `openai_compatible` | 任意兼容 OpenAI 格式的模型 | 按量 |
| 隐私优先 | `anthropic` | `claude-3-haiku-20240307` | ~$3-5 |

### 14.2 核心依赖

| 包名 | 用途 |
|------|------|
| `lark-oapi` | 飞书开放平台 SDK |
| `aiohttp` / `fastapi` | Webhook 服务 |
| `openai` / `anthropic` | LLM 调用 (指令解析/摘要) |
| `chromadb` / `qdrant-client` | 向量数据库 |
| `sentence-transformers` | 文本嵌入 |
| `pyyaml` | 配置管理 |
| `pydantic` | 数据模型 |
| `sqlite` / `sqlalchemy` | 会话持久化 |

### 14.3 环境变量

```bash
# 飞书配置
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_VERIFICATION_TOKEN=xxx

# ── Hermes 自身 AI ──
# provider: openai | anthropic | openai_compatible
HERMES_AI_PROVIDER=openai
HERMES_AI_MODEL=gpt-4o-mini
HERMES_AI_API_KEY=sk-xxx
HERMES_AI_BASE_URL=          # 兼容 OpenAI 格式的第三方 API

# ── 执行引擎 ──
OPENCODE_API_KEY=sk-xxx
ANTHROPIC_API_KEY=sk-ant-xxx

# 知识库
VECTOR_DB_PATH=./data/knowledge

# Hermes 配置
HERMES_LOG_LEVEL=INFO
HERMES_WEBHOOK_PORT=9000
HERMES_DEFAULT_ENGINE=opencode
```

### 14.4 飞书配置指南

1. 在飞书开放平台创建应用
2. 开启 `im:message` 权限
3. 配置事件订阅 URL: `https://your-domain:9000/webhook/feishu`
4. 添加 Bot 能力
5. 发布并添加至群聊/好友
