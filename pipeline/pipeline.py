"""知识库自动化流水线。

四步流水线：采集 -> 分析 -> 整理 -> 保存
"""
import argparse
import logging
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from pipeline.model_client import tracker

import httpx
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from model_client import chat_with_retry

BASE_DIR = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
RAW_DIR = KNOWLEDGE_DIR / "raw"
ARTICLES_DIR = KNOWLEDGE_DIR / "articles"

RAW_DIR.mkdir(parents=True, exist_ok=True)
ARTICLES_DIR.mkdir(parents=True, exist_ok=True)

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
RSS_SOURCES_FILE = Path(__file__).resolve().parent / "rss_sources.yaml"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

AI_KEYWORDS = [
    "ai", "llm", "agent", "gpt", "chatgpt", "openai", "claude",
    "gemini", "langchain", "rag", "embedding", "vector", "diffusion",
    "neural", "transformer", "gemma", "mistral",
]


def is_ai_related(title: str, description: str = "") -> bool:
    """Check if content is AI-related."""
    text = f"{title} {description}".lower()
    return any(kw in text for kw in AI_KEYWORDS)


def _build_github_query() -> str:
    """Build GitHub search query (limited keywords for API compatibility)."""
    keywords = ["ai", "llm", "agent", "gpt", "openai", "claude"]
    return " ".join(keywords)


def generate_id() -> str:
    """Generate unique ID with source prefix."""
    return str(uuid.uuid4())


def get_timestamp() -> str:
    """Get current ISO timestamp."""
    return datetime.now().isoformat()


def build_fallback_summary(item: dict) -> str:
    """Build a validation-safe summary when LLM analysis is unavailable."""
    title = item.get("title", "") or "该项目"
    description = item.get("description", "") or item.get("raw_content", "") or "暂无详细描述"
    description = re.sub(r"\s+", " ", description).strip()
    summary = f"{title}：{description[:80]}"
    if len(summary) < 20:
        summary += "，需要人工复核其技术价值和适用场景"
    return summary[:100]


def fetch_github(
    limit: int = 10,
    github_token: Optional[str] = None,
    dry_run: bool = False,
) -> list[dict]:
    """Fetch AI-related repos from GitHub Search API.

    Args:
        limit: Max items to fetch.
        github_token: GitHub API token (optional).
        dry_run: If True, skip HTTP requests.

    Returns:
        List of raw items.
    """
    items = []
    headers = {"Accept": "application/vnd.github.v3+json"}
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    query = _build_github_query()
    params = {"q": query, "sort": "stars", "order": "desc", "per_page": min(limit * 2, 100)}

    if dry_run:
        logger.info(f"[DRY RUN] GitHub search: query='{query}', limit={limit}")
        return items

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(GITHUB_SEARCH_URL, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

        for repo in data.get("items", [])[:limit]:
            if not is_ai_related(repo.get("name", ""), repo.get("description", "")):
                continue
            items.append({
                "id": generate_id(),
                "source": "github-search",
                "title": repo.get("name", ""),
                "url": repo.get("html_url", ""),
                "description": repo.get("description", "") or "",
                "stars": str(repo.get("stargazers_count", 0)),
                "language": repo.get("language", "") or "",
                "raw_content": f"{repo.get('name')}\n{repo.get('description', '')}",
                "status": "pending",
                "collected_at": get_timestamp(),
            })
            logger.info(f"[GitHub] {repo.get('name')} ⭐{repo.get('stargazers_count', 0)}")

    except httpx.HTTPStatusError as e:
        logger.error(f"GitHub API error: {e.response.status_code} {e.response.text[:200]}")
    except Exception as e:
        logger.error(f"GitHub fetch error: {e}")

    return items


def _parse_rss_xml(xml_text: str) -> list[dict]:
    """Parse RSS XML with regex (simple implementation).

    Args:
        xml_text: Raw XML content.

    Returns:
        List of parsed items.
    """
    items = []
    item_pattern = re.compile(r"<item>(.*?)</item>", re.DOTALL | re.IGNORECASE)
    title_pattern = re.compile(r"<title>(.*?)</title>", re.DOTALL | re.IGNORECASE)
    link_pattern = re.compile(r"<link>(.*?)</link>", re.DOTALL | re.IGNORECASE)
    desc_pattern = re.compile(r"<description>(.*?)</description>", re.DOTALL | re.IGNORECASE)

    for item_match in item_pattern.finditer(xml_text):
        item_xml = item_match.group(1)
        title = (title_pattern.search(item_xml) or re.compile(r"<title>(.*?)</title>", re.IGNORECASE).search(item_xml) or type("", (), {"group": lambda s, x: ""})()).group(1) or ""
        link = (link_pattern.search(item_xml) or re.compile(r"<link>(.*?)</link>", re.IGNORECASE).search(item_xml) or type("", (), {"group": lambda s, x: ""})()).group(1) or ""
        description = (desc_pattern.search(item_xml) or re.compile(r"<description>(.*?)</description>", re.IGNORECASE).search(item_xml) or type("", (), {"group": lambda s, x: ""})()).group(1) or ""

        title = re.sub(r"<[^>]+>", "", title).strip()
        description = re.sub(r"<[^>]+>", "", description).strip()
        link = link.strip()

        if title:
            items.append({"title": title, "link": link, "description": description})

    return items


def fetch_rss(
    limit: int = 10,
    dry_run: bool = False,
) -> list[dict]:
    """Fetch AI-related items from RSS sources.

    Args:
        limit: Max items per source.
        dry_run: If True, skip HTTP requests.

    Returns:
        List of raw items.
    """
    if not RSS_SOURCES_FILE.exists():
        logger.warning(f"RSS config not found: {RSS_SOURCES_FILE}")
        return []

    with open(RSS_SOURCES_FILE, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    sources = [s for s in config.get("sources", []) if s.get("enabled", False)]
    if not sources:
        logger.warning("No RSS sources enabled")
        return []

    all_items = []

    for source in sources:
        name = source.get("name", "")
        url = source.get("url", "")
        category = source.get("category", "")

        if dry_run:
            logger.info(f"[DRY RUN] RSS: {name} ({url})")
            continue

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(url)
                response.raise_for_status()

            parsed = _parse_rss_xml(response.text)
            for item in parsed[:limit]:
                if not is_ai_related(item.get("title", ""), item.get("description", "")):
                    continue
                all_items.append({
                    "id": generate_id(),
                    "source": f"rss-{source.get('name', '').lower().replace(' ', '-')}",
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "description": item.get("description", "")[:500],
                    "raw_content": f"{item.get('title')}\n{item.get('description', '')}",
                    "status": "pending",
                    "collected_at": get_timestamp(),
                })
                logger.info(f"[RSS] {item.get('title')[:60]}")

        except httpx.HTTPStatusError as e:
            logger.error(f"RSS error [{name}]: HTTP {e.response.status_code}")
        except Exception as e:
            logger.error(f"RSS error [{name}]: {e}")

    return all_items


def save_raw(items: list[dict]) -> int:
    """Save raw items to knowledge/raw/.

    Args:
        items: Items to save.

    Returns:
        Number of items saved.
    """
    count = 0
    for item in items:
        timestamp = datetime.now().strftime("%Y%m%d")
        filename = f"raw-{timestamp}-{item['id'][:8]}.json"
        filepath = RAW_DIR / filename
        with open(filepath, "w", encoding="utf-8") as f:
            import json
            json.dump(item, f, ensure_ascii=False, indent=2)
        count += 1
    return count


def step_collect(
    sources: list[str],
    limit: int,
    dry_run: bool = False,
) -> list[dict]:
    """Step 1: Collect content from sources.

    Args:
        sources: Source list (github, rss).
        limit: Max items per source.
        dry_run: Dry run mode.

    Returns:
        Collected items.
    """
    logger.info(f"=== Step 1: Collect (sources={sources}, limit={limit}, dry={dry_run}) ===")

    items = []
    github_token = None

    if "github" in sources:
        items.extend(fetch_github(limit, github_token, dry_run))

    if "rss" in sources:
        items.extend(fetch_rss(limit, dry_run))

    saved = 0
    if not dry_run and items:
        saved = save_raw(items)
        logger.info(f"Saved {saved} raw items to {RAW_DIR}")

    logger.info(f"Collect complete: {len(items)} items, {saved} saved")
    return items


def step_analyze(items: list[dict], dry_run: bool = False) -> list[dict]:
    """Step 2: Analyze items with LLM.

    Args:
        items: Raw items.
        dry_run: Dry run mode.

    Returns:
        Analyzed items.
    """
    logger.info(f"=== Step 2: Analyze ({len(items)} items, dry={dry_run}) ===")

    analyzed = []
    for item in items:
        content = item.get("raw_content", "")
        if not content:
            content = f"{item.get('title', '')}\n{item.get('description', '')}"

        if dry_run:
            logger.info(f"[DRY RUN] Analyze: {item.get('title', '')[:50]}")
            analyzed.append({**item, "summary": "[dry-run summary]", "tags": ["dry-run"], "analysis": {"relevance_score": 0}})
            continue

        try:
            messages = [
                {
                    "role": "system",
                    "content": "你是一个专业的技术文章分析师。请分析以下内容，生成中文摘要（20-100字，必须至少20字），推荐2-5个标签，返回JSON格式：{\"summary\": \"...\", \"tags\": [...], \"relevance_score\": <1-10整数>}。9-10改变格局，7-8直接有帮助，5-6值得了解，1-4价值有限。摘要必须足够详细，至少20字。",
                },
                {
                    "role": "user",
                    "content": content[:3000],
                },
            ]
            response = chat_with_retry(messages)

            import json
            import re
            result_text = response.content.strip()
            match = re.search(r"\{.*\}", result_text, re.DOTALL)
            if match:
                result = json.loads(match.group())
            else:
                result = json.loads(result_text)

            summary = result.get("summary", "")
            if len(summary) < 20:
                summary = build_fallback_summary(item)

            analyzed_item = {
                "id": item.get("id"),
                "title": item.get("title"),
                "source": item.get("source"),
                "source_url": item.get("url"),
                "summary": summary,
                "tags": result.get("tags", ["ai"]),
                "analysis": {
                    "relevance_score": result.get("relevance_score", 5),
                },
                "status": "draft",
                "collected_at": item.get("collected_at"),
            }
            analyzed.append(analyzed_item)
            logger.info(f"Analyzed: {item.get('title', '')[:50]} (score={result.get('relevance_score', '?')})")

        except Exception as e:
            logger.error(f"Analyze failed for {item.get('title', '')}: {e}")
            analyzed.append({
                "id": item.get("id"),
                "title": item.get("title"),
                "source": item.get("source"),
                "source_url": item.get("url"),
                "summary": build_fallback_summary(item),
                "tags": ["ai"],
                "analysis": {"relevance_score": 3},
                "status": "draft",
                "collected_at": item.get("collected_at"),
            })

    return analyzed


def step_organize(items: list[dict], dry_run: bool = False) -> list[dict]:
    """Step 3: Deduplicate and standardize.

    Args:
        items: Analyzed items.
        dry_run: Dry run mode.

    Returns:
        Organized items.
    """
    logger.info(f"=== Step 3: Organize ({len(items)} items, dry={dry_run}) ===")

    seen_urls: set[str] = set()
    organized = []

    for item in items:
        url = item.get("source_url", "")
        title = item.get("title", "")

        if url and url in seen_urls:
            logger.info(f"Duplicate skipped: {title[:50]}")
            continue

        if url:
            seen_urls.add(url)

        item["status"] = "review"

        if dry_run:
            logger.info(f"[DRY RUN] Organize: {title[:50]}")
        else:
            logger.info(f"Organized: {title[:50]}")

        organized.append(item)

    logger.info(f"Organize complete: {len(organized)} unique items (removed {len(items) - len(organized)} duplicates)")
    return organized


def step_save(items: list[dict], dry_run: bool = False) -> int:
    """Step 4: Save articles to knowledge/articles/.

    Args:
        items: Organized items.
        dry_run: Dry run mode.

    Returns:
        Number of items saved.
    """
    logger.info(f"=== Step 4: Save ({len(items)} items, dry={dry_run}) ===")

    timestamp = datetime.now().strftime("%Y%m%d")
    count = 0
    for idx, item in enumerate(items, start=1):
        source_prefix = item.get("source", "unknown").split("-")[0]
        new_id = f"{source_prefix}-{timestamp}-{idx:03d}"
        item["id"] = new_id
        filename = f"{new_id}.json"
        filepath = ARTICLES_DIR / filename

        if dry_run:
            logger.info(f"[DRY RUN] Save: {filepath}")
            count += 1
            continue

        with open(filepath, "w", encoding="utf-8") as f:
            import json
            json.dump(item, f, ensure_ascii=False, indent=2)
        count += 1
        logger.info(f"Saved: {filepath.name}")

    logger.info(f"Save complete: {count} articles to {ARTICLES_DIR}")
    return count


def run(
    sources: list[str],
    limit: int,
    dry_run: bool = False,
    verbose: bool = False,
    steps: list[int] | None = None,
) -> None:
    """Run the pipeline (optionally subset of steps).

    Args:
        sources: Source list.
        limit: Max items per source.
        dry_run: Dry run mode.
        verbose: Verbose logging.
        steps: List of step numbers to run (1-4). If None, runs all.
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if steps is None:
        steps = [1, 2, 3, 4]

    logger.info(f"Running steps: {steps}")

    items = []
    analyzed = []
    organized = []
    saved = 0

    if 1 in steps:
        items = step_collect(sources, limit, dry_run)
        if not items and not dry_run:
            logger.warning("No items collected, stopping pipeline")
            return

    if 2 in steps:
        if not items and not dry_run:
            logger.warning("No items to analyze, skipping step 2")
        else:
            analyzed = step_analyze(items, dry_run) if items else []
            if not analyzed and not dry_run:
                logger.warning("No items analyzed, skipping remaining steps")
                return

    if 3 in steps:
        if not analyzed and not dry_run:
            logger.warning("No items to organize, skipping step 3")
        else:
            organized = step_organize(analyzed, dry_run) if analyzed else []

    if 4 in steps:
        if not organized and not dry_run:
            logger.warning("No items to save, skipping step 4")
        else:
            saved = step_save(organized, dry_run) if organized else 0

    logger.info(f"=== Pipeline complete: {saved} articles saved ===")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="AI知识库自动化流水线：采集->分析->整理->保存",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  python pipeline/pipeline.py --sources github,rss --limit 20   # 完整流水线
  python pipeline/pipeline.py --sources github --limit 5      # 只采集GitHub
  python pipeline/pipeline.py --sources rss --limit 10        # 只采集RSS
  python pipeline/pipeline.py --sources github --limit 5 --dry-run  # 干跑模式
  python pipeline/pipeline.py --verbose                        # 详细日志""",
    )
    parser.add_argument(
        "--sources",
        default="github,rss",
        help="数据源，逗号分隔 (github,rss)，默认: github,rss",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="每个源最大采集数量，默认: 10",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="干跑模式：不发HTTP请求，不写文件",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="详细日志",
    )
    parser.add_argument(
        "--step",
        action="append",
        type=int,
        choices=[1, 2, 3, 4],
        help="指定要运行的步骤（可多次使用，如 --step 1 --step 2）",
    )
    args = parser.parse_args()

    sources = [s.strip() for s in args.sources.split(",")]
    steps = args.step if args.step else None

    run(sources, args.limit, args.dry_run, args.verbose, steps)
    tracker.report()


if __name__ == "__main__":
    main()