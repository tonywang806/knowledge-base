#!/usr/bin/env python3
"""知识条目 5 维度质量评分脚本。

支持单文件和多文件（通配符）输入模式，对每条知识条目从摘要质量、
技术深度、格式规范、标签精度、空洞词检测五个维度进行评分，
输出可视化进度条和等级判定。
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

CHINESE_BUZZWORDS: frozenset[str] = frozenset({
    "赋能", "抓手", "闭环", "打通", "全链路",
    "底层逻辑", "颗粒度", "对齐", "拉通", "沉淀",
    "强大的", "革命性的",
})

ENGLISH_BUZZWORDS: frozenset[str] = frozenset({
    "groundbreaking", "revolutionary", "game-changing",
    "cutting-edge", "world-class", "best-in-class",
    "next-generation", "industry-leading",
})

STANDARD_TAGS: frozenset[str] = frozenset({
    "ai", "agent", "llm", "rag", "mcp", "llmops",
    "reasoning", "rl", "self-evolving", "open-source",
    "vision", "coding", "multimodal", "inference",
    "training", "finetuning", "deployment", "benchmark",
    "safety", "alignment", "prompt", "workflow", "tool-use",
})

TECH_KEYWORDS: frozenset[str] = frozenset({
    "agent", "rag", "llm", "mcp", "api", "sdk",
    "模型", "推理", "训练", "微调", "部署", "编排",
    "token", "embedding", "transformer", "diffusion",
})

BUZZWORD_PATTERN = re.compile(
    "|".join(
        [re.escape(w) for w in CHINESE_BUZZWORDS]
        + [rf"\b{re.escape(w)}\b" for w in ENGLISH_BUZZWORDS]
    ),
    re.IGNORECASE,
)


@dataclass
class DimensionScore:
    """单个维度的评分结果。"""

    name: str
    score: float
    max_score: float
    detail: str = ""


@dataclass
class QualityReport:
    """知识条目的完整质量报告。"""

    path: Path
    dimensions: list[DimensionScore] = field(default_factory=list)
    total_score: float = 0.0
    grade: str = "C"

    def compute_total(self) -> None:
        """计算加权总分并判定等级。"""
        self.total_score = sum(d.score for d in self.dimensions)
        if self.total_score >= 80:
            self.grade = "A"
        elif self.total_score >= 60:
            self.grade = "B"
        else:
            self.grade = "C"


def _score_summary(data: dict) -> DimensionScore:
    """评分维度：摘要质量（满分 25）。"""
    summary = data.get("summary", "") or ""
    length = len(summary)
    max_score = 25.0

    if length >= 50:
        base = max_score
    elif length >= 20:
        ratio = (length - 20) / 30
        base = 15 + ratio * 10
    else:
        ratio = length / 20 if length > 0 else 0
        base = ratio * 15

    bonus = 0.0
    matched = [kw for kw in TECH_KEYWORDS if kw in summary.lower()]
    if matched:
        bonus = min(5.0, 2.5 * len(matched))

    score = min(max_score, base + bonus)
    detail = f"长度 {length} 字"
    if matched:
        detail += f"，关键词: {','.join(matched)}"
    if score >= 50 and length < 50:
        detail += f"，基础分 {base:.1f} + 关键词奖励 {bonus:.1f}"

    return DimensionScore("摘要质量", round(score, 1), max_score, detail)


def _score_tech_depth(data: dict) -> DimensionScore:
    """评分维度：技术深度（满分 25）。"""
    max_score = 25.0
    score_val = None

    if "score" in data and isinstance(data["score"], (int, float)):
        score_val = data["score"]
    elif "analysis" in data and isinstance(data["analysis"], dict):
        score_val = data["analysis"].get("relevance_score")

    if score_val is None:
        return DimensionScore("技术深度", 0.0, max_score, "无评分数据")

    score_val = max(0, min(10, score_val))
    mapped = score_val / 10 * max_score
    return DimensionScore("技术深度", round(mapped, 1), max_score, f"原始评分 {score_val}/10")


def _score_format(data: dict) -> DimensionScore:
    """评分维度：格式规范（满分 20）。"""
    max_score = 20.0
    checks: list[tuple[str, bool]] = [
        ("id", bool(data.get("id"))),
        ("title", bool(data.get("title"))),
        ("source_url", bool(data.get("source_url"))),
        ("status", data.get("status") in {"draft", "reviewed", "published", "pending", "archived"}),
        ("timestamp", bool(data.get("collected_at") or data.get("updated_at") or data.get("created_at"))),
    ]

    per_item = max_score / len(checks)
    scored = sum(per_item for _, ok in checks if ok)
    passed = [name for name, ok in checks if ok]
    failed = [name for name, ok in checks if not ok]

    detail = f"通过: {','.join(passed)}" if passed else ""
    if failed:
        detail += f" 缺失: {','.join(failed)}"

    return DimensionScore("格式规范", round(scored, 1), max_score, detail.strip())


def _score_tags(data: dict) -> DimensionScore:
    """评分维度：标签精度（满分 15）。"""
    max_score = 15.0
    tags = data.get("tags", []) or []

    if not tags:
        return DimensionScore("标签精度", 0.0, max_score, "无标签")

    valid_count = sum(1 for t in tags if t in STANDARD_TAGS)
    total_count = len(tags)

    if 1 <= total_count <= 3:
        count_score = 10.0
    elif total_count <= 5:
        count_score = 7.0
    elif total_count <= 8:
        count_score = 4.0
    else:
        count_score = 2.0

    validity_ratio = valid_count / total_count if total_count > 0 else 0
    validity_score = 5.0 * validity_ratio

    score = min(max_score, count_score + validity_score)
    invalid = [t for t in tags if t not in STANDARD_TAGS]
    detail = f"{valid_count}/{total_count} 合法"
    if invalid:
        detail += f"，非标准: {','.join(invalid[:3])}"

    return DimensionScore("标签精度", round(score, 1), max_score, detail)


def _score_buzzword(data: dict) -> DimensionScore:
    """评分维度：空洞词检测（满分 15）。"""
    max_score = 15.0
    summary = data.get("summary", "") or ""
    title = data.get("title", "") or ""
    text = f"{title} {summary}"

    found = BUZZWORD_PATTERN.findall(text)
    if not found:
        return DimensionScore("空洞词检测", max_score, max_score, "无空洞词")

    penalty = min(max_score, len(found) * 5.0)
    score = max(0, max_score - penalty)
    unique = list(dict.fromkeys(found))
    detail = f"检测到 {len(found)} 处空洞词: {','.join(unique[:5])}"

    return DimensionScore("空洞词检测", round(score, 1), max_score, detail)


def evaluate_article(path: Path) -> QualityReport:
    """对单个知识条目进行 5 维度评分。"""
    report = QualityReport(path=path)

    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except (json.JSONDecodeError, OSError) as exc:
        report.dimensions = [
            DimensionScore("摘要质量", 0, 25, f"文件错误: {exc}"),
            DimensionScore("技术深度", 0, 25, "文件错误"),
            DimensionScore("格式规范", 0, 20, "文件错误"),
            DimensionScore("标签精度", 0, 15, "文件错误"),
            DimensionScore("空洞词检测", 0, 15, "文件错误"),
        ]
        report.compute_total()
        return report

    if not isinstance(data, dict):
        report.dimensions = [
            DimensionScore("摘要质量", 0, 25, "根节点非 dict"),
            DimensionScore("技术深度", 0, 25, "根节点非 dict"),
            DimensionScore("格式规范", 0, 20, "根节点非 dict"),
            DimensionScore("标签精度", 0, 15, "根节点非 dict"),
            DimensionScore("空洞词检测", 0, 15, "根节点非 dict"),
        ]
        report.compute_total()
        return report

    report.dimensions = [
        _score_summary(data),
        _score_tech_depth(data),
        _score_format(data),
        _score_tags(data),
        _score_buzzword(data),
    ]
    report.compute_total()
    return report


def _render_bar(score: float, max_score: float, width: int = 20) -> str:
    """渲染可视化进度条。"""
    filled = int(width * score / max_score) if max_score > 0 else 0
    filled = max(0, min(width, filled))
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {score:5.1f}/{max_score:.0f}"


def print_report(report: QualityReport) -> None:
    """打印单条报告。"""
    grade_color = {"A": "\033[32m", "B": "\033[33m", "C": "\033[31m"}
    grade_reset = "\033[0m"

    print(f"\n{'─' * 60}")
    print(f"📄 {report.path.name}")
    print(f"{'─' * 60}")

    for dim in report.dimensions:
        print(f"  {dim.name:8s} {_render_bar(dim.score, dim.max_score)}  {dim.detail}")

    color = grade_color.get(report.grade, "")
    reset = "\033[0m"
    print(f"{'─' * 60}")
    print(f"  总分: {report.total_score:5.1f}/100  等级: {color}{report.grade}{reset}")


def main() -> None:
    """入口函数。"""
    if len(sys.argv) < 2:
        print(f"用法: {sys.argv[0]} <json_file> [json_file2 ...]", file=sys.stderr)
        print("支持通配符: *.json", file=sys.stderr)
        sys.exit(1)

    file_paths: list[Path] = []
    for spec in sys.argv[1:]:
        p = Path(spec)
        if p.exists():
            file_paths.append(p)
        else:
            matched = sorted(Path(".").glob(spec))
            if matched:
                file_paths.extend(matched)
            else:
                print(f"错误: 文件不存在: {spec}", file=sys.stderr)
                sys.exit(1)

    if not file_paths:
        print("错误: 没有匹配到任何文件", file=sys.stderr)
        sys.exit(1)

    reports: list[QualityReport] = []
    for fp in file_paths:
        report = evaluate_article(fp)
        reports.append(report)
        print_report(report)

    has_c = any(r.grade == "C" for r in reports)

    print(f"\n{'=' * 60}")
    a_count = sum(1 for r in reports if r.grade == "A")
    b_count = sum(1 for r in reports if r.grade == "B")
    c_count = sum(1 for r in reports if r.grade == "C")
    print(f"汇总: {len(reports)} 篇 | A:{a_count}  B:{b_count}  C:{c_count}")
    print(f"{'=' * 60}")

    sys.exit(1 if has_c else 0)


if __name__ == "__main__":
    main()