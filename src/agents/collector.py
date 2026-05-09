"""Collector Agent - fetches AI content from GitHub Trending and Hacker News."""
import requests
from bs4 import BeautifulSoup

from config import RAW_DIR
from tests.security import sanitize_input
from utils.logger import get_logger
from utils.storage import generate_id, get_timestamp, save_json

logger = get_logger(__name__)

GITHUB_TRENDING_URL = "https://github.com/trending?since=weekly"
HN_API_URL = "https://hacker-news.firebaseio.com/v0"
AI_KEYWORDS = ["ai", "llm", "agent", "gpt", "chatgpt", "openai", "claude", "gemini", "langchain", "rag", "embedding", "vector"]


def is_ai_related(title: str, description: str = "") -> bool:
    """Check if content is AI-related.

    Args:
        title: Item title.
        description: Item description.

    Returns:
        True if AI-related.
    """
    text = f"{title} {description}".lower()
    return any(keyword in text for keyword in AI_KEYWORDS)


def fetch_github_trending(limit: int = 10) -> list[dict]:
    """Fetch GitHub Trending repositories.

    Args:
        limit: Maximum number of items.

    Returns:
        List of repositories.
    """
    items = []
    try:
        response = requests.get(GITHUB_TRENDING_URL, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")

        for article in soup.select("article Box-row")[:limit]:
            title_elem = article.select_one("a")
            if not title_elem:
                continue

            title = title_elem.get_text(strip=True)
            url = "https://github.com" + title_elem.get("href", "")
            description = article.select_one("p").get_text(strip=True) if article.select_one("p") else ""
            stars = article.select_one("a[href$='stargazers']").get_text(strip=True) if article.select_one("a[href$='stargazers']") else "0"
            language = article.select_one("span[itemprop='programmingLanguage']").get_text(strip=True) if article.select_one("span[itemprop='programmingLanguage']") else ""

            if is_ai_related(title, description):
                items.append({
                    "id": generate_id(),
                    "source": "github_trending",
                    "title": title,
                    "url": url,
                    "description": description,
                    "stars": stars,
                    "language": language,
                    "raw_content": f"{title}\n{description}",
                    "status": "pending",
                    "collected_at": get_timestamp()
                })
                logger.info(f"Collected GitHub: {title}")

    except Exception as e:
        logger.error(f"Failed to fetch GitHub Trending: {e}")

    return items


def fetch_hacker_news(limit: int = 10) -> list[dict]:
    """Fetch Hacker News AI-related items.

    Args:
        limit: Maximum number of items.

    Returns:
        List of items.
    """
    items = []
    try:
        response = requests.get(f"{HN_API_URL}/topstories.json", timeout=30)
        response.raise_for_status()
        story_ids = response.json()[:100]

        for story_id in story_ids[:limit * 3]:
            story_response = requests.get(f"{HN_API_URL}/item/{story_id}.json", timeout=10)
            if story_response.status_code != 200:
                continue

            story = story_response.json()
            if not story or not story.get("title"):
                continue

            if is_ai_related(story.get("title", ""), story.get("text", "")):
                items.append({
                    "id": generate_id(),
                    "source": "hn",
                    "title": story.get("title"),
                    "url": story.get("url", f"https://news.ycombinator.com/item?id={story_id}"),
                    "description": story.get("text", "")[:500],
                    "stars": str(story.get("score", 0)),
                    "author": story.get("by", ""),
                    "raw_content": f"{story.get('title')}\n{story.get('text', '')}",
                    "status": "pending",
                    "collected_at": get_timestamp()
                })
                logger.info(f"Collected HN: {story.get('title')}")

                if len(items) >= limit:
                    break

    except Exception as e:
        logger.error(f"Failed to fetch Hacker News: {e}")

    return items


def collect_github(limit: int = 10) -> list[dict]:
    """Collect from GitHub Trending.

    Args:
        limit: Maximum number of items.

    Returns:
        List of collected items.
    """
    items = fetch_github_trending(limit)
    for item in items:
        save_json(item, RAW_DIR, "raw-")
    logger.info(f"Collected {len(items)} items from GitHub")
    return items


def collect_hn(limit: int = 10) -> list[dict]:
    """Collect from Hacker News.

    Args:
        limit: Maximum number of items.

    Returns:
        List of collected items.
    """
    items = fetch_hacker_news(limit)
    for item in items:
        save_json(item, RAW_DIR, "raw-")
    logger.info(f"Collected {len(items)} items from HN")
    return items


def run(source: str = "github,hn", limit: int = 10) -> list[dict]:
    """Run collector.

    Args:
        source: Source to collect from (github,hn or all).
        limit: Maximum number of items per source.

    Returns:
        List of collected items.
    """
    all_items = []
    sources = [s.strip() for s in source.split(",")]

    if "github" in sources or "all" in sources:
        all_items.extend(collect_github(limit))

    if "hn" in sources or "all" in sources:
        all_items.extend(collect_hn(limit))

    total_warnings = 0
    cleaned_items = []
    for item in all_items:
        for field in ("title", "description"):
            if field in item and isinstance(item[field], str):
                cleaned, warnings = sanitize_input(item[field])
                item[field] = cleaned
                total_warnings += len(warnings)
                if warnings:
                    logger.warning(f"[Security] {item.get('url', '?')} {field} 检出注入模式：{warnings}")
        cleaned_items.append(item)

    if total_warnings > 0:
        logger.warning(f"[Security] collect 阶段共拦截 {total_warnings} 处可疑输入")

    logger.info(f"Total collected: {len(cleaned_items)} items")
    return cleaned_items


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Collect AI content from GitHub and HN")
    parser.add_argument("--source", default="all", help="Source: github,hn or all")
    parser.add_argument("--limit", type=int, default=10, help="Maximum items per source")
    args = parser.parse_args()

    run(args.source, args.limit)