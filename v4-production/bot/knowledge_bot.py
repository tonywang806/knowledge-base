"""知识库交互模块。

提供知识搜索、订阅管理、权限控制等功能。
"""

import json
import logging
import os
import re
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Intent(Enum):
    """意图类型枚举。"""

    SEARCH = "search"
    TODAY = "today"
    TOP = "top"
    BROWSE_TOP = "browse_top"
    SUBSCRIBE = "subscribe"
    HELP = "help"
    BROWSE_TODAY = "browse_today"
    UNKNOWN = "unknown"


class Permission(Enum):
    """权限级别枚举。"""

    READ = "read"
    WRITE = "write"
    DELETE = "delete"


def format_search_results(results: list[dict], query: str = "") -> str:
    """格式化搜索结果。

    Args:
        results: 搜索结果列表。
        query: 查询关键词。

    Returns:
        格式化的结果文本。
    """
    if not results:
        return "未找到匹配的知识条目。"

    lines = [f"🔍 搜索「{query}」找到 {len(results)} 条结果：\n"]
    for i, article in enumerate(results, 1):
        title = article.get("title", "无标题")
        summary = article.get("summary", "无摘要")
        tags = article.get("tags", [])
        url = article.get("source_url", "")
        score = article.get("analysis", {}).get("relevance_score", 0)
        lines.append(f"{i}. {title}")
        lines.append(f"   {summary}")
        if tags:
            lines.append(f"   🏷️ {', '.join(tags)}")
        if score:
            lines.append(f"   ⭐ {score}")
        if url:
            lines.append(f"   🔗 {url}")
        lines.append("")

    return "\n".join(lines)


class KnowledgeSearchEngine:
    """搜索引擎，支持关键词、标签、日期范围过滤。"""

    def __init__(self, articles_dir: str):
        """初始化搜索引擎。

        Args:
            articles_dir: 知识库文章目录路径。
        """
        self.articles_dir = Path(articles_dir)
        self._cache = []
        self._cache_time = None

    def _load_articles(self) -> list[dict]:
        """加载所有文章。"""
        now = datetime.now()
        if self._cache and self._cache_time:
            cache_age = (now - self._cache_time).total_seconds()
            if cache_age < 300:
                return self._cache

        articles = []
        if not self.articles_dir.exists():
            logger.warning(f"Articles directory does not exist: {self.articles_dir}")
            return articles

        for json_file in self.articles_dir.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    articles.append(json.load(f))
            except Exception as e:
                logger.error(f"Failed to load {json_file}: {e}")

        self._cache = articles
        self._cache_time = now
        return articles

    def search(
        self,
        keywords: Optional[list[str]] = None,
        keyword: Optional[str] = None,
        tags: Optional[list[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 10,
    ) -> list[dict]:
        """搜索知识库。

        Args:
            keywords: 关键词列表。
            keyword: 单一关键词（keywords 的别名）。
            tags: 标签列表。
            start_date: 开始日期。
            end_date: 结束日期。
            limit: 返回结果数量限制。

        Returns:
            匹配的文章列表。
        """
        if keyword and not keywords:
            keywords = [keyword]
        articles = self._load_articles()
        results = []

        for article in articles:
            if keywords:
                title = article.get("title", "").lower()
                summary = article.get("summary", "").lower()
                matched = any(kw.lower() in title or kw.lower() in summary for kw in keywords)
                if not matched:
                    continue

            if tags:
                article_tags = article.get("tags", [])
                if not any(tag in article_tags for tag in tags):
                    continue

            if start_date or end_date:
                collected_at_str = article.get("collected_at", "")
                try:
                    collected_at = datetime.fromisoformat(collected_at_str.replace("Z", "+00:00"))
                    if start_date and collected_at < start_date:
                        continue
                    if end_date and collected_at > end_date:
                        continue
                except (ValueError, TypeError):
                    continue

            results.append(article)

        results.sort(
            key=lambda x: x.get("analysis", {}).get("relevance_score", 0),
            reverse=True,
        )
        return results[:limit]

    def get_today(self, limit: int = 10) -> list[dict]:
        """获取今天的知识条目。

        Args:
            limit: 返回结果数量限制。

        Returns:
            今天的文章列表。
        """
        articles = self._load_articles()
        today = datetime.now().date()
        results = []

        for article in articles:
            collected_at_str = article.get("collected_at", "")
            try:
                collected_at = datetime.fromisoformat(collected_at_str.replace("Z", "+00:00"))
                if collected_at.date() == today:
                    results.append(article)
            except (ValueError, TypeError):
                continue

        return results[:limit]

    def get_top(self, limit: int = 10) -> list[dict]:
        """获取热门知识条目（按相关性排序）。

        Args:
            limit: 返回结果数量限制。

        Returns:
            按相关性分数排序的文章列表。
        """
        articles = self._load_articles()
        scored = []
        for article in articles:
            score = article.get("analysis", {}).get("relevance_score", 0)
            scored.append((score, article))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [article for _, article in scored[:limit]]


class SubscriptionManager:
    """用户订阅管理。"""

    def __init__(self, data_file: Optional[str] = None):
        """初始化订阅管理器。

        Args:
            data_file: 订阅数据存储文件路径。
        """
        if data_file:
            self.data_file = Path(data_file)
        else:
            self.data_file = Path(__file__).parent / "subscriptions.json"
        self._subscriptions: dict[str, list[str]] = {}
        self._load()

    def _load(self) -> None:
        """加载订阅数据。"""
        if self.data_file.exists():
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    self._subscriptions = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load subscriptions: {e}")
                self._subscriptions = {}

    def _save(self) -> None:
        """保存订阅数据。"""
        try:
            self.data_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(self._subscriptions, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save subscriptions: {e}")

    def add(self, user_id: str, tags: list[str]) -> bool:
        """添加订阅。

        Args:
            user_id: 用户 ID。
            tags: 标签列表。

        Returns:
            是否成功。
        """
        if user_id not in self._subscriptions:
            self._subscriptions[user_id] = []
        for tag in tags:
            if tag not in self._subscriptions[user_id]:
                self._subscriptions[user_id].append(tag)
        self._save()
        return True

    def remove(self, user_id: str, tags: Optional[list[str]] = None) -> bool:
        """删除订阅。

        Args:
            user_id: 用户 ID。
            tags: 要删除的标签列表，None 表示删除所有订阅。

        Returns:
            是否成功。
        """
        if user_id not in self._subscriptions:
            return False
        if tags is None:
            self._subscriptions[user_id] = []
        else:
            for tag in tags:
                if tag in self._subscriptions[user_id]:
                    self._subscriptions[user_id].remove(tag)
        self._save()
        return True

    def get(self, user_id: str) -> list[str]:
        """获取用户订阅。

        Args:
            user_id: 用户 ID。

        Returns:
            订阅的标签列表。
        """
        return self._subscriptions.get(user_id, [])

    def list_users(self) -> list[str]:
        """列出所有有订阅的用户。

        Returns:
            用户 ID 列表。
        """
        return list(self._subscriptions.keys())


class PermissionManager:
    """三级权限控制系统。"""

    def __init__(self, data_file: Optional[str] = None):
        """初始化权限管理器。

        Args:
            data_file: 权限数据存储文件路径。
        """
        if data_file:
            self.data_file = Path(data_file)
        else:
            self.data_file = Path(__file__).parent / "permissions.json"
        self._permissions: dict[str, Permission] = {}
        self._load()

    def _load(self) -> None:
        """加载权限数据。"""
        if self.data_file.exists():
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._permissions = {
                        k: Permission(v) for k, v in data.items()
                    }
            except Exception as e:
                logger.error(f"Failed to load permissions: {e}")
                self._permissions = {}

    def _save(self) -> None:
        """保存权限数据。"""
        try:
            self.data_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump({k: v.value for k, v in self._permissions.items()}, f)
        except Exception as e:
            logger.error(f"Failed to save permissions: {e}")

    def grant(self, user_id: str, permission: Permission) -> bool:
        """授予权限。

        Args:
            user_id: 用户 ID。
            permission: 权限级别。

        Returns:
            是否成功。
        """
        self._permissions[user_id] = permission
        self._save()
        return True

    def revoke(self, user_id: str) -> bool:
        """撤销权限。

        Args:
            user_id: 用户 ID。

        Returns:
            是否成功。
        """
        if user_id in self._permissions:
            del self._permissions[user_id]
            self._save()
            return True
        return False

    def get(self, user_id: str) -> Permission:
        """获取用户权限。

        Args:
            user_id: 用户 ID。

        Returns:
            权限级别，默认返回 READ。
        """
        return self._permissions.get(user_id, Permission.READ)

    def has_permission(self, user_id: str, required: Permission) -> bool:
        """检查用户是否有指定权限。

        Args:
            user_id: 用户 ID。
            required: 需要的权限级别。

        Returns:
            是否有权限。
        """
        user_perm = self.get(user_id)
        perm_levels = [Permission.READ, Permission.WRITE, Permission.DELETE]
        return perm_levels.index(user_perm) >= perm_levels.index(required)


def recognize_intent(text: str) -> tuple[Intent, str]:
    """识别用户意图（规则匹配）。

    优先匹配命令前缀，再匹配自然语言关键词。

    Args:
        text: 用户输入文本。

    Returns:
        (Intent, 参数字符串) 元组。
    """
    text = text.strip()
    text_lower = text.lower()

    command_patterns = {
        "/search": (Intent.SEARCH, None),
        "/today": (Intent.TODAY, None),
        "/top": (Intent.TOP, None),
        "/subscribe": (Intent.SUBSCRIBE, None),
        "/help": (Intent.HELP, None),
    }

    for cmd, result in command_patterns.items():
        if text_lower.startswith(cmd):
            params = text[len(cmd):].strip()
            return (result[0], params if params else result[1])

    keywords = {
        "搜索": Intent.SEARCH,
        "查询": Intent.SEARCH,
        "查找": Intent.SEARCH,
        "今天": Intent.BROWSE_TODAY,
        "今日": Intent.BROWSE_TODAY,
        "简报": Intent.BROWSE_TODAY,
        "最近": Intent.BROWSE_TODAY,
        "最新": Intent.BROWSE_TODAY,
        "top": Intent.BROWSE_TOP,
        "热门": Intent.BROWSE_TOP,
        "热门推荐": Intent.BROWSE_TOP,
        "订阅": Intent.SUBSCRIBE,
        "关注": Intent.SUBSCRIBE,
        "帮助": Intent.HELP,
        "help": Intent.HELP,
    }

    for keyword, intent in keywords.items():
        if keyword in text_lower:
            if intent == Intent.SUBSCRIBE:
                params = text_lower.replace(keyword, "").strip()
                return (intent, params)
            return (intent, text)

    return (Intent.UNKNOWN, text)


class KnowledgeBot:
    """知识库机器人主入口。"""

    def __init__(
        self,
        articles_dir: Optional[str] = None,
        data_dir: Optional[str] = None,
    ):
        """初始化知识库机器人。

        Args:
            articles_dir: 知识库文章目录路径。
            data_dir: 数据存储目录路径。
        """
        if articles_dir:
            self.articles_dir = Path(articles_dir)
        else:
            base_dir = Path(__file__).parent.parent
            self.articles_dir = base_dir / "knowledge" / "articles"

        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            self.data_dir = Path(__file__).parent / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.search_engine = KnowledgeSearchEngine(str(self.articles_dir))
        self.subscription_manager = SubscriptionManager(
            str(self.data_dir / "subscriptions.json")
        )
        self.permission_manager = PermissionManager(
            str(self.data_dir / "permissions.json")
        )

    def handle_message(self, user_id: str, text: str) -> str:
        """统一消息入口。

        Args:
            user_id: 用户 ID。
            text: 用户消息文本。

        Returns:
            回复文本。
        """
        intent, params = recognize_intent(text)

        if intent == Intent.SEARCH:
            return self._handle_search(user_id, params)
        elif intent in (Intent.TODAY, Intent.BROWSE_TODAY):
            return self._handle_today(user_id, params)
        elif intent in (Intent.TOP, Intent.BROWSE_TOP):
            return self._handle_top(user_id, params)
            return self._handle_top(user_id, params)
        elif intent == Intent.SUBSCRIBE:
            return self._handle_subscribe(user_id, params)
        elif intent == Intent.HELP:
            return self._handle_help(user_id, params)
        else:
            return "无法识别您的意图，请输入 /help 查看帮助。"

    def _handle_search(self, user_id: str, params: str) -> str:
        """处理搜索请求。

        Args:
            user_id: 用户 ID。
            params: 搜索参数。

        Returns:
            搜索结果文本。
        """
        if not self.permission_manager.has_permission(user_id, Permission.READ):
            return "您没有搜索权限。"

        keywords = params.split() if params else []
        results = self.search_engine.search(keywords=keywords or None)

        if not results:
            return "未找到匹配的知识条目。"

        response = f"找到 {len(results)} 条结果：\n\n"
        for i, article in enumerate(results, 1):
            title = article.get("title", "无标题")
            summary = article.get("summary", "无摘要")
            tags = article.get("tags", [])
            response += f"{i}. {title}\n   {summary}\n   标签: {', '.join(tags)}\n\n"

        return response.strip()

    def _handle_today(self, user_id: str, params: str) -> str:
        """处理今日简报请求。

        Args:
            user_id: 用户 ID。
            params: 附加参数。

        Returns:
            简报文本。
        """
        if not self.permission_manager.has_permission(user_id, Permission.READ):
            return "您没有查看权限。"

        try:
            limit = int(params) if params else 10
        except ValueError:
            limit = 10

        results = self.search_engine.get_today(limit=limit)

        if not results:
            return "今天暂无新增知识条目。"

        response = f"今日知识简报 (共 {len(results)} 条)：\n\n"
        for i, article in enumerate(results, 1):
            title = article.get("title", "无标题")
            summary = article.get("summary", "无摘要")
            response += f"{i}. {title}\n   {summary}\n\n"

        return response.strip()

    def _handle_top(self, user_id: str, params: str) -> str:
        """处理热门推荐请求。

        Args:
            user_id: 用户 ID。
            params: 附加参数。

        Returns:
            推荐结果文本。
        """
        if not self.permission_manager.has_permission(user_id, Permission.READ):
            return "您没有查看权限。"

        try:
            limit = int(params) if params else 10
        except ValueError:
            limit = 10

        results = self.search_engine.get_top(limit=limit)

        if not results:
            return "知识库为空。"

        response = f"热门推荐 (Top {len(results)})：\n\n"
        for i, article in enumerate(results, 1):
            title = article.get("title", "无标题")
            summary = article.get("summary", "无摘要")
            score = article.get("analysis", {}).get("relevance_score", 0)
            response += f"{i}. {title}\n   {summary}\n   评分: {score}\n\n"

        return response.strip()

    def _handle_subscribe(self, user_id: str, params: str) -> str:
        """处理订阅请求。

        Args:
            user_id: 用户 ID。
            params: 订阅参数。

        Returns:
            订阅结果文本。
        """
        if not self.permission_manager.has_permission(user_id, Permission.WRITE):
            return "您没有订阅权限，请联系管理员获取 WRITE 权限。"

        if not params or params == "list":
            subscriptions = self.subscription_manager.get(user_id)
            if not subscriptions:
                return "您尚未订阅任何标签。"
            return f"您的订阅: {', '.join(subscriptions)}"

        if params.startswith("add "):
            tags = params[4:].split(",")
            tags = [t.strip() for t in tags if t.strip()]
            self.subscription_manager.add(user_id, tags)
            return f"已添加订阅: {', '.join(tags)}"

        if params.startswith("remove "):
            tags = params[7:].split(",")
            tags = [t.strip() for t in tags if t.strip()]
            self.subscription_manager.remove(user_id, tags)
            return f"已移除订阅: {', '.join(tags)}"

        tags = params.split()
        self.subscription_manager.add(user_id, tags)
        return f"已订阅: {', '.join(tags)}"

    def _handle_help(self, user_id: str, params: str) -> str:
        """处理帮助请求。

        Args:
            user_id: 用户 ID。
            params: 附加参数。

        Returns:
            帮助文本。
        """
        return """知识库机器人帮助：

命令列表：
/search [关键词] - 搜索知识库
/today [数量] - 查看今日简报
/top [数量] - 查看热门推荐
/subscribe - 查看当前订阅
/subscribe add <标签> - 添加订阅
/subscribe remove <标签> - 移除订阅
/help - 显示帮助信息

权限说明：
- READ: 可搜索和查看知识库
- WRITE: 可管理订阅
- DELETE: 可删除内容（待实现）

自然语言示例：
- "搜索 AI"
- "今天有什么新内容"
- "热门推荐"
- "订阅 agent 标签"
"""