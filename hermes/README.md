<div align="center">
  <h1>🤖 Hermes</h1>
  <p><strong>AI 编程信使系统 — 通过飞书发送消息，自动执行编程任务</strong></p>
  <p>⚡ 自主思考 · 自动执行 · 自我进化</p>
</div>

---

## ✨ 特性

| 能力 | 说明 |
|------|------|
| 📲 **飞书接入** | WebSocket 长连接，无需 ngrok，无需公网 IP |
| 🧠 **AI 驱动** | DeepSeek / OpenAI / Anthropic 任意模型 |
| 📁 **项目感知** | 自动扫描项目，自然语言匹配（"给 zsadmin 加个接口"） |
| 🛠️ **11 种内置技能** | 编程、查库、截图、搜索、Excel导出、项目分析等 |
| 🤖 **自动创能** | 无匹配技能时，AI 自动生成 Python 技能并热加载 |
| 🔄 **迭代执行** | 多轮命令 + 结果反馈 + LLM 决策下一步 |
| 🧠 **记忆系统** | SQLite 持久化，语义检索历史任务 |
| 🔌 **插件体系** | `plugins/` 目录 + `plugin.yaml` 元数据 |
| 💬 **上下文记忆** | 按用户隔离，多轮对话压缩，重启不丢失 |
| 📊 **数据库查询** | 直接查询 MySQL，自动生成 SQL，导出 Excel |
| 🖥️ **IDE 启动** | 一键启动 IntelliJ IDEA / VS Code / PyCharm |
| 📸 **截图能力** | 截图桌面 + 飞书直接发送图片 |
| 🔄 **自我进化** | 每次任务记录学习，越用越聪明 |

## 🚀 快速开始

### 1. 安装

```bash
pip install -e .
```

### 2. 配置

```bash
cp .env.example .env
# 编辑 .env 填入 API Key 和飞书配置
```

### 3. 启动

```bash
python -m src.main
```

### 4. 在飞书使用

```
你好                    → Hermes 自我介绍
给 zsadmin 加个健康检查   → 自动编程
查一下 users 表          → 数据库查询
截图我的桌面             → 截图发送
读取一下 huihuoke 项目   → 项目分析
搜索 Python 教程         → 网页搜索
导出代码统计为 Excel     → 生成表格
```

## 🏗️ 项目结构

```
hermes/
├── config/               # 配置文件
├── plugins/              # 插件目录（plugin.yaml + .py）
├── custom_skills/        # 自定义技能（自动生成也放这里）
├── src/
│   ├── main.py           # 入口
│   ├── llm/              # AI 客户端（DeepSeek/OpenAI/Anthropic）
│   ├── im_gateway/       # 飞书/微信适配器
│   ├── skills/           # 技能系统（内置技能 + 注册中心）
│   │   ├── builtin/      # 内置技能（11个）
│   │   ├── registry.py   # 技能注册/发现/热加载
│   │   └── generator.py  # AI 自动生成技能
│   ├── memory/           # 持久化记忆系统
│   ├── executor/         # 迭代执行器（多轮反馈）
│   ├── plugin/           # 插件管理器
│   ├── scanner/          # 项目扫描器
│   ├── processor/        # 意图识别 + 上下文管理
│   ├── operator/         # 系统操作（shell/IDE/DB）
│   └── evolution/        # 自进化系统
├── data/                 # 运行时数据
└── docs/                 # 设计文档
```

## 🧠 技能系统

Hermes 通过 **技能（Skill）** 来处理不同类型的任务。现有 11 个内置技能：

| 技能 | 触发关键词 | 功能 |
|------|-----------|------|
| `chat` | 兜底 | 对话、自动生成新技能 |
| `code_generation` | 写/生成/修复 | 编程任务 |
| `database_query` | 查/查询/表 | 数据库查询 + Excel导出 |
| `screenshot` | 截图/截屏/桌面 | 截图并发送 |
| `project_analysis` | 读取/分析/统计 | 项目结构分析 |
| `web_search` | 搜索/搜一下 | 网络搜索 |
| `excel_export` | excel/导出/表格 | 导出为 Excel |
| `ide_launch` | 打开/idea/vscode | 启动 IDE |
| `install_package` | 安装 | pip 安装包 |
| `plugin_hello` | 插件测试 | 插件示例 |
| `my_custom_skill` | 自定义 | 用户自定义示例 |

### 自动创能

当用户需求没有匹配的技能时，Hermes 会用 AI **自动生成并热加载**新技能：

```
你: 帮我把项目数据整理成 Word 文档
→ 没有匹配技能 → AI 生成 WordExportSkill
→ 写入 custom_skills/_auto_word_20260512.py
→ 热加载到系统 → 立即执行
```

## 🔌 插件开发

```yaml
# plugins/my_plugin/plugin.yaml
name: my_plugin
version: 1.0.0
description: 我的插件
dependencies:
  - requests
```

```python
# plugins/my_plugin/hello_skill.py
from src.skills.base import Skill, SkillContext

class HelloSkill(Skill):
    name = "hello"
    triggers = ["hello"]

    async def execute(self, ctx):
        yield "Hello from plugin!"
```

放在 `plugins/` 目录下，Hermes 启动时自动加载。

## ⚙️ 配置说明

```ini
# AI 模型（必填）
HERMES_AI_PROVIDER=openai_compatible
HERMES_AI_MODEL=deepseek-v4-flash
HERMES_AI_API_KEY=sk-xxx
HERMES_AI_BASE_URL=https://api.deepseek.com/v1

# 飞书 Bot（飞书接入时才需要）
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
```

## 🔄 与其他项目对比

| 特性 | Hermes | ClawPanel | Cursor |
|------|--------|-----------|--------|
| IM 接入 | ✅ 飞书 | ❌ 桌面应用 | ❌ IDE |
| 自生成技能 | ✅ 自动创能 | ❌ | ❌ |
| 记忆系统 | ✅ SQLite | ❌ | ❌ |
| 多模型 | ✅ DeepSeek/GPT/Claude | ✅ | ❌ |
| 项目感知 | ✅ 自动扫描 | ❌ | ✅ |
| 数据库直连 | ✅ | ❌ | ❌ |
| 插件系统 | ✅ | ❌ | ❌ |
| 价格 | 仅 API 费用 | 收费 | 收费 |

## 📝 许可证

[MIT](LICENSE)

---

<div align="center">
  <sub>Hermes — 让编程像聊天一样简单</sub>
</div>
