"""Router 路由模式模块。

实现两层意图分类策略：
1. 第一层：关键词快速匹配（零成本，不调 LLM）
2. 第二层：LLM 分类兜底（处理模糊意图）

支持三种意图：github_search / knowledge_query / general_chat
"""
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

KNOWLEDGE_INDEX_PATH = Path(__file__).parent.parent / "knowledge" / "articles" / "index.json"

GITHUB_KEYWORDS = ["github", "项目", "仓库", "搜索", "repo", "search"]
KNOWLEDGE_KEYWORDS = ["知识库", "知识", "查找", "查询", "article", "文章", "笔记"]
GREETING_KEYWORDS = ["你好", "hi", "hello", "在吗", "嗨", "嗯", "啊", "哦", "好吧", "好的", "收到", "知道了"]

SIMPLE_REPLIES = {
    "你好": "你好！有什么我可以帮你的吗？",
    "hi": "Hi！需要帮忙搜点什么吗？",
    "hello": "你好！有什么可以帮到你？",
    "在吗": "在的！请说",
    "嗨": "嗨！需要帮忙吗？",
    "嗯": "嗯嗯，在的呢",
    "啊": "怎么啦？",
    "哦": "好的，还有什么需要吗？",
    "好吧": "好的",
    "好的": "收到！还有别的吗？",
    "收到": "好的！",
    "知道了": "好的！",
}


def chat(messages: list[dict[str, str]]) -> tuple[str, dict]:
    """发送聊天请求并返回 (text, usage) 元组。

    Args:
        messages: 消息列表，格式为 [{"role": "user", "content": "..."}]。

    Returns:
        (text, usage) 元组，其中 usage 是包含 token 信息的字典。
    """
    from pipeline.model_client import chat_with_retry

    response = chat_with_retry(messages)
    usage = {
        "prompt_tokens": response.usage.prompt_tokens,
        "completion_tokens": response.usage.completion_tokens,
        "total_tokens": response.usage.total_tokens,
    }
    return response.content, usage


def chat_json(messages: list[dict[str, str]]) -> dict:
    """发送聊天请求并解析 JSON 响应。

    Args:
        messages: 消息列表。

    Returns:
        解析后的 JSON 对象。
    """
    from pipeline.model_client import chat_with_retry

    response = chat_with_retry(messages)
    try:
        return json.loads(response.content)
    except json.JSONDecodeError:
        logger.error(f"JSON 解析失败: {response.content}")
        return {}


def classify_by_keywords(query: str) -> Optional[str]:
    """第一层分类：关键词快速匹配。

    Args:
        query: 用户查询。

    Returns:
        意图类型字符串，如果无法匹配则返回 None。
    """
    query_lower = query.lower().strip()
    github_score = sum(1 for kw in GITHUB_KEYWORDS if kw.lower() in query_lower)
    knowledge_score = sum(1 for kw in KNOWLEDGE_KEYWORDS if kw.lower() in query_lower)

    if github_score > knowledge_score:
        return "github_search"
    elif knowledge_score > github_score:
        return "knowledge_query"

    if query_lower in [k.lower() for k in GREETING_KEYWORDS] or (
        any(word in query_lower for word in GREETING_KEYWORDS) and len(query) < 10
    ):
        return "general_chat"

    return None


def classify_by_llm(query: str) -> str:
    """第二层分类：LLM 分类兜底。

    Args:
        query: 用户查询。

    Returns:
        意图类型字符串。
    """
    system_prompt = """你是一个意图分类器。请根据用户查询判断其意图类型。
可选类型：
- github_search: 用户想要搜索 GitHub 仓库
- knowledge_query: 用户想要查询本地知识库中的内容
- general_chat: 用户想要进行一般性对话

请直接返回类型名称，不要返回其他内容。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query},
    ]

    try:
        intent, _ = chat(messages)
        intent = intent.strip().lower()
        if intent in ["github_search", "knowledge_query", "general_chat"]:
            return intent
    except Exception as e:
        logger.warning(f"LLM 分类失败: {e}")

    return "general_chat"


def route(query: str) -> str:
    """统一入口函数：根据查询内容路由到对应的处理器。

    Args:
        query: 用户查询。

    Returns:
        处理结果字符串。
    """
    intent = classify_by_keywords(query)
    if intent is None:
        logger.info("关键词匹配未命中，使用 LLM 分类")
        intent = classify_by_llm(query)

    logger.info(f"识别到意图: {intent}")

    if intent == "github_search":
        return handle_github_search(query)
    elif intent == "knowledge_query":
        return handle_knowledge_query(query)
    else:
        return handle_general_chat(query)


def handle_github_search(query: str) -> str:
    """处理 GitHub 搜索请求。

    Args:
        query: 用户查询。

    Returns:
        搜索结果字符串。
    """
    query = query.strip()
    for prefix in ["搜索 github ", "github ", "搜索 ", "搜 "]:
        if query.startswith(prefix):
            query = query[len(prefix):].strip()
            break

    if not query:
        return "请提供搜索关键词，例如：搜索 github langgraph"

    encoded_query = urllib.parse.quote(query)
    url = f"https://api.github.com/search/repositories?q={encoded_query}&per_page=5"

    try:
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/vnd.github.v3+json")
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))

        items = data.get("items", [])
        if not items:
            return f"未找到与 '{query}' 相关的 GitHub 仓库"

        results = []
        for i, item in enumerate(items, 1):
            name = item.get("full_name", "")
            desc = item.get("description", "") or "无描述"
            stars = item.get("stargazers_count", 0)
            url_repo = item.get("html_url", "")
            results.append(f"{i}. {name}\n   {desc}\n   ⭐ {stars} | {url_repo}")

        return "GitHub 搜索结果：\n\n" + "\n\n".join(results)

    except urllib.error.HTTPError as e:
        return f"GitHub API 请求失败: {e.code}"
    except urllib.error.URLError as e:
        return f"网络请求失败: {e.reason}"
    except Exception as e:
        return f"搜索失败: {str(e)}"


def handle_knowledge_query(query: str) -> str:
    """处理知识库查询请求。

    Args:
        query: 用户查询。

    Returns:
        知识库检索结果字符串。
    """
    query = query.strip()
    for prefix in ["查询知识库 ", "知识库 ", "查找 ", "搜索知识 ", "查 "]:
        if query.startswith(prefix):
            query = query[len(prefix):].strip()
            break

    if not query:
        return "请提供查询关键词，例如：查询知识库 langgraph"

    if not KNOWLEDGE_INDEX_PATH.exists():
        return f"知识库索引文件不存在: {KNOWLEDGE_INDEX_PATH}"

    try:
        with open(KNOWLEDGE_INDEX_PATH, "r", encoding="utf-8") as f:
            index_data = json.load(f)

        articles = index_data.get("articles", [])
        if not articles:
            return "知识库为空"

        query_lower = query.lower()
        matched = []
        for article in articles:
            title = article.get("title", "").lower()
            summary = article.get("summary", "").lower()
            tags = [t.lower() for t in article.get("tags", [])]
            if query_lower in title or query_lower in summary or any(query_lower in tag for tag in tags):
                matched.append(article)

        if not matched:
            return f"未找到与 '{query}' 相关的知识条目"

        results = []
        for item in matched[:5]:
            title = item.get("title", "无标题")
            summary = item.get("summary", "无摘要")
            source_url = item.get("source_url", "")
            tags = item.get("tags", [])
            results.append(f"- {title}\n  {summary}\n  标签: {', '.join(tags)}")

        return "知识库查询结果：\n\n" + "\n\n".join(results)

    except json.JSONDecodeError:
        return "知识库索引文件格式错误"
    except Exception as e:
        return f"知识库查询失败: {str(e)}"


def handle_general_chat(query: str) -> str:
    """处理一般性聊天请求。

    Args:
        query: 用户查询。

    Returns:
        LLM 回复内容。
    """
    query_lower = query.lower().strip()

    if query_lower in SIMPLE_REPLIES:
        return SIMPLE_REPLIES[query_lower]

    system_prompt = "你是一个友好的 AI 助手，请根据用户问题给出有帮助的回答。"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query},
    ]

    try:
        reply, _ = chat(messages)
        return reply
    except Exception as e:
        return f"聊天失败: {str(e)}"


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    test_queries = [
        "搜索 github langchain",
        "查找 langgraph 相关文章",
        "今天天气怎么样",
        "你好",
        "在吗",
        "好的",
    ]

    print("=== Router 测试 ===\n")
    for q in test_queries:
        print(f"输入: {q}")
        result = route(q)
        print(f"输出: {result}\n")
        print("-" * 50)