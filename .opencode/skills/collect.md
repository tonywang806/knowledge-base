# Skill: collect

从 GitHub Trending 和 Hacker News 采集 AI 相关内容。

## 触发条件

- 用户请求采集
- 定时任务

## 工作流程

1. 调用 GitHub API 获取 Trending 仓库
2. 访问 HN API 获取最新帖子，过滤 AI 相关
3. 去重检查（对比现有 URL）
4. 写入 `knowledge/raw/` 目录

## 使用方法

```bash
python -m agents.collect --source github,hn --limit 20
```

## 输出

- 新增条目写入 `knowledge/raw/{source}-{YYYYMMDD}-{NNN}.json`
- 日志记录采集结果