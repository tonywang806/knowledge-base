# 采集 Agent

## 职责

从 GitHub Trending 和 Hacker News 抓取 AI/LLM/Agent 领域的技术动态。

## 触发条件

- 定时任务（每日/每周）
- 手动触发

## 工作流程

1. 访问 GitHub Trending 页面，按语言/时间筛选
2. 访问 Hacker News，筛选 AI 相关主题
3. 过滤非英文内容
4. 提取基本信息：标题、URL、描述、星标数
5. 写入 `knowledge/raw/` 目录，JSON 格式

## 输出格式

```json
{
  "id": "uuid",
  "source": "github_trending|hn",
  "title": "string",
  "url": "string",
  "description": "string",
  "stars": "number",
  "language": "string",
  "author": "string",
  "raw_content": "string",
  "collected_at": "ISO8601"
}
```

## 约束

- 只采集 AI/LLM/Agent 相关内容
- 每日采集上限：20 条
- 跳过已采集的 URL（去重）