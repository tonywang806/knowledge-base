# 个人 AI 知识库助手

自动从 GitHub Trending、Hacker News 采集 AI/LLM/Agent 领域技术动态，AI 分析后结构化存储为 JSON，支持多渠道分发（Telegram/飞书）。

## 快速开始

```bash
# 安装依赖
uv sync

# 配置环境变量
cp config/.env.example config/.env
# 编辑 config/.env 填入 API Key
```

## 运行方式

项目提供两种运行方式：

### V1 — Python 脚本版

通过 `uv run python` 直接运行各模块，适合开发调试和 CI 集成。

```bash
# 采集（GitHub Trending + Hacker News）
uv run python -m src.agents.collector --source all --limit 10

# 分析（调用 LLM 生成摘要和标签）
uv run python -m src.agents.analyzer

# 整理 & 分发（归类 + 推送到 Telegram/飞书）
uv run python -m src.agents.organizer --platform telegram
```

也可通过 Skill 入口运行：

```bash
uv run python -m src.skills.collect --source github --limit 10
uv run python -m src.skills.analyze
uv run python -m src.skills.distribute --platform telegram
```

**参数说明：**

| 命令 | 参数 | 说明 |
|------|------|------|
| collector / collect | `--source` | 采集源：`github`、`hn`、`all`（默认） |
| collector / collect | `--limit` | 每个源最大条数（默认 10） |
| analyzer / analyze | `--source` | 源目录路径（默认 `knowledge/raw/`） |
| organizer / distribute | `--platform` | 分发平台：`telegram`、`feishu`、`none` |

### V2 — OpenCode Agent 版

通过 OpenCode 调度 Markdown 定义的 Agent/Skill，适合交互式使用和自动化工作流。

```bash
# 采集 GitHub Trending
opencode "采集 GitHub Trending 的 AI 相关项目"

# 分析已采集内容
opencode "分析 knowledge/raw/ 下待处理的内容"

# 整理并分发
opencode "整理 knowledge/articles/ 并分发到 Telegram"
```

Agent 和 Skill 的定义文件位于 `.opencode/` 目录：

| 角色 | 定义文件 | 职责 |
|------|----------|------|
| 采集 Agent | `.opencode/agents/collector.md` | 从外部源采集技术动态 |
| 分析 Agent | `.opencode/agents/analyzer.md` | 深度分析和价值评估 |
| 整理 Agent | `.opencode/agents/organizer.md` | 去重、格式化、归档、分发 |

**触发 Skill：**

| Skill | 定义文件 | 用途 |
|-------|----------|------|
| collect | `.opencode/skills/collect.md` | 触发采集流程 |
| analyze | `.opencode/skills/analyze.md` | 触发分析流程 |
| distribute | `.opencode/skills/distribute.md` | 触发分发流程 |
| github-trending | `.opencode/skills/github-trending/` | 采集 GitHub 热门项目 |
| tech-summary | `.opencode/skills/tech-summary/` | 深度技术分析总结 |

## 测试

```bash
# 运行全部测试（详细输出）
uv run pytest tests/ -v

# 运行单个测试文件
uv run pytest tests/test_validate_json.py -v

# 运行指定测试类
uv run pytest tests/test_validate_json.py::TestRequiredFields -v

# 运行指定测试用例
uv run pytest tests/test_validate_json.py::TestCheckParse::test_parse_valid_json -v
```

## 数据校验

```bash
# 校验 knowledge/articles/ 下所有 JSON 文件
uv run python hooks/validate_json.py knowledge/articles/*.json
```

## 知识条目格式

每条知识以 JSON 文件存储在 `knowledge/articles/` 目录下，ID 格式为 `{source}-{YYYYMMDD}-{NNN}`：

```json
{
  "id": "github-20260301-001",
  "title": "OpenClaw: 开源 AI Agent 运行时",
  "source": "github-trending",
  "source_url": "https://github.com/example/project",
  "collected_at": "2026-03-01T10:00:00Z",
  "summary": "一句话中文摘要（不超过 100 字）",
  "analysis": {
    "tech_highlights": ["多 Agent 路由", "50+ 平台支持"],
    "relevance_score": 9
  },
  "tags": ["agent", "runtime", "open-source"],
  "status": "draft"
}
```

**必填字段**: id, title, source_url, summary, tags, status
**status 可选值**: draft / reviewed / published / pending / archived

## 项目结构

```
personal_knowledgebase/
├── config/              # 配置（含 .env）
├── hooks/               # 校验脚本
│   └── validate_json.py
├── knowledge/
│   ├── raw/             # 采集原始数据
│   └── articles/        # 分析后的结构化文章
├── src/
│   ├── agents/          # V1: Python Agent 实现
│   │   ├── collector.py
│   │   ├── analyzer.py
│   │   └── organizer.py
│   ├── skills/          # V1: Python Skill 入口
│   │   ├── collect.py
│   │   ├── analyze.py
│   │   └── distribute.py
│   └── utils/
│       ├── logger.py
│       └── storage.py
├── .opencode/
│   ├── agents/          # V2: OpenCode Agent 定义
│   └── skills/          # V2: OpenCode Skill 定义
├── main.py              # 入口（占位）
├── pyproject.toml
└── requirements.txt
```

## 环境变量

在 `config/.env` 中配置：

| 变量 | 说明 | 必填 |
|------|------|------|
| `OPENAI_API_KEY` | LLM API Key | 是 |
| `OPENAI_BASE_URL` | LLM API 地址（默认 OpenAI） | 否 |
| `OPENAI_MODEL` | 模型名称（默认 gpt-4o-mini） | 否 |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token | 分发时必填 |
| `TELEGRAM_CHAT_ID` | Telegram Chat ID | 分发时必填 |
| `FEISHU_WEBHOOK_URL` | 飞书 Webhook URL | 分发时必填 |