"""Analyze node - LLM-powered article analyzer."""
import json
import logging
from datetime import datetime

from workflows.model_client import accumulate_usage, chat_json

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """你是一个专业的 AI 技术分析师。请根据输入的技术项目信息，生成结构化的分析结果。

要求：
1. 为每个项目生成一句中文摘要（不超过 100 字）
2. 生成 2-5 个相关标签
3. 给出 relevance_score (0.0-1.0)

输出格式（JSON 数组）：
[
  {
    "summary": "中文摘要",
    "tags": ["tag1", "tag2"],
    "relevance_score": 0.85
  }
  ]"""


def analyze_node(state):
    """用 LLM 对每条 raw item 生成中文摘要、标签、评分。"""
    print("[analyze_node] 开始分析...")

    raw_items = state["raw_items"]
    if not raw_items:
        return {"analyses": [], "articles": []}

    prompt_parts = []
    for i, item in enumerate(raw_items):
        prompt_parts.append(
            f"### 项目 {i+1}\n"
            f"名称: {item.get('title', '')}\n"
            f"描述: {item.get('description', '')}\n"
            f"链接: {item.get('source_url', '')}\n"
            f"Stars: {item.get('stars', 0)}\n"
            f"语言: {item.get('language', '')}"
        )

    prompt = "请分析以下 AI/LLM 相关项目：\n\n" + "\n\n".join(prompt_parts)

    parsed, usage = chat_json(prompt, system=SYSTEM_PROMPT, node_name="analyze")
    accumulate_usage(state["usage"], usage)

    if not isinstance(parsed, list):
        parsed = []

    analyses = []
    articles = []
    for i, meta in enumerate(parsed):
        if i >= len(raw_items):
            break
        item = raw_items[i]
        ana_id = f"github-{datetime.now().strftime('%Y%m%d')}-{i+1:03d}"
        analysis_data = {
            "id": ana_id,
            "title": item.get("title", ""),
            "source": item.get("source", "github-trending"),
            "source_url": item.get("source_url", ""),
            "collected_at": item.get("collected_at", ""),
            "summary": meta.get("summary", ""),
            "tags": meta.get("tags", []),
            "relevance_score": meta.get("relevance_score", 0.5),
        }
        analyses.append(analysis_data)
        articles.append({
            "id": ana_id,
            "title": item.get("title", ""),
            "source": item.get("source", "github-trending"),
            "source_url": item.get("source_url", ""),
            "collected_at": item.get("collected_at", ""),
            "summary": meta.get("summary", ""),
            "analysis": {
                "relevance_score": meta.get("relevance_score", 0.5),
            },
            "tags": meta.get("tags", []),
            "status": "draft",
        })

    print(f"[analyze_node] 分析完成，生成 {len(analyses)} 条")
    return {"analyses": analyses, "articles": articles}
