"""Analyzer Agent - analyzes content and generates summaries with tags."""
from openai import OpenAI

from config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL, RAW_DIR, ARTICLES_DIR
from utils.logger import get_logger
from utils.storage import load_json, read_pending_items, save_json, update_item_status

logger = get_logger(__name__)

DEFAULT_TAGS = ["ai", "llm", "agent", "tool", "research", "paper", "开源", "工具", "教程"]


def create_client() -> OpenAI:
    """Create OpenAI client."""
    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
    return client


def generate_summary(client: OpenAI, content: str) -> str:
    """Generate Chinese summary using LLM.

    Args:
        client: OpenAI client.
        content: Content to summarize.

    Returns:
        Generated summary in Chinese.
    """
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "你是一个专业的技术文章分析师。请用100-200字中文总结以下内容，要点包括：项目是什么、解决什么问题、有什么特点。"
                },
                {
                    "role": "user",
                    "content": content[:3000]
                }
            ],
            temperature=0.7,
            max_tokens=500
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Failed to generate summary: {e}")
        return ""


def recommend_tags(client: OpenAI, content: str) -> list[str]:
    """Recommend tags using LLM.

    Args:
        client: OpenAI client.
        content: Content to tag.

    Returns:
        List of recommended tags.
    """
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": f"从以下标签中选择2-5个最相关的：{', '.join(DEFAULT_TAGS)}。如果都不合适，可以添加新的标签。请返回JSON数组格式。"
                },
                {
                    "role": "user",
                    "content": content[:2000]
                }
            ],
            temperature=0.3,
            max_tokens=100
        )
        result = response.choices[0].message.content
        import json
        import re
        match = re.search(r'\[.*\]', result)
        if match:
            return json.loads(match.group())
    except Exception as e:
        logger.error(f"Failed to recommend tags: {e}")
    return ["ai"]


def analyze_item(client: OpenAI, item: dict) -> dict:
    """Analyze a single item.

    Args:
        client: OpenAI client.
        item: Item to analyze.

    Returns:
        Analyzed item.
    """
    content = item.get("raw_content", "")
    if not content:
        content = f"{item.get('title', '')}\n{item.get('description', '')}"

    summary = generate_summary(client, content)
    tags = recommend_tags(client, content)

    analyzed = {
        "id": item.get("id"),
        "title": item.get("title"),
        "source_url": item.get("url"),
        "summary": summary,
        "tags": tags,
        "status": "pending",
        "created_at": item.get("collected_at"),
        "updated_at": item.get("collected_at")
    }

    logger.info(f"Analyzed: {item.get('title')}")
    return analyzed


def run(source_dir = None) -> list[dict]:
    """Run analyzer.

    Args:
        source_dir: Source directory (defaults to RAW_DIR).

    Returns:
        List of analyzed items.
    """
    source_dir = source_dir or RAW_DIR

    client = create_client()
    items = read_pending_items(source_dir)

    if not items:
        logger.info("No pending items to analyze")
        return []

    analyzed_items = []
    for item in items:
        analyzed = analyze_item(client, item)
        analyzed_items.append(analyzed)
        save_json(analyzed, ARTICLES_DIR, "article-")

    logger.info(f"Analyzed {len(analyzed_items)} items")
    return analyzed_items


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Analyze collected content")
    parser.add_argument("--source", default=None, help="Source directory")
    args = parser.parse_args()

    run(args.source)