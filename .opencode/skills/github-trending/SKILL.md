---
name: github-trending
description: 当需要采集 GitHub 热门开源项目时使用此技能。适用于知识库采集阶段。
allowed-tools:
  - Read
  - Grep
  - Glob
  - WebFetch
---

# GitHub 热门项目采集技能

## 使用场景

在知识库采集阶段，从 GitHub 搜索并采集 AI 领域热门开源项目。

## 执行步骤

### 第 1 步：搜索热门仓库

GET https://api.github.com/search/repositories?q=created:>{7天前日期}+stars:>100&sort=stars&order=desc&per_page=30

### 第 2 步：提取仓库信息

提取 name, full_name, html_url, description, stargazers_count, language, topics

### 第 3 步：过滤

纳入：AI/ML/LLM/Agent 相关、开发者工具、框架重大更新
排除：Awesome 列表、纯教程、Star 刷量、无 README

### 第 4 步：去重

按 full_name 去重，只保留一条

### 第 5 步：撰写中文摘要

公式：[项目名] + 做什么 + 为什么值得关注

### 第 6 步：排序取 Top 15

按 Star 数降序排列

### 第 7 步：输出 JSON

路径：knowledge/raw/github-trending-{YYYY-MM-DD}.json

## JSON 输出格式

```json
{
  "source": "github-trending",
  "skill": "github-trending",
  "collected_at": "ISO8601",
  "items": [
    {
      "name": "string",
      "url": "string",
      "summary": "string",
      "stars": "number",
      "language": "string",
      "topics": ["string"]
    }
  ]
}
```

## 注意事项

- GitHub API 未认证限频 10 次/分钟
- 摘要必须是中文
- 不编造不存在的仓库