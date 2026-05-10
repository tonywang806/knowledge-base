"""Formatter 模块：多渠道格式化工具。

将知识条目 JSON 转换为不同平台格式：Markdown、Telegram MarkdownV2、飞书卡片。
"""

import json
from datetime import date, datetime
from pathlib import Path
from typing import TypedDict

import logging

logger = logging.getLogger(__name__)


class DigestOutput(TypedDict):
    """每日简报输出类型。"""

    markdown: str
    telegram: str
    feishu: dict


def _normalize_score(score: float) -> float:
    """将评分归一化到 0-1 范围。

    Args:
        score: 原始评分，可能是 0-1 小数、0-100 百分比或 0-10 分制。

    Returns:
        归一化后的评分（0-1）。
    """
    if score > 1:
        return min(score / 100, 1.0)
    return score


def _score_emoji(score: float) -> str:
    """根据相关性评分返回对应 emoji。

    Args:
        score: 相关性评分，范围 0-1。

    Returns:
        绿色/黄色/红色圆点 emoji。
    """
    if score >= 0.8:
        return "🟢"
    elif score >= 0.6:
        return "🟡"
    else:
        return "🔴"


def _get_source_url(article: dict) -> str:
    """获取文章源链接，兼容不同字段名。

    Args:
        article: 文章字典。

    Returns:
        源链接 URL。
    """
    return article.get("source_url") or article.get("url", "")


def _date_from_collected_at(collected_at: str) -> str:
    """从 ISO 时间字符串中提取日期部分。

    Args:
        collected_at: ISO 格式时间字符串，如 "2026-04-11T16:03:47+00:00"。

    Returns:
        仅包含日期部分的前 10 个字符，如 "2026-04-11"。
    """
    return collected_at[:10]


def _escape_telegram(text: str) -> str:
    """转义 Telegram MarkdownV2 特殊字符。

    Args:
        text: 待转义文本。

    Returns:
        转义后的文本。
    """
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    for char in escape_chars:
        text = text.replace(char, f"\\{char}")
    return text


def _feishu_header_template(score: float) -> str:
    """根据评分返回飞书卡片 header 颜色。

    Args:
        score: 相关性评分。

    Returns:
        飞书支持的颜色标识符：green / yellow / red。
    """
    if score >= 0.8:
        return "green"
    elif score >= 0.6:
        return "yellow"
    else:
        return "red"


def _load_article(file_path: Path) -> dict | None:
    """加载单个 JSON 文章文件。

    Args:
        file_path: JSON 文件路径。

    Returns:
        文章字典，解析失败返回 None。
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"加载文件失败 {file_path}: {e}")
        return None


def json_to_markdown(article: dict) -> str:
    """将单篇知识条目转换为 Markdown 格式。

    Args:
        article: 知识条目字典，字段包括 id, title, source, source_url,
            collected_at, summary, tags, analysis.relevance_score。

    Returns:
        Markdown 格式字符串。
    """
    title = article.get("title", "无标题")
    source = article.get("source", "unknown")
    source_url = _get_source_url(article)
    collected_at = article.get("collected_at", "")
    summary = article.get("summary", "")
    tags = article.get("tags", [])
    relevance = _normalize_score(article.get("analysis", {}).get("relevance_score", 0.0))

    date_str = _date_from_collected_at(collected_at)
    emoji = _score_emoji(relevance)
    tags_str = " / ".join(tags) if tags else "无"
    relevance_pct = int(relevance * 100)

    lines = [
        f"# {title}",
        "",
        f"**来源**: {source}  **日期**: {date_str}  **相关性**: {emoji} {relevance_pct}%",
        "",
        f"**标签**: {tags_str}",
        "",
        f"## 摘要",
        summary,
        "",
    ]

    if source_url:
        lines.append(f"[查看原文]({source_url})")

    return "\n".join(lines)


def _escape_url(text: str) -> str:
    """转义 URL 中的 Telegram MarkdownV2 特殊字符。

    Args:
        text: URL 字符串。

    Returns:
        转义后的 URL。
    """
    return text.replace(".", "\\.")


def json_to_telegram(article: dict) -> str:
    """将单篇知识条目转换为 Telegram MarkdownV2 格式。

    Args:
        article: 知识条目字典，字段包括 id, title, source, source_url,
            collected_at, summary, tags, analysis.relevance_score。

    Returns:
        Telegram MarkdownV2 格式字符串。
    """
    title = _escape_telegram(article.get("title", "无标题"))
    source = _escape_telegram(article.get("source", "unknown"))
    source_url = _escape_url(_get_source_url(article))
    summary = _escape_telegram(article.get("summary", ""))
    tags = article.get("tags", [])
    relevance = _normalize_score(article.get("analysis", {}).get("relevance_score", 0.0))

    emoji = _score_emoji(relevance)
    tags_str = "_".join(tags) if tags else "无"
    relevance_pct = int(relevance * 100)

    parts = [
        f"*{title}*",
        "",
        f"{emoji} *相关性*: {relevance_pct}%",
        f"📡 *来源*: {source}",
        f"🏷️ *标签*: {tags_str}",
        "",
        summary,
    ]

    if source_url:
        parts.append(f"\n[🔗 原文链接]({source_url})")

    return "\n".join(parts)


def json_to_feishu(article: dict) -> dict:
    """将单篇知识条目转换为飞书 interactive 卡片 dict。

    Args:
        article: 知识条目字典，字段包括 id, title, source, source_url,
            collected_at, summary, tags, analysis.relevance_score。

    Returns:
        飞书消息 dict，包含 msg_type=interactive 和 card 结构。
    """
    title = article.get("title", "无标题")
    source = article.get("source", "unknown")
    source_url = _get_source_url(article)
    collected_at = article.get("collected_at", "")
    summary = article.get("summary", "")
    tags = article.get("tags", [])
    relevance = _normalize_score(article.get("analysis", {}).get("relevance_score", 0.0))

    date_str = _date_from_collected_at(collected_at)
    header_color = _feishu_header_template(relevance)
    relevance_pct = int(relevance * 100)
    tags_str = " ".join(tags) if tags else "无"

    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": title[:50],
                },
                "template": header_color,
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**相关性**: {relevance_pct}%  |  **来源**: {source}  |  **日期**: {date_str}",
                    },
                },
                {
                    "tag": "hr",
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**摘要**\n{summary[:200]}",
                    },
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**标签**: {tags_str}",
                    },
                },
            ],
        },
    }

    if source_url:
        card["card"]["elements"].append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "查看原文"},
                        "type": "primary",
                        "url": source_url,
                    }
                ],
            }
        )

    return card


def generate_daily_digest(
    knowledge_dir: str = "knowledge/articles",
    date: str | None = None,
    top_n: int = 5,
) -> DigestOutput:
    """生成当日知识简报。

    Args:
        knowledge_dir: 知识库目录路径。
        date: 目标日期字符串，格式 "YYYY-MM-DD"，默认为当天。
        top_n: 最多返回条目数。

    Returns:
        包含三个渠道格式的 dict：markdown, telegram, feishu。
        当日无文章时返回提示语。
    """
    if date is None:
        target_date = datetime.now().date()
    else:
        target_date = datetime.strptime(date, "%Y-%m-%d").date()

    date_str = target_date.strftime("%Y-%m-%d")
    articles_dir = Path(knowledge_dir)

    if not articles_dir.exists():
        logger.warning(f"知识目录不存在: {articles_dir}")
        return _empty_digest(date_str)

    files = sorted(articles_dir.glob("*.json"))
    articles = []
    for f in files:
        if f.name == "index.json":
            continue
        article = _load_article(f)
        if article:
            article_date = _date_from_collected_at(article.get("collected_at", ""))
            if article_date == date_str:
                articles.append(article)

    if not articles:
        return _empty_digest(date_str)

    articles.sort(key=lambda a: a.get("analysis", {}).get("relevance_score", 0.0), reverse=True)
    top_articles = articles[:top_n]

    escaped_date = _escape_telegram(date_str)
    md_parts = [f"# 📰 {date_str} 知识简报\n", f"共收录 {len(articles)} 条，选取 Top {len(top_articles)}\n"]
    tg_parts = [f"📰 *{escaped_date} 知识简报*", f"共收录 {len(articles)} 条，选取 Top {len(top_articles)}\n"]
    feishu_elements = []

    for i, article in enumerate(top_articles, 1):
        md_parts.append(f"\n## [{i}] {json_to_markdown(article)}")
        tg_parts.append(f"\n{json_to_telegram(article)}")
        feishu_elements.append({"tag": "div", "text": {"tag": "lark_md", "content": json_to_markdown(article)}})

    feishu_card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"📰 {date_str} 知识简报"},
                "template": "blue",
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": f"共收录 {len(articles)} 条，选取 Top {len(top_articles)}"}},
                {"tag": "hr"},
            ] + feishu_elements,
        },
    }

    return DigestOutput(
        markdown="\n".join(md_parts),
        telegram="\n".join(tg_parts),
        feishu=feishu_card,
    )


def _empty_digest(date_str: str) -> DigestOutput:
    """生成空简报占位符。

    Args:
        date_str: 日期字符串。

    Returns:
        包含提示语的 DigestOutput。
    """
    empty_md = f"# 📭 {date_str} 暂无新增知识条目"
    empty_tg = f"📭 *{_escape_telegram(date_str)} 暂无新增知识条目*"
    empty_feishu = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"📭 {date_str} 暂无新增知识条目"},
                "template": "grey",
            },
            "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": "今日暂无新增知识条目"}}],
        },
    }
    return DigestOutput(markdown=empty_md, telegram=empty_tg, feishu=empty_feishu)