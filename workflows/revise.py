"""Revise node - revise analyses based on review feedback."""
import json
import logging

from workflows.model_client import accumulate_usage, chat_json

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个严谨的技术编辑。请根据审核反馈，修改分析结果。

要求：
1. 修正摘要（更清晰、更准确）
2. 调整标签（更贴切）
3. 如有必要修正 relevance_score
4. 保持 JSON 输出格式

输出格式（JSON 数组，每项包含 id, summary, tags, relevance_score）：
[
  {
    "id": "原 ID",
    "summary": "修正后的摘要",
    "tags": ["修正后的标签"],
    "relevance_score": 修正后的评分
  }
  ]"""


def revise_node(state):
    """根据审核反馈修改 analyses。"""
    analyses = state["analyses"]
    feedback = state.get("review_feedback")

    if not analyses or not feedback:
        print("[revise_node] 无 analyses 或 review_feedback，跳过")
        return {}

    print("[revise_node] 开始修改...")

    input_data = {
        "feedback": feedback,
        "analyses": analyses,
    }
    prompt = json.dumps(input_data, ensure_ascii=False)

    parsed, usage = chat_json(prompt, system=SYSTEM_PROMPT, temperature=0.4, node_name="revise")
    accumulate_usage(state["usage"], usage)

    if not isinstance(parsed, list):
        parsed = []

    meta_map = {m["id"]: m for m in parsed}
    improved = []
    for item in analyses:
        mid = item.get("id", "")
        if mid in meta_map:
            m = meta_map[mid]
            improved.append({
                **item,
                "summary": m.get("summary", item.get("summary", "")),
                "tags": m.get("tags", item.get("tags", [])),
                "relevance_score": m.get("relevance_score", item.get("relevance_score", 0.5)),
            })
        else:
            improved.append(item)

    print(f"[revise_node] 修改完成，{len(improved)} 条")
    return {"analyses": improved, "iteration": state["iteration"] + 1}
