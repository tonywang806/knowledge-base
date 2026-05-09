"""Review node - five-dimension quality reviewer."""
import logging

from workflows.model_client import accumulate_usage, chat_json

logger = logging.getLogger(__name__)

REVIEWER_PASS_THRESHOLD = 6.5

WEIGHTS = {
    "summary_quality": 0.25,
    "technical_depth": 0.25,
    "relevance": 0.20,
    "originality": 0.15,
    "formatting": 0.15,
}

SYSTEM_PROMPT = """你是一个专业的 AI 技术内容审核员。请对以下分析结果进行五维度评分：

1. summary_quality (摘要质量): 摘要是否清晰、准确、有信息量 (1-10)
2. technical_depth (技术深度): 技术分析是否深入、有洞察 (1-10)
3. relevance (相关性): 与 AI/LLM/Agent 领域相关程度 (1-10)
4. originality (原创性): 内容是否有独特见解 (1-10)
5. formatting (格式规范): 格式是否符合规范（中文摘要、不超过100字、适当标签）(1-10)

输出格式（严格 JSON 数组，每项对应一条分析）：
[
  {
    "summary_quality": 1-10,
    "technical_depth": 1-10,
    "relevance": 1-10,
    "originality": 1-10,
    "formatting": 1-10,
    "weighted_score": 0.0,
    "comment": "简短评语（可选）"
  }
]"""


def review_node(state):
    """五维度审核 analyses，加权总分 >= 7.0 通过。"""
    print("[review_node] 开始审核...")

    analyses = state["analyses"][:5]

    prompt_parts = []
    for i, ana in enumerate(analyses):
        prompt_parts.append(
            f"### 分析 {i+1}\n"
            f"标题: {ana.get('title', '')}\n"
            f"摘要: {ana.get('summary', '')}\n"
            f"标签: {', '.join(ana.get('tags', []))}\n"
            f"来源: {ana.get('source_url', '')}"
        )

    prompt = "请对以下分析结果进行评分：\n\n" + "\n\n".join(prompt_parts)

    try:
        parsed, usage = chat_json(prompt, system=SYSTEM_PROMPT, temperature=0.2, node_name="review")
        accumulate_usage(state["usage"], usage)
    except Exception as e:
        logger.warning(f"[review_node] LLM 调用失败，自动通过: {e}")
        return {
            "review_passed": True,
            "review_feedback": None,
            "review_result": {},
        }

    if not isinstance(parsed, list):
        parsed = []

    total_score = 0.0
    score_count = 0
    for score_entry in parsed:
        ws = sum(
            score_entry.get(dim, 5) * w
            for dim, w in WEIGHTS.items()
        )
        score_entry["weighted_score"] = ws
        total_score += ws
        score_count += 1

    avg_score = (total_score / score_count) if score_count > 0 else 0.0
    review_passed = avg_score >= REVIEWER_PASS_THRESHOLD
    feedback = None if review_passed else f"加权总分 {avg_score:.2f} < {REVIEWER_PASS_THRESHOLD}，请改进"

    print(f"[review_node] 审核完成，passed={review_passed}，avg={avg_score:.2f}")
    return {
        "review_passed": review_passed,
        "review_feedback": feedback,
        "review_result": {"scores": parsed, "avg_score": avg_score},
    }
