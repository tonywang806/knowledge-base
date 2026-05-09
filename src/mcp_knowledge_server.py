#!/usr/bin/env python3
"""
MCP Knowledge Server - 提供本地知识库搜索能力
使用 JSON-RPC 2.0 over stdio 协议
"""

import json
import os
import sys
from collections import Counter
from pathlib import Path


def _get_base_dir():
    return Path(__file__).parent.resolve().parent


KNOWLEDGE_DIR = _get_base_dir() / "knowledge" / "articles"


class MCPServer:
    def __init__(self):
        self.tools = {
            "search_articles": {
                "description": "搜索知识库文章",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "keyword": {"type": "string", "description": "搜索关键词"},
                        "limit": {"type": "integer", "description": "返回数量限制", "default": 5}
                    },
                    "required": ["keyword"]
                }
            },
            "get_article": {
                "description": "获取单篇文章详情",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "article_id": {"type": "string", "description": "文章ID"}
                    },
                    "required": ["article_id"]
                }
            },
            "knowledge_stats": {
                "description": "获取知识库统计信息",
                "inputSchema": {"type": "object", "properties": {}}
            }
        }
        self._cache = None

    def _load_articles(self):
        if self._cache is not None:
            return self._cache
        self._cache = []
        for f in KNOWLEDGE_DIR.glob("*.json"):
            try:
                with open(f, encoding="utf-8") as fp:
                    self._cache.append(json.load(fp))
            except (json.JSONDecodeError, IOError):
                continue
        return self._cache

    def _search(self, keyword, limit=5):
        kw = keyword.lower()
        articles = self._load_articles()
        results = [
            (a, (kw in a.get("title", "").lower()) +
                (kw in a.get("summary", "").lower()) * 0.5)
            for a in articles
        ]
        results = [(a, score) for a, score in results if score > 0]
        results.sort(key=lambda x: (-x[1], -x[0].get("analysis", {}).get("relevance_score", 0)))
        return [a for a, _ in results[:limit]]

    def _get_article(self, article_id):
        articles = self._load_articles()
        for a in articles:
            if a.get("id") == article_id:
                return a
        return None

    def _stats(self):
        articles = self._load_articles()
        sources = Counter(a.get("source", "unknown") for a in articles)
        tags = Counter(tag for a in articles for tag in a.get("tags", []))
        return {
            "total": len(articles),
            "by_source": dict(sources),
            "top_tags": [t for t, _ in tags.most_common(10)]
        }

    def _handle_initialize(self, params):
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "mcp_knowledge_server", "version": "1.0.0"}
        }

    def _handle_tools_list(self, params):
        tools = [{"name": k, **v} for k, v in self.tools.items()]
        return {"tools": tools}

    def _handle_tools_call(self, params):
        name = params.get("name")
        args = params.get("arguments", {})

        if name == "search_articles":
            results = self._search(args.get("keyword", ""), args.get("limit", 5))
            return {
                "content": [{
                    "type": "text",
                    "text": json.dumps([
                        {"id": a["id"], "title": a["title"], "summary": a.get("summary", "")[:200]}
                        for a in results
                    ], ensure_ascii=False)
                }]
            }
        elif name == "get_article":
            article = self._get_article(args.get("article_id", ""))
            if not article:
                return {"content": [{"type": "text", "text": "Article not found"}], "isError": True}
            return {"content": [{"type": "text", "text": json.dumps(article, ensure_ascii=False)}]}
        elif name == "knowledge_stats":
            stats = self._stats()
            return {"content": [{"type": "text", "text": json.dumps(stats, ensure_ascii=False)}]}
        return {"content": [{"type": "text", "text": "Unknown tool"}], "isError": True}

    def _dispatch(self, method, params):
        handlers = {
            "initialize": self._handle_initialize,
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tools_call,
        }
        handler = handlers.get(method)
        if handler:
            return {"result": handler(params)}
        return {"error": {"code": -32601, "message": f"Method not found: {method}"}}

    def run(self):
        for line in sys.stdin:
            try:
                request = json.loads(line.strip())
            except json.JSONDecodeError:
                continue

            response = self._dispatch(request.get("method", ""), request.get("params", {}))
            response["jsonrpc"] = "2.0"
            response["id"] = request.get("id")
            print(json.dumps(response), flush=True)


if __name__ == "__main__":
    MCPServer().run()
