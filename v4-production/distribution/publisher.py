"""Publisher 模块：多渠道消息推送。

将生成的简报异步推送到 Telegram 和飞书。
"""

import asyncio
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import aiohttp

from distribution.formatter import DigestOutput, generate_daily_digest

import logging

logger = logging.getLogger(__name__)


@dataclass
class PublishResult:
    """发布结果数据类。

    Attributes:
        channel: 渠道标识（telegram/feishu）。
        success: 是否发布成功。
        message_id: 成功时返回的消息 ID，失败时为 None。
        error: 失败时的错误信息，成功时为 None。
    """

    channel: str
    success: bool
    message_id: str | None = None
    error: str | None = None


class BasePublisher(ABC):
    """消息发布器抽象基类。

    定义 send_message() 和 send_digest() 接口。
    """

    @abstractmethod
    async def send_message(self, content: Any) -> PublishResult:
        """发送单条消息。

        Args:
            content: 消息内容，格式由子类决定。

        Returns:
            PublishResult: 发布结果。
        """

    @abstractmethod
    async def send_digest(self, content: DigestOutput) -> PublishResult:
        """发送每日简报。

        Args:
            content: 包含多格式的简报内容。

        Returns:
            PublishResult: 发布结果。
        """


class TelegramPublisher(BasePublisher):
    """Telegram 消息发布器。

    通过 Telegram Bot API 异步发送 MarkdownV2 消息。
    """

    def __init__(self) -> None:
        """初始化 Telegram 发布器。

        Raises:
            ValueError: 缺少必要的环境变量。
        """
        self._token = os.getenv("TELEGRAM_BOT_TOKEN")
        self._chat_id = os.getenv("TELEGRAM_CHAT_ID")

        if not self._token:
            raise ValueError("缺少环境变量 TELEGRAM_BOT_TOKEN")
        if not self._chat_id:
            raise ValueError("缺少环境变量 TELEGRAM_CHAT_ID")

        self._api_url = f"https://api.telegram.org/bot{self._token}"
        self._timeout = aiohttp.ClientTimeout(total=30)

    async def send_message(self, content: str) -> PublishResult:
        """发送 MarkdownV2 格式消息。

        Args:
            content: MarkdownV2 格式的文本消息。

        Returns:
            PublishResult: 发布结果。
        """
        url = f"{self._api_url}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": content,
            "parse_mode": "MarkdownV2",
        }

        try:
            async with aiohttp.ClientSession(timeout=self._timeout) as session:
                async with session.post(url, json=payload) as response:
                    data = await response.json()

                    if response.status == 200 and data.get("ok"):
                        message_id = str(data["result"]["message_id"])
                        logger.info(f"Telegram 消息发送成功: {message_id}")
                        return PublishResult(
                            channel="telegram",
                            success=True,
                            message_id=message_id,
                        )
                    else:
                        error_msg = data.get("description", "未知错误")
                        logger.error(f"Telegram 发送失败: {error_msg}")
                        return PublishResult(
                            channel="telegram",
                            success=False,
                            error=error_msg,
                        )

        except asyncio.TimeoutError:
            logger.error("Telegram 请求超时")
            return PublishResult(
                channel="telegram",
                success=False,
                error="请求超时",
            )
        except aiohttp.ClientError as e:
            logger.error(f"Telegram 网络错误: {e}")
            return PublishResult(
                channel="telegram",
                success=False,
                error=str(e),
            )

    async def send_digest(self, content: DigestOutput) -> PublishResult:
        """发送每日简报。

        Args:
            content: 包含多格式的简报内容，使用 telegram 字段。

        Returns:
            PublishResult: 发布结果。
        """
        telegram_content = content.get("telegram", "")
        return await self.send_message(telegram_content)


class FeishuPublisher(BasePublisher):
    """飞书消息发布器。

    通过飞书 Webhook 发送卡片消息。
    """

    def __init__(self) -> None:
        """初始化飞书发布器。

        Raises:
            ValueError: 缺少必要的环境变量。
        """
        self._webhook_url = os.getenv("FEISHU_WEBHOOK_URL")

        if not self._webhook_url:
            raise ValueError("缺少环境变量 FEISHU_WEBHOOK_URL")

        self._timeout = aiohttp.ClientTimeout(total=30)

    async def send_message(self, content: dict) -> PublishResult:
        """发送卡片消息。

        Args:
            content: 飞书 interactive 卡片 dict。

        Returns:
            PublishResult: 发布结果。
        """
        try:
            async with aiohttp.ClientSession(timeout=self._timeout) as session:
                async with session.post(self._webhook_url, json=content) as response:
                    data = await response.json()

                    if response.status == 200 and data.get("code") == 0:
                        logger.info("飞书消息发送成功")
                        return PublishResult(
                            channel="feishu",
                            success=True,
                            message_id=data.get("msg_id"),
                        )
                    else:
                        error_msg = data.get("msg", "未知错误")
                        logger.error(f"飞书发送失败: {error_msg}")
                        return PublishResult(
                            channel="feishu",
                            success=False,
                            error=error_msg,
                        )

        except asyncio.TimeoutError:
            logger.error("飞书请求超时")
            return PublishResult(
                channel="feishu",
                success=False,
                error="请求超时",
            )
        except aiohttp.ClientError as e:
            logger.error(f"飞书网络错误: {e}")
            return PublishResult(
                channel="feishu",
                success=False,
                error=str(e),
            )

    async def send_digest(self, content: DigestOutput) -> PublishResult:
        """发送每日简报。

        Args:
            content: 包含多格式的简报内容，使用 feishu 字段。

        Returns:
            PublishResult: 发布结果。
        """
        feishu_content = content.get("feishu", {})
        return await self.send_message(feishu_content)


async def publish_daily_digest(
    knowledge_dir: str = "knowledge/articles",
    date: str | None = None,
    top_n: int = 5,
    channels: list[str] | None = None,
) -> list[PublishResult]:
    """统一异步入口：生成并发布每日简报。

    调用 generate_daily_digest() 生成三种格式，并发发布到所有渠道。

    Args:
        knowledge_dir: 知识库目录路径。
        date: 目标日期字符串，格式 "YYYY-MM-DD"，默认为当天。
        top_n: 最多返回条目数。
        channels: 要发布的渠道列表，默认为 ["telegram", "feishu"]。

    Returns:
        各渠道的发布结果列表。
    """
    if channels is None:
        channels = ["telegram", "feishu"]

    digest = generate_daily_digest(knowledge_dir=knowledge_dir, date=date, top_n=top_n)

    publishers: dict[str, BasePublisher] = {}
    for channel in channels:
        try:
            if channel == "telegram":
                publishers[channel] = TelegramPublisher()
            elif channel == "feishu":
                publishers[channel] = FeishuPublisher()
        except ValueError as e:
            logger.warning(f"跳过渠道 {channel}: {e}")

    tasks = []
    for channel, publisher in publishers.items():
        task = publisher.send_digest(digest)
        tasks.append(task)

    results = await asyncio.gather(*tasks, return_exceptions=True)

    output: list[PublishResult] = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            channel = list(publishers.keys())[i]
            logger.error(f"渠道 {channel} 发布异常: {result}")
            output.append(PublishResult(
                channel=channel,
                success=False,
                error=str(result),
            ))
        else:
            output.append(result)

    return output