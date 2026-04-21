---
name: tech-summary
description: 当需要对采集的技术内容进行深度分析总结时使用此技能
allowed-tools:
  - Read
  - Grep
  - Glob
  - WebFetch
---

# 技术内容深度分析技能

## 使用场景

对知识库中已采集的技术内容进行深度分析、提取要点、评分评级。

## 执行步骤

### 第 1 步：读取采集文件

读取 knowledge/raw/ 目录中最新采集的文件

### 第 2 步：逐条深度分析

对于每条内容，提取：
- 摘要（不超过 50 字）
- 技术亮点（2-3 个，用事实说话）
- 评分（1-10 分，附理由）
- 标签建议

### 第 3 步：趋势发现

识别共同主题、新概念、趋势

### 第 4 步：输出分析结果 JSON

路径：knowledge/raw/tech-summary-{YYYY-MM-DD}.json

## 评分标准

| 分数 | 级别 | 说明 |
|------|------|------|
| 9-10 | 改变格局 | 突破性技术，可能改变行业格局 |
| 7-8 | 直接有帮助 | 立即可用于工作 |
| 5-6 | 值得了解 | 有价值但非紧急 |
| 1-4 | 可略过 | 价值有限 |

## 约束

- 15 个项目中 9-10 分不超过 2 个
- 评分必须有事实依据，不能主观臆断
- 技术亮点必须用事实说话

## JSON 输出格式

```json
{
  "source": "tech-summary",
  "skill": "tech-summary",
  "analyzed_at": "ISO8601",
  "items": [
    {
      "title": "string",
      "url": "string",
      "summary": "string",
      "tech_highlights": ["string"],
      "relevance_score": "number",
      "score_reason": "string",
      "tags": ["string"]
    }
  ],
  "trends": ["string"]
}
```