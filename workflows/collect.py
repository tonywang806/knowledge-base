"""Collect node - GitHub trending repository collector."""
import json
import logging
import os
import urllib.request
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def collect_node(state):
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
