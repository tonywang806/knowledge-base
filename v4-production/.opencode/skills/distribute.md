# Skill: distribute

将知识条目分发到 Telegram 或飞书。

## 触发条件

- 用户请求分发
- 整理完成后自动触发

## 工作流程

1. 读取 `knowledge/articles/` 中待分发条目
2. 格式化消息内容
3. 调用对应平台 API 发送
4. 记录分发结果

## 配置项

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
FEISHU_WEBHOOK_URL=
```

## 使用方法

```bash
python -m skills.distribute --platform telegram --id <article_id>
python -m skills.distribute --platform feishu --id <article_id>
```

## 输出

- 消息发送成功/失败
- 分发日志