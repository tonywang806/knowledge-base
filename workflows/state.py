"""KBState definition for LangGraph workflow."""
from typing import Any, TypedDict


class KBState(TypedDict):
    plan: dict[str, Any]
    iteration: int
    raw_items: list[dict]
    sources: list[dict]
    analyses: list[dict]
    articles: list[dict]
    review_feedback: str | None
    review_passed: bool
    review_result: dict
    needs_human_review: bool
    usage: dict[str, int]


def new_state(**kwargs) -> KBState:
    defaults: KBState = {
        "plan": {},
        "iteration": 0,
        "raw_items": [],
        "sources": [],
        "analyses": [],
        "articles": [],
        "review_feedback": None,
        "review_passed": False,
        "review_result": {},
        "needs_human_review": False,
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
    defaults.update(kwargs)
    return defaults
