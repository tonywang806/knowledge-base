"""LangGraph workflow nodes for knowledge base pipeline."""
import json
import logging
import os
import urllib.request
from datetime import datetime, timezone
from typing import Any

from .model_client import accumulate_usage, chat, chat_json
from .state import KBState

logger = logging.getLogger(__name__)


def collect_node(state: KBState) -> dict:
    """采集 GitHub AI 相关仓库。"""
    from pathlib import Path
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")

    print("[collect_node] 开始采集 GitHub 仓库...")

    api_key = os.environ.get("GITHUB_TOKEN", "")
    headers = {"Accept": "application/vnd.github.v3+json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    query = "AI OR LLM OR machine-learning OR agent in:name,description,readme"
    sort = "stars"
    order = "desc"
    per_page = 20

    url = (
        f"https://api.github.com/search/repositories"
        f"?q={urllib.request.quote(query)}"
        f"&sort={sort}&order={order}&per_page={per_page}"
    )

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        logger.error(f"GitHub API 请求失败: {e}")
        return {"raw_items": []}

    items = data.get("items", [])
    raw_items = []
    for repo in items:
        raw_items.append({
            "source": "github-trending",
            "source_url": repo.get("html_url", ""),
            "title": repo.get("name", ""),
            "description": repo.get("description", ""),
            "stars": repo.get("stargazers_count", 0),
            "language": repo.get("language", ""),
            "collected_at": datetime.now(timezone.utc).isoformat(),
        })

    print(f"[collect_node] 采集完成，共 {len(raw_items)} 条")
    return {"raw_items": raw_items}


def analyze_node(state: KBState) -> dict:
    """用 LLM 对每条 raw item 生成中文摘要、标签、评分。"""
    print("[analyze_node] 开始分析...")

    system_prompt = """你是一个专业的 AI 技术分析师。请根据输入的技术项目信息，生成结构化的分析结果。

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

    raw_items = state.raw_items
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

    parsed, usage = chat_json(prompt, system=system_prompt)
    accumulate_usage(state.usage, usage)

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


def organize_node(state: KBState) -> dict:
    """过滤低分、按 URL 去重，有反馈时用 LLM 修正。"""
    print("[organize_node] 开始整理...")

    articles = state.articles
    iteration = state.iteration
    feedback = state.review_feedback

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
        system_prompt = """你是一个严谨的技术编辑。请根据审核反馈，修正文章的摘要、标签或评分。

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

        prompt = json.dumps({"feedback": feedback, "articles": filtered}, ensure_ascii=False)

        parsed, usage = chat_json(prompt, system=system_prompt)
        accumulate_usage(state.usage, usage)

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

    print(f"[organize_node] 整理完成，保留 {len(filtered)} 条")
    return {"articles": filtered}


def review_node(state: KBState) -> dict:
    """五维度审核 analyses，加权总分 >= 7.0 通过，temperature=0.1。"""
    print("[review_node] 开始审核...")

    analyses = state.analyses[:5]
    iteration = state.iteration

    WEIGHTS = {
        "summary_quality": 0.25,
        "technical_depth": 0.25,
        "relevance": 0.20,
        "originality": 0.15,
        "formatting": 0.15,
    }

    system_prompt = """你是一个专业的 AI 技术内容审核员。请对以下分析结果进行五维度评分：

1. summary_quality (摘要质量): 摘要是否清晰、准确、有信息量 (1-10)
2. technical_depth (技术深度): 技术分析是否深入、有洞察 (1-10)
3. relevance (相关性): 与 AI/LLM/Agent 领域相关程度 (1-10)
4. originality (原创性): 内容是否有独特见解 (1-10)
5. formatting (格式规范): 格式是否符合规范（中文摘要、不超过100字、适当标签）(1-10)

输出格式（严格 JSON 数组，每项对应一条分析）：
[
  {
    "summary_quality": 1-10,
    "technical_depth": 1-10,
    "relevance": 1-10,
    "originality": 1-10,
    "formatting": 1-10,
    "weighted_score": 0.0,
    "comment": "简短评语（可选）"
  }
]"""

    prompt_parts = []
    for i, ana in enumerate(analyses):
        prompt_parts.append(
            f"### 分析 {i+1}\n"
            f"标题: {ana.get('title', '')}\n"
            f"摘要: {ana.get('summary', '')}\n"
            f"标签: {', '.join(ana.get('tags', []))}\n"
            f"来源: {ana.get('source_url', '')}"
        )

    prompt = "请对以下分析结果进行评分：\n\n" + "\n\n".join(prompt_parts)

    try:
        parsed, usage = chat_json(prompt, system=system_prompt, temperature=0.2)
        accumulate_usage(state.usage, usage)
    except Exception as e:
        logger.warning(f"[review_node] LLM 调用失败，自动通过: {e}")
        return {
            "review_passed": True,
            "review_feedback": None,
            "review_result": {},
        }

    if not isinstance(parsed, list):
        parsed = []

    total_score = 0.0
    score_count = 0
    for score_entry in parsed:
        ws = sum(
            score_entry.get(dim, 5) * w
            for dim, w in WEIGHTS.items()
        )
        score_entry["weighted_score"] = ws
        total_score += ws
        score_count += 1

    avg_score = (total_score / score_count) if score_count > 0 else 0.0
    review_passed = avg_score >= 6.5
    feedback = None if review_passed else f"加权总分 {avg_score:.2f} < 6.5，请改进"

    print(f"[review_node] 审核完成，passed={review_passed}，avg={avg_score:.2f}")
    return {
        "review_passed": review_passed,
        "review_feedback": feedback,
        "review_result": {"scores": parsed, "avg_score": avg_score},
    }


def save_node(state: KBState) -> dict:
    """保存 articles 到 JSON 文件，更新 index.json。"""
    print("[save_node] 开始保存...")

    articles = state.articles
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

    print(f"[save_node] 保存完成，共 {len(saved)} 条")
    return {"saved_ids": saved}
