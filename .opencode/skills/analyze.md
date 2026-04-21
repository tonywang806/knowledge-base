# Skill: analyze

分析采集的原始内容，生成结构化摘要和标签。

## 触发条件

- 用户请求分析
- 采集完成后自动触发

## 工作流程

1. 读取 `knowledge/raw/` 中未处理条目
2. 调用 LLM 生成摘要和标签
3. 写入 `knowledge/articles/` 目录

## 使用方法

```bash
python -m skills.analyze --status pending
```

## 输出

- 分析结果写入 `knowledge/articles/YYYY-MM-DD-*.json`
- 日志记录分析结果