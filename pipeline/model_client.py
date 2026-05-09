"""统一 LLM 调用客户端模块。

支持 DeepSeek、Qwen、OpenAI、Ollama 四种模型提供商。
通过环境变量 LLM_PROVIDER 切换，默认使用 Ollama 本地模型。
"""
import os
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class Usage:
    """Token 用量统计。"""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class LLMResponse:
    """LLM 调用响应。"""

    content: str
    usage: Usage


class LLMProvider(ABC):
    """LLM Provider 抽象基类。"""

    @abstractmethod
    def chat(self, messages: list[dict[str, str]]) -> LLMResponse:
        """发送聊天请求。

        Args:
            messages: 消息列表，格式为 [{"role": "user", "content": "..."}]。

        Returns:
            LLMResponse 对象。
        """
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """获取模型名称。"""
        pass


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI 兼容 API Provider 实现。"""

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        model_name: str = "gpt-4o-mini",
        timeout: float = 60.0,
        is_ollama: bool = False,
    ):
        """初始化 Provider。

        Args:
            base_url: API 基础地址。
            api_key: API Key，可为 None（如 Ollama 本地部署）。
            model_name: 模型名称。
            timeout: 请求超时时间（秒）。
            is_ollama: 是否为 Ollama（使用不同 API 格式）。
        """
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model_name = model_name
        self._timeout = timeout
        self._is_ollama = is_ollama

    @property
    def model_name(self) -> str:
        return self._model_name

    def chat(self, messages: list[dict[str, str]]) -> LLMResponse:
        """发送聊天请求到 OpenAI 兼容 API。

        Args:
            messages: 消息列表。

        Returns:
            LLMResponse 对象。

        Raises:
            httpx.HTTPStatusError: API 返回错误状态码。
            httpx.TimeoutException: 请求超时。
        """
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        if self._is_ollama:
            return self._ollama_chat(messages, headers)
        else:
            return self._openai_chat(messages, headers)

    def _openai_chat(
        self,
        messages: list[dict[str, str]],
        headers: dict[str, str],
    ) -> LLMResponse:
        """OpenAI 格式 API 调用。"""
        payload = {
            "model": self._model_name,
            "messages": messages,
            "stream": False,
        }

        url = f"{self._base_url}/chat/completions"

        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        usage_data = data.get("usage", {})
        usage = Usage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )

        return LLMResponse(content=content, usage=usage)

    def _ollama_chat(
        self,
        messages: list[dict[str, str]],
        headers: dict[str, str],
    ) -> LLMResponse:
        """Ollama API 调用。"""
        payload = {
            "model": self._model_name,
            "messages": messages,
            "stream": False,
        }

        url = f"{self._base_url}/api/chat"

        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        content = data["message"]["content"]
        usage = Usage(
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
            total_tokens=data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
        )

        return LLMResponse(content=content, usage=usage)


def _get_default_provider() -> LLMProvider:
    """根据环境变量创建默认 Provider。

    Returns:
        LLMProvider 实例。
    """
    provider = os.getenv("LLM_PROVIDER", "ollama").lower()

    if provider == "ollama":
        return OpenAICompatibleProvider(
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            api_key=None,
            model_name=os.getenv("OLLAMA_MODEL", "qwen3.6:latest"),
            is_ollama=True,
        )
    elif provider == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY 环境变量未设置")
        return OpenAICompatibleProvider(
            base_url="https://api.deepseek.com/v1",
            api_key=api_key,
            model_name="deepseek-chat",
        )
    elif provider == "qwen":
        api_key = os.getenv("QWEN_API_KEY")
        if not api_key:
            raise ValueError("QWEN_API_KEY 环境变量未设置")
        return OpenAICompatibleProvider(
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=api_key,
            model_name="qwen-turbo",
        )
    elif provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY 环境变量未设置")
        return OpenAICompatibleProvider(
            base_url="https://api.openai.com/v1",
            api_key=api_key,
            model_name="gpt-4o-mini",
        )
    else:
        raise ValueError(f"不支持的 LLM_PROVIDER: {provider}")


_default_provider: Optional[LLMProvider] = None


def get_provider() -> LLMProvider:
    """获取默认 Provider 实例（单例）。

    Returns:
        LLMProvider 实例。
    """
    global _default_provider
    if _default_provider is None:
        _default_provider = _get_default_provider()
    return _default_provider


def chat_with_retry(
    messages: list[dict[str, str]],
    provider: Optional[LLMProvider] = None,
    max_retries: int = 3,
    base_delay: float = 1.0,
    timeout: float = 60.0,
) -> LLMResponse:
    """带重试的聊天请求。

    Args:
        messages: 消息列表。
        provider: LLMProvider 实例，默认为全局 provider。
        max_retries: 最大重试次数。
        base_delay: 初始延迟（秒），后续指数增长。
        timeout: 请求超时时间（秒）。

    Returns:
        LLMResponse 对象。

    Raises:
        httpx.HTTPStatusError: 所有重试均失败后抛出最后一次异常。
    """
    if provider is None:
        provider = get_provider()

    last_exception = None
    for attempt in range(max_retries):
        try:
            return provider.chat(messages)
        except (httpx.HTTPStatusError, httpx.TimeoutException) as e:
            last_exception = e
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    f"请求失败 (尝试 {attempt + 1}/{max_retries}): {e}. "
                    f"等待 {delay:.1f}s 后重试..."
                )
                time.sleep(delay)
            else:
                logger.error(f"请求最终失败: {e}")

    raise last_exception


def quick_chat(
    content: str,
    system_prompt: Optional[str] = None,
    provider: Optional[LLMProvider] = None,
) -> str:
    """便捷的聊天函数，一句话调用 LLM。

    Args:
        content: 用户消息内容。
        system_prompt: 系统提示词，可选。
        provider: LLMProvider 实例，可选。

    Returns:
        LLM 返回的内容字符串。
    """
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": content})

    response = chat_with_retry(messages, provider=provider)
    return response.content


# Token 消耗估算和成本计算（USD 计价）
MODEL_PRICING = {
    "deepseek-chat": {"input": 0.27, "output": 1.10},
    "qwen-turbo": {"input": 0.40, "output": 1.20},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "ollama": {"input": 0.0, "output": 0.0},  # 本地部署免费
}


def estimate_tokens(text: str) -> int:
    """估算文本的 Token 数量。

    简单估算：约 4 个字符 = 1 个 Token。

    Args:
        text: 输入文本。

    Returns:
        估算的 Token 数量。
    """
    return len(text) // 4


def calculate_cost(
    model_name: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> float:
    """计算 API 调用成本（USD）。

    Args:
        model_name: 模型名称。
        prompt_tokens: 输入 Token 数量。
        completion_tokens: 输出 Token 数量。

    Returns:
        成本（美元）。
    """
    pricing = MODEL_PRICING.get(model_name, {"input": 0.0, "output": 0.0})

    input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
    output_cost = (completion_tokens / 1_000_000) * pricing["output"]

    return input_cost + output_cost


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=== 模型客户端测试 ===")
    print(f"Provider: {os.getenv('LLM_PROVIDER', 'ollama')}")

    provider = get_provider()
    print(f"Model: {provider.model_name}")

    messages = [{"role": "user", "content": "你好，请用一句话介绍自己"}]
    response = chat_with_retry(messages)

    print(f"\n回复: {response.content}")
    print(f"用量: {response.usage}")

    cost = calculate_cost(
        provider.model_name,
        response.usage.prompt_tokens,
        response.usage.completion_tokens,
    )
    print(f"成本: ${cost:.6f}")

    quick_result = quick_chat("2 + 2 等于多少？")
    print(f"\nquick_chat 结果: {quick_result}")