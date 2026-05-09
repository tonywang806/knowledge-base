"""Organize node - filter, deduplicate and persist articles."""
import json
import logging
import os
from datetime import datetime, timezone

from workflows.model_client import accumulate_usage, chat_json

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个严谨的技术编辑。请根据审核反馈，修正文章的摘要、标签或评分。

输入格式（JSON）：
{
  "feedback": "审核反馈内容",
  "articles": [...]  // 文章列表
}

输出格式（JSON 数组，每项包含 id, summary, tags, relevance_score）：
[
  {
    "id": "原 ID",
    "summary": "修正后的摘要",
    "tags": ["修正后的标签"],
    "relevance_score": 修正后的评分
  }
]"""


def _save_articles(articles):
    base_dir = os.environ.get("KB_ARTICLES_DIR", "knowledge/articles")
    os.makedirs(base_dir, exist_ok=True)

    index_path = os.path.join(base_dir, "index.json")
    index_data = {}
    if os.path.exists(index_path):
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                index_data = json.load(f)
        except Exception:
            index_data = {}

    saved = []
    for item in articles:
        aid = item.get("id", "")
        if not aid:
            continue
        item_path = os.path.join(base_dir, f"{aid}.json")
        with open(item_path, "w", encoding="utf-8") as f:
            json.dump(item, f, ensure_ascii=False, indent=2)
        index_data[aid] = {
            "title": item.get("title", ""),
            "source_url": item.get("source_url", ""),
            "status": item.get("status", "draft"),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        saved.append(aid)

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)
    return saved


def organize_node(state):
    """过滤低分、按 URL 去重，有反馈时用 LLM 修正，最后持久化。"""
    print("[organize_node] 开始整理...")

    articles = state["articles"]
    iteration = state["iteration"]
    feedback = state["review_feedback"]

    filtered = []
    seen_urls = set()
    for item in articles:
        score = item.get("analysis", {}).get("relevance_score", 0.5)
        if score < 0.6:
            continue
        url = item.get("source_url", "")
        if url and url in seen_urls:
            continue
        seen_urls.add(url)
        filtered.append(item)

    if iteration > 0 and feedback:
        prompt = json.dumps({"feedback": feedback, "articles": filtered}, ensure_ascii=False)
        parsed, usage = chat_json(prompt, system=SYSTEM_PROMPT, node_name="organize")
        accumulate_usage(state["usage"], usage)

        if isinstance(parsed, list):
            meta_map = {m["id"]: m for m in parsed}
            for item in filtered:
                mid = item.get("id", "")
                if mid in meta_map:
                    m = meta_map[mid]
                    item["summary"] = m.get("summary", item.get("summary", ""))
                    item["tags"] = m.get("tags", item.get("tags", []))
                    item["analysis"]["relevance_score"] = m.get(
                        "relevance_score",
                        item.get("analysis", {}).get("relevance_score", 0.5),
                    )

    saved = _save_articles(filtered)
    print(f"[organize_node] 整理完成，保留 {len(filtered)} 条，保存 {len(saved)} 条")
    return {"articles": filtered, "saved_ids": saved}
