"""LangGraph 工作流图 — 6 节点版"""
import logging
import sys
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).parent.parent))

from langgraph.graph import END, StateGraph

from workflows.planner import planner_node
from workflows.analyze import analyze_node
from workflows.collect import collect_node
from workflows.organize import organize_node
from workflows.review import review_node
from workflows.revise import revise_node
from workflows.reviser import human_flag_node
from workflows.state import KBState, new_state

logger = logging.getLogger(__name__)


def route_after_review(state) -> Literal["organize", "revise", "human_flag"]:
    """条件路由：读 state["plan"]["max_iterations"]，不再硬编码 3"""
    plan = state.get("plan", {}) or {}
    max_iter = int(plan.get("max_iterations", 3))
    iteration = state.get("iteration", 0)

    if state["review_passed"]:
        return "organize"
    elif iteration >= max_iter:
        return "human_flag"
    else:
        return "revise"


def build_graph() -> StateGraph:
    graph = StateGraph(KBState)

    graph.add_node("plan", planner_node)
    graph.add_node("collect", collect_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("review", review_node)
    graph.add_node("revise", revise_node)
    graph.add_node("organize", organize_node)
    graph.add_node("human_flag", human_flag_node)

    graph.add_edge("plan", "collect")
    graph.add_edge("collect", "analyze")
    graph.add_edge("analyze", "review")

    graph.add_conditional_edges(
        "review",
        route_after_review,
        {
            "organize": "organize",
            "revise": "revise",
            "human_flag": "human_flag",
        },
    )

    graph.add_edge("revise", "review")

    graph.add_edge("organize", END)
    graph.add_edge("human_flag", END)

    graph.set_entry_point("plan")
    return graph

app = build_graph()

if __name__ == "__main__":
    from workflows.model_client import get_cost_guard, BudgetExceededError

    initial_state: KBState = {
        "sources": [], "analyses": [], "articles": [],
        "raw_items": [], "review_result": {},
        "review_feedback": "", "review_passed": False,
        "iteration": 0, "needs_human_review": False,
        "plan": {}, "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }

    try:
        final_state = app.compile().invoke(initial_state)
        print("\n=== 工作流完成 ===")
    except BudgetExceededError as e:
        print(f"\n[FATAL] 预算熔断触发：{e}")

    # ★ 接入点 ③ · 收尾打报告 · 落盘到 knowledge/cost-report.json
    guard = get_cost_guard()
    report = guard.get_report()
    print(f"\n[CostGuard] 总调用 {report['total_calls']} 次 · 总成本 ¥{report['total_cost']}")
    print(f"[CostGuard] 按节点：{report['by_node']}")
    guard.save_report("knowledge/cost-report.json")
