"""多 Agent 预算守卫模块。"""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from exceptions import BudgetExceededError


@dataclass
class CostRecord:
    """单次 LLM 调用记录。"""

    timestamp: datetime
    node_name: str
    prompt_tokens: int
    completion_tokens: int
    cost_yuan: float
    model: str = ""


class CostGuard:
    """多 Agent 预算守卫，提供三重保护机制。"""

    def __init__(
        self,
        budget_yuan: float = 1.0,
        alert_threshold: float = 0.8,
        input_price_per_million: float = 1.0,
        output_price_per_million: float = 2.0,
        budget_exceeded_error: type = BudgetExceededError,
    ):
        """初始化预算守卫。

        Args:
            budget_yuan: 预算金额（元）
            alert_threshold: 预警阈值（0-1）
            input_price_per_million: 输入价格（每百万 token）
            output_price_per_million: 输出价格（每百万 token）
            budget_exceeded_error: 预算超限时抛出的异常类
        """
        self.budget_yuan = budget_yuan
        self.alert_threshold = alert_threshold
        self.input_price_per_million = input_price_per_million
        self.output_price_per_million = output_price_per_million
        self.budget_exceeded_error = budget_exceeded_error

        self._records: list[CostRecord] = []
        self._total_cost_yuan: float = 0.0

    def record(
        self, node_name: str, usage: dict[str, int], model: str = ""
    ) -> CostRecord:
        """记录一次 LLM 调用的 token 用量。

        Args:
            node_name: 节点名称
            usage: 用量字典，包含 prompt_tokens 和 completion_tokens
            model: 模型名称

        Returns:
            生成的 CostRecord
        """
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        cost_yuan = (
            prompt_tokens * self.input_price_per_million / 1_000_000
            + completion_tokens * self.output_price_per_million / 1_000_000
        )

        record = CostRecord(
            timestamp=datetime.now(),
            node_name=node_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_yuan=cost_yuan,
            model=model,
        )

        self._records.append(record)
        self._total_cost_yuan += cost_yuan

        return record

    @property
    def total_prompt_tokens(self) -> int:
        """总输入 token 数。"""
        return sum(r.prompt_tokens for r in self._records)

    @property
    def total_completion_tokens(self) -> int:
        """总输出 token 数。"""
        return sum(r.completion_tokens for r in self._records)

    @property
    def total_cost_yuan(self) -> float:
        """总成本（元）。"""
        return self._total_cost_yuan

    def check(self) -> dict[str, Any]:
        """检查预算状态。

        Returns:
            预算状态字典

        Raises:
            BudgetExceededError: 超出预算时抛出
        """
        usage_ratio = self._total_cost_yuan / self.budget_yuan if self.budget_yuan > 0 else 0

        if usage_ratio >= 1.0:
            raise self.budget_exceeded_error(
                f"预算超限：已使用 {self._total_cost_yuan:.4f} 元，"
                f"预算 {self.budget_yuan:.4f} 元"
            )

        if usage_ratio >= self.alert_threshold:
            return {
                "status": "warning",
                "total_cost": self._total_cost_yuan,
                "budget": self.budget_yuan,
                "usage_ratio": usage_ratio,
                "message": f"预算使用率已达 {usage_ratio:.1%}，请注意",
            }

        return {
            "status": "ok",
            "total_cost": self._total_cost_yuan,
            "budget": self.budget_yuan,
            "usage_ratio": usage_ratio,
            "message": "预算使用正常",
        }

    def get_report(self) -> dict[str, Any]:
        """生成成本报告。

        Returns:
            成本报告字典
        """
        node_stats: dict[str, dict[str, Any]] = {}

        for record in self._records:
            if record.node_name not in node_stats:
                node_stats[record.node_name] = {
                    "call_count": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_cost": 0.0,
                    "models": set(),
                }

            stats = node_stats[record.node_name]
            stats["call_count"] += 1
            stats["prompt_tokens"] += record.prompt_tokens
            stats["completion_tokens"] += record.completion_tokens
            stats["total_cost"] += record.cost_yuan
            if record.model:
                stats["models"].add(record.model)

        for stats in node_stats.values():
            stats["models"] = list(stats["models"])

        return {
            "total_cost": self._total_cost_yuan,
            "budget": self.budget_yuan,
            "usage_ratio": self._total_cost_yuan / self.budget_yuan if self.budget_yuan > 0 else 0,
            "total_calls": len(self._records),
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "by_node": node_stats,
        }

    def save_report(self, path: str = None) -> str:
        """保存成本报告到 JSON 文件。

        Args:
            path: 文件路径，默认保存到 temp 文件

        Returns:
            保存的文件路径
        """
        report = self.get_report()

        if path is None:
            path = f"cost_report_{int(time.time())}.json"

        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        return path


if __name__ == "__main__":
    print("=" * 50)
    print("CostGuard 测试")
    print("=" * 50)

    guard = CostGuard(budget_yuan=1.0, alert_threshold=0.8)

    print("\n[测试 1] 成本追踪正确")
    guard.record("collector", {"prompt_tokens": 1000, "completion_tokens": 500})
    guard.record("analyzer", {"prompt_tokens": 2000, "completion_tokens": 1000})
    print(f"  total_prompt_tokens: {guard.total_prompt_tokens}")
    print(f"  total_cost_yuan: {guard.total_cost_yuan:.6f}")
    assert guard.total_prompt_tokens == 3000
    cost = guard.total_cost_yuan
    assert cost > 0
    print(f"  ✓ 测试通过")

    print("\n[测试 2] 预算超限检测")
    guard2 = CostGuard(budget_yuan=0.01, alert_threshold=0.8)
    guard2.record("test", {"prompt_tokens": 10000, "completion_tokens": 5000})
    try:
        guard2.check()
        print("  ✗ 应该抛出异常但没有")
        assert False
    except BudgetExceededError as e:
        print(f"  异常信息: {e}")
        print(f"  ✓ 测试通过")

    print("\n[测试 3] 预警阈值触发")
    guard3 = CostGuard(budget_yuan=1.0, alert_threshold=0.8)
    guard3.record("collector", {"prompt_tokens": 800000, "completion_tokens": 0})
    result = guard3.check()
    print(f"  status: {result['status']}")
    print(f"  usage_ratio: {result['usage_ratio']:.2f}")
    assert result["status"] == "warning"
    assert result["usage_ratio"] >= 0.8
    print(f"  ✓ 测试通过")

    print("\n[测试 4] 成本报告生成")
    guard4 = CostGuard(budget_yuan=1.0, alert_threshold=0.8)
    guard4.record("collector", {"prompt_tokens": 1000, "completion_tokens": 500}, "gpt-4")
    guard4.record("analyzer", {"prompt_tokens": 2000, "completion_tokens": 1000}, "gpt-4")
    report = guard4.get_report()
    print(f"  total_calls: {report['total_calls']}")
    print(f"  by_node keys: {list(report['by_node'].keys())}")
    assert report["total_calls"] == 2
    assert "collector" in report["by_node"]
    assert "analyzer" in report["by_node"]
    print(f"  ✓ 测试通过")

    print("\n[测试 5] 保存报告到文件")
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = tmp.name
    saved_path = guard4.save_report(tmp_path)
    with open(saved_path, "r") as f:
        loaded = json.load(f)
    print(f"  保存路径: {saved_path}")
    print(f"  加载的 total_cost: {loaded['total_cost']}")
    assert loaded["total_cost"] == guard4.total_cost_yuan
    print(f"  ✓ 测试通过")

    print("\n" + "=" * 50)
    print("所有测试通过！")
    print("=" * 50)