# 整理 Agent

## 职责

对分析后的内容进行归类存储，并触发分发流程。

## 触发条件

- 分析 Agent 完成
- 手动触发

## 工作流程

1. 读取 `knowledge/articles/` 中 status=pending 的条目
2. 按标签归类到对应目录
3. 更新 status=published
4. 触发分发（如果配置了 Telegram/飞书）
5. 记录分发日志

## 目录结构

```
knowledge/articles/
├── ai/           # AI 基础
├── llm/           # 大语言模型
├── agent/         # Agent 相关
└── other/         # 其他
```

## 分发配置

- Telegram：需要 bot_token 和 chat_id
- 飞书：需要 webhook URL
- 分发开关可配置

## 约束

- 禁止直接修改 knowledge/raw/ 目录
- 分发失败自动重试 3 次
- 保留分发历史记录