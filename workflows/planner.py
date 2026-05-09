"""Planner node for knowledge base pipeline."""
import os

from workflows.state import KBState


def plan_strategy(target_count: int | None = None) -> dict:
    """根据目标采集量返回对应策略。

    Args:
        target_count: 目标采集数量，不传则从环境变量 PLANNER_TARGET_COUNT 读取

    Returns:
        策略配置 dict
    """
    if target_count is None:
        target_count = int(os.environ.get("PLANNER_TARGET_COUNT", "10"))

    if target_count < 10:
        tier = "lite"
        strategy = {
            "tier": tier,
            "per_source_limit": 5,
            "relevance_threshold": 0.7,
            "max_iterations": 1,
            "rationale": (
                "采集量 <10 时采用轻量策略，限制每个来源最多 5 条，"
                "高相关性阈值 0.7 过滤噪音，单次迭代快速产出。"
            ),
        }
    elif target_count < 20:
        tier = "standard"
        strategy = {
            "tier": tier,
            "per_source_limit": 10,
            "relevance_threshold": 0.5,
            "max_iterations": 2,
            "rationale": (
                "采集量 10-20 时采用标准策略，平衡数量与质量，"
                "中等阈值 0.5 保证覆盖率，两次迭代充分审核。"
            ),
        }
    else:
        tier = "full"
        strategy = {
            "tier": tier,
            "per_source_limit": 20,
            "relevance_threshold": 0.4,
            "max_iterations": 3,
            "rationale": (
                "采集量 >=20 时采用完整策略，扩大来源上限 20 条，"
                "低阈值 0.4 尽量保留内容，三次迭代确保质量。"
            ),
        }

    return strategy


def planner_node(state: KBState) -> dict:
    """LangGraph 节点：生成采集策略。"""
    plan = plan_strategy()
    print(f"[planner_node] tier={plan['tier']}, rationale={plan['rationale'][:40]}...")
    return {"plan": plan}
