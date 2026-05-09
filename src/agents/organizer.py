"""Organizer Agent - organizes and distributes knowledge articles."""
import re
from pathlib import Path

import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, FEISHU_WEBHOOK_URL, ARTICLES_DIR
from tests.security import filter_output
from utils.logger import get_logger
from utils.storage import load_json, read_pending_items, save_json, update_item_status, list_files

logger = get_logger(__name__)

TAG_CATEGORIES = {
    "ai": "ai",
    "llm": "llm",
    "agent": "agent",
    "gpt": "llm",
    "chatgpt": "llm",
    "openai": "llm",
    "claude": "llm",
    "gemini": "llm",
    "langchain": "agent",
    "rag": "ai",
    "tool": "tool",
    "开源": "tool",
    "research": "research",
    "paper": "research",
    "教程": "tutorial",
}


def categorize_by_tags(tags: list[str]) -> str:
    """Categorize article by tags.

    Args:
        tags: List of tags.

    Returns:
        Category directory name.
    """
    for tag in tags:
        if tag.lower() in TAG_CATEGORIES:
            return TAG_CATEGORIES[tag.lower()]
    return "other"


def format_message(item: dict) -> str:
    """Format article as message.

    Args:
        item: Article to format.

    Returns:
        Formatted message.
    """
    title = item.get("title", "")
    summary = item.get("summary", "")
    tags = ", ".join(item.get("tags", []))
    url = item.get("source_url", "")

    return f"""📖 {title}

{summary}

🏷️ {tags}
🔗 {url}"""


def send_telegram(message: str) -> bool:
    """Send message to Telegram.

    Args:
        message: Message to send.

    Returns:
        True if successful.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram not configured")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        response = requests.post(url, json=data, timeout=30)
        response.raise_for_status()
        logger.info("Telegram message sent")
        return True
    except Exception as e:
        logger.error(f"Failed to send Telegram: {e}")
        return False


def send_feishu(message: str) -> bool:
    """Send message to Feishu webhook.

    Args:
        message: Message to send.

    Returns:
        True if successful.
    """
    if not FEISHU_WEBHOOK_URL:
        logger.warning("Feishu not configured")
        return False

    data = {"msg_type": "text", "content": {"text": message}}

    try:
        response = requests.post(FEISHU_WEBHOOK_URL, json=data, timeout=30)
        response.raise_for_status()
        logger.info("Feishu message sent")
        return True
    except Exception as e:
        logger.error(f"Failed to send Feishu: {e}")
        return False


def distribute_article(item: dict, platform: str = "telegram") -> bool:
    """Distribute article to platform.

    Args:
        item: Article to distribute.
        platform: Platform (telegram or feishu).

    Returns:
        True if successful.
    """
    message = format_message(item)

    if platform == "telegram":
        return send_telegram(message)
    elif platform == "feishu":
        return send_feishu(message)
    else:
        logger.error(f"Unknown platform: {platform}")
        return False


def organize_article(item: dict) -> dict:
    """Organize a single article.

    Args:
        item: Article to organize.

    Returns:
        Organized article.
    """
    category = categorize_by_tags(item.get("tags", []))
    item["category"] = category

    status = "published"
    item["status"] = status

    logger.info(f"Organized: {item.get('title')} -> {category}")
    return item


def run(platform: str = "telegram") -> list[dict]:
    """Run organizer.

    Args:
        platform: Distribution platform.

    Returns:
        List of organized articles.
    """
    items = read_pending_items(ARTICLES_DIR)

    if not items:
        logger.info("No pending articles to organize")
        return []

    organized = []
    total_pii = 0
    for item in items:
        organized_item = organize_article(item)

        for field in ("summary", "content", "title"):
            if field in organized_item and isinstance(organized_item[field], str):
                filtered, detections = filter_output(organized_item[field], mask=True)
                organized_item[field] = filtered
                total_pii += len(detections)
                if detections:
                    logger.warning(f"[Security] {organized_item.get('id', '?')} {field} 掩码 PII：{detections}")

        organized.append(organized_item)

        if platform:
            distribute_article(organized_item, platform)
        else:
            save_json(organized_item, ARTICLES_DIR)

    if total_pii > 0:
        logger.warning(f"[Security] organize 阶段共掩码 {total_pii} 处 PII")

    logger.info(f"Organized {len(organized)} articles")
    return organized


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Organize and distribute articles")
    parser.add_argument("--platform", default="telegram", help="Platform: telegram, feishu, or none")
    args = parser.parse_args()

    run(args.platform)