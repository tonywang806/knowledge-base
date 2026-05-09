"""KBState definition for LangGraph workflow."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class KBState:
    plan: dict = field(default_factory=dict)
    iteration: int = 0
    raw_items: list[dict] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    analyses: list[dict] = field(default_factory=list)
    articles: list[dict] = field(default_factory=list)
    review_feedback: Optional[str] = None
    review_passed: bool = False
    review_result: dict = field(default_factory=dict)
    needs_human_review: bool = False
    usage: dict = field(
        default_factory=lambda: {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
    )

    def __post_init__(self):
        if isinstance(self.usage, dict) and "prompt_tokens" not in self.usage:
            self.usage = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }

    @property
    def cost_tracker(self) -> dict:
        return self.usage
