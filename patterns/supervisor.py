"""Supervisor 监督模式模块。

实现双 Agent 协作：
1. Worker Agent：接收任务，输出 JSON 格式的分析报告
2. Supervisor Agent：对 Worker 的输出进行质量审核

审核维度：准确性(1-10)、深度(1-10)、格式(1-10)
通过阈值：score >= 7
最大重试轮次：3 轮
"""
import json
import logging
from typing import Optional

from pipeline.model_client import chat_with_retry

logger = logging.getLogger(__name__)

PASS_THRESHOLD = 7


def _chat(messages: list[dict[str, str]]) -> tuple[str, dict]:
    """发送聊天请求并返回 (text, usage) 元组。

    Args:
        messages: 消息列表。

    Returns:
        (text, usage_dict) 元组。
    """
    response = chat_with_retry(messages)
    usage = {
        "prompt_tokens": response.usage.prompt_tokens,
        "completion_tokens": response.usage.completion_tokens,
        "total_tokens": response.usage.total_tokens,
    }
    return response.content, usage


def worker_analyze(task: str) -> dict:
    """Worker Agent：分析任务并输出 JSON 格式的报告。

    Args:
        task: 用户任务描述。

    Returns:
        JSON 格式的分析报告。
    """
    system_prompt = """你是一个专业的技术分析师。请分析用户提出的任务，并输出一份 JSON 格式的分析报告。

输出格式要求：
{
    "topic": "分析主题",
    "summary": "简短摘要（50字以内）",
    "key_points": ["要点1", "要点2", "要点3"],
    "conclusion": "结论或建议"
}

请确保输出是合法的 JSON，不要包含 Markdown 代码块或其他额外内容。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]

    try:
        text, usage = _chat(messages)
        logger.info(f"Worker 调用消耗: {usage['total_tokens']} tokens")
        return json.loads(text.strip())
    except json.JSONDecodeError as e:
        logger.error(f"Worker JSON 解析失败: {e}")
        return {
            "topic": "解析失败",
            "summary": "Worker 输出无法解析为 JSON",
            "key_points": [],
            "conclusion": "请重试",
        }


def supervisor_review(worker_output: dict) -> dict:
    """Supervisor Agent：审核 Worker 的输出。

    Args:
        worker_output: Worker 输出的 JSON 报告。

    Returns:
        审核结果 {"passed": bool, "score": int, "feedback": str}。
    """
    system_prompt = """你是一个严格的质量审核员。请对分析报告进行评分和反馈。

评分维度（每个维度 1-10 分）：
1. 准确性：信息是否准确、可靠
2. 深度：分析是否深入、有洞察
3. 格式：JSON 结构是否规范、完整

总分计算：(准确性 + 深度 + 格式) / 3，取整数

输出格式要求（必须是合法 JSON）：
{
    "passed": true或false（当总分 >= 7 时为 true）,
    "score": 总分（1-10 的整数）,
    "accuracy": 准确性分数（1-10）,
    "depth": 深度分数（1-10）,
    "format_score": 格式分数（1-10）,
    "feedback": "审核反馈，简要说明评分理由和改进建议"
}

请直接输出 JSON，不要包含 Markdown 代码块或其他额外内容。"""

    output_str = json.dumps(worker_output, ensure_ascii=False, indent=2)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"请审核以下分析报告：\n\n{output_str}"},
    ]

    try:
        text, usage = _chat(messages)
        logger.info(f"Supervisor 调用消耗: {usage['total_tokens']} tokens")
        result = json.loads(text.strip())
        return {
            "passed": result.get("passed", False),
            "score": result.get("score", 0),
            "feedback": result.get("feedback", ""),
        }
    except json.JSONDecodeError as e:
        logger.error(f"Supervisor JSON 解析失败: {e}")
        return {
            "passed": False,
            "score": 0,
            "feedback": f"审核器解析失败: {e}",
        }


def supervisor(task: str, max_retries: int = 3) -> dict:
    """Supervisor 主函数：协调 Worker 和 Supervisor 进行质量控制。

    Args:
        task: 用户任务描述。
        max_retries: 最大重试次数（默认 3）。

    Returns:
        包含以下字段的字典：
        - output: Worker 的最终输出（dict）
        - attempts: 尝试次数（int）
        - final_score: 最终评分（int）
        - warning: 警告信息（可选，仅在超限后出现）
    """
    output = None
    attempts = 0
    final_score = 0
    warning = None

    for attempt in range(1, max_retries + 1):
        attempts = attempt
        logger.info(f"=== 第 {attempt} 轮审核 ===")

        worker_output = worker_analyze(task)
        output = worker_output
        logger.info(f"Worker 输出: {json.dumps(worker_output, ensure_ascii=False)[:200]}...")

        review_result = supervisor_review(worker_output)
        final_score = review_result["score"]

        logger.info(f"审核结果: passed={review_result['passed']}, score={final_score}")
        logger.info(f"反馈: {review_result['feedback']}")

        if review_result["passed"]:
            logger.info(f"审核通过！总尝试次数: {attempt}")
            return {
                "output": output,
                "attempts": attempts,
                "final_score": final_score,
            }

        if attempt < max_retries:
            logger.info(f"审核未通过，进入第 {attempt + 1} 轮...")

    logger.warning(f"达到最大重试次数 ({max_retries})，强制返回")
    warning = f"超过最大重试次数 {max_retries}，输出可能未达最佳质量"
    return {
        "output": output,
        "attempts": attempts,
        "final_score": final_score,
        "warning": warning,
    }


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    print("=== Supervisor 监督模式测试 ===\n")

    test_tasks = [
        "分析当前 AI Agent 领域的技术发展趋势",
        "解释 LangGraph 的核心概念和工作原理",
    ]

    for i, task in enumerate(test_tasks, 1):
        print(f"--- 测试任务 {i}: {task} ---")
        result = supervisor(task, max_retries=3)

        print(f"\n最终输出:")
        print(json.dumps(result["output"], ensure_ascii=False, indent=2))
        print(f"\n尝试次数: {result['attempts']}")
        print(f"最终评分: {result['final_score']}")
        if result.get("warning"):
            print(f"⚠️ 警告: {result['warning']}")
        print("\n" + "=" * 60 + "\n")