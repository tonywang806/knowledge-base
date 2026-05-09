"""LangGraph workflow graph definition."""
import logging
import sys
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).parent.parent))

from langgraph.graph import END, StateGraph

from workflows.nodes import analyze_node, collect_node, organize_node, review_node, save_node
from workflows.state import KBState

logger = logging.getLogger(__name__)


def review_router(state: KBState) -> Literal["save", "analyze"]:
    if state.review_passed:
        return "save"
    return "analyze"


def build_graph() -> StateGraph:
    graph = StateGraph(KBState)

    graph.add_node("collect", collect_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("organize", organize_node)
    graph.add_node("review", review_node)
    graph.add_node("save", save_node)

    graph.add_edge("collect", "analyze")
    graph.add_edge("analyze", "organize")
    graph.add_edge("organize", "review")

    graph.add_conditional_edges(
        "review",
        review_router,
        {
            "save": "save",
            "analyze": "analyze",
        },
    )

    graph.add_edge("save", END)

    graph.set_entry_point("collect")

    return graph.compile()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    app = build_graph()
    print("=" * 60)
    print("开始执行知识库采集工作流")
    print("=" * 60)

    initial_state = KBState(iteration=0)
    for state in app.stream(initial_state):
        node_name = next(iter(state.keys()))
        node_state = state[node_name]
        print(f"\n--- [{node_name}] ---")

        if node_name == "collect":
            print(f"采集条目数: {len(node_state.get('raw_items', []))}")
        elif node_name == "analyze":
            print(f"分析条目数: {len(node_state.get('analyses', []))}")
        elif node_name == "organize":
            print(f"整理后条目数: {len(node_state.get('articles', []))}")
        elif node_name == "review":
            passed = node_state.get("review_passed", False)
            avg = node_state.get("review_result", {}).get("avg_score", 0.0)
            print(f"审核通过: {passed}, 平均加权分: {avg:.2f}")
        elif node_name == "save":
            saved = (node_state or {}).get("saved_ids", [])
            print(f"保存条目: {len(saved)}")

    print("\n" + "=" * 60)
    print("工作流执行完成")
    print("=" * 60)
