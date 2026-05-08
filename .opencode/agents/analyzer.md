# 分析 Agent

## 职责

处理采集的原始内容，提取关键信息、生成摘要、建议标签。

## 触发条件

- 采集 Agent 完成
- 手动触发

## 工作流程

1. 读取 `knowledge/raw/` 中 status=pending 的条目
2. 访问 source_url 获取完整内容（可选）
3. 生成中文摘要（100-200 字）
4. 建议标签：领域、主题、技术栈
5. 更新 JSON 写入 `knowledge/articles/`

## 输出格式

```json
{
  "id": "{source}-{YYYYMMDD}-{NNN}",
  "title": "string",
  "source_url": "string",
  "summary": "string",
  "tags": ["ai", "llm", "agent"],
  "status": "pending|published|archived",
  "created_at": "ISO8601",
  "updated_at": "ISO8601"
}
```

## 约束

- 摘要使用中文
- 标签数量：2-5 个
- 只处理 status=pending 的条目
