"""AI 知识库评估测试。"""

import json
import re
import warnings
from pathlib import Path

import pytest

warnings.filterwarnings("ignore", category=pytest.PytestUnknownMarkWarning)

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from workflows.model_client import chat


EVAL_CASES = [
    {
        "name": "正面：技术文章",
        "input": "LangGraph v0.3 发布：新增多 Agent 协作工作流支持，支持并行任务执行和状态持久化，适合构建复杂 Agent 系统。GitHub Star 突破 50k。",
        "expected": {
            "has_summary": lambda x: len(x) >= 20,
            "has_keywords": lambda x: any(k in x for k in ["Agent", "LangGraph", "工作流", "llm"]),
            "relevance_score_range": lambda x: 5 <= x <= 10,
        },
    },
    {
        "name": "负面：无关内容",
        "input": "今天天气很好，适合去公园散步。",
        "expected": {
            "relevance_score_range": lambda x: 1 <= x <= 5,
            "not_tech_content": lambda x: not any(k in x for k in ["Agent", "LLM", "AI", "model"]),
        },
    },
    {
        "name": "边界：极短输入",
        "input": "AI",
        "expected": {
            "not_crash": lambda x: True,
            "has_summary": lambda x: len(x) >= 10,
        },
    },
]

SYSTEM_PROMPT = """你是一个 AI 知识库分析助手。给定输入内容，返回一个 JSON：
{
  "summary": "一句话摘要（20字以上）",
  "keywords": ["关键词1", "关键词2"],
  "relevance_score": 7
}
- relevance_score: 1-10，AI/Agent/LLM 相关性"""

SYSTEM_JUDGE = """你是一个评判专家。分析以下内容质量并打分（1-10）：
- 7-10：高质量，有技术价值
- 5-6：中等质量
- 1-4：低质量或无关内容

只返回一个整数分数。"""


def _parse_llm_json_response(text: str) -> dict:
    """解析 LLM 返回的 JSON 文本。"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:]) if lines else text
        text = text.strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group())
    return {}


def _check_case(result_text: str, case: dict) -> dict:
    """对单个 case 执行所有期望检查。"""
    checks = case["expected"]
    results = {}
    for key, check in checks.items():
        try:
            results[key] = check(result_text)
        except Exception:
            results[key] = False
    return results


class TestEvalCasesStructure:
    """验证 EVAL_CASES 结构完整性（不调用 LLM）。"""

    def test_has_at_least_3_cases(self):
        assert len(EVAL_CASES) >= 3

    def test_each_case_has_required_fields(self):
        for case in EVAL_CASES:
            assert "name" in case, f"Missing name in {case}"
            assert "input" in case, f"Missing input in {case}"
            assert "expected" in case, f"Missing expected in {case}"

    def test_each_case_expected_is_dict(self):
        for case in EVAL_CASES:
            assert isinstance(case["expected"], dict), f"expected must be dict: {case}"

    def test_cases_cover_positive_negative_edge(self):
        names = [c["name"] for c in EVAL_CASES]
        assert any("正面" in n for n in names)
        assert any("负面" in n for n in names)
        assert any("边界" in n for n in names)


class TestPositiveCase:
    """正面案例测试。"""

    @pytest.mark.slow
    def test_technical_article_generates_summary(self):
        case = next(c for c in EVAL_CASES if "正面" in c["name"])
        prompt = f"{SYSTEM_PROMPT}\n\n输入：{case['input']}"
        text, _ = chat(prompt, system="你是一个 AI 知识库分析助手。")
        assert "summary" in text.lower() or len(text) >= 20

    @pytest.mark.slow
    def test_technical_article_has_keywords(self):
        case = next(c for c in EVAL_CASES if "正面" in c["name"])
        prompt = f"{SYSTEM_PROMPT}\n\n输入：{case['input']}"
        text, _ = chat(prompt, system="你是一个 AI 知识库分析助手。")
        check_results = _check_case(text, case)
        assert check_results.get("has_keywords", False), f"No keywords found in: {text[:200]}"


class TestNegativeCase:
    """负面案例测试。"""

    @pytest.mark.slow
    def test_irrelevant_content_low_score(self):
        case = next(c for c in EVAL_CASES if "负面" in c["name"])
        prompt = f"{SYSTEM_PROMPT}\n\n输入：{case['input']}"
        text, _ = chat(prompt, system="你是一个 AI 知识库分析助手。")
        parsed = _parse_llm_json_response(text)
        score = parsed.get("relevance_score", 5)
        assert score <= 5, f"Expected low score for irrelevant content, got {score}"


class TestEdgeCase:
    """边界案例测试。"""

    @pytest.mark.slow
    def test_short_input_no_crash(self):
        case = next(c for c in EVAL_CASES if "边界" in c["name"])
        prompt = f"{SYSTEM_PROMPT}\n\n输入：{case['input']}"
        try:
            text, _ = chat(prompt, system="你是一个 AI 知识库分析助手。")
            assert text is not None
            assert len(text) >= 5
        except Exception as e:
            pytest.fail(f"Should not crash on short input: {e}")


class TestLLMasJudge:
    """LLM-as-Judge 测试。"""

    @pytest.mark.slow
    def test_llm_judge_scores_above_threshold(self):
        case = next(c for c in EVAL_CASES if "正面" in c["name"])
        prompt = f"{SYSTEM_PROMPT}\n\n输入：{case['input']}"
        result_text, _ = chat(prompt, system="你是一个 AI 知识库分析助手。")

        judge_prompt = f"{SYSTEM_JUDGE}\n\n内容：{result_text[:500]}"
        score_text, _ = chat(judge_prompt, system="你是一个评判专家。")

        score_match = re.search(r"\d+", score_text.strip())
        assert score_match, f"Cannot parse score from: {score_text}"
        score = int(score_match.group())
        assert score >= 5, f"LLM judge score {score} < 5 for content: {result_text[:200]}"

    @pytest.mark.slow
    def test_judge_scores_negative_case_lower_than_positive(self):
        pos_case = next(c for c in EVAL_CASES if "正面" in c["name"])
        neg_case = next(c for c in EVAL_CASES if "负面" in c["name"])

        pos_prompt = f"{SYSTEM_PROMPT}\n\n输入：{pos_case['input']}"
        pos_result, _ = chat(pos_prompt, system="你是一个 AI 知识库分析助手。")

        neg_prompt = f"{SYSTEM_PROMPT}\n\n输入：{neg_case['input']}"
        neg_result, _ = chat(neg_prompt, system="你是一个 AI 知识库分析助手。")

        def get_score(text):
            judge_prompt = f"{SYSTEM_JUDGE}\n\n内容：{text[:500]}"
            score_text, _ = chat(judge_prompt, system="你是一个评判专家。")
            match = re.search(r"\d+", score_text.strip())
            return int(match.group()) if match else 0

        pos_score = get_score(pos_result)
        neg_score = get_score(neg_result)
        assert pos_score >= neg_score, f"Positive score {pos_score} should >= Negative score {neg_score}"


class TestLocalValidation:
    """本地验证测试（不调用 LLM）。"""

    def test_eval_cases_loaded_successfully(self):
        assert len(EVAL_CASES) > 0

    def test_expected_checks_are_callable(self):
        for case in EVAL_CASES:
            for key, check in case["expected"].items():
                assert callable(check), f"{key} must be callable in {case['name']}"

    def test_relavance_score_range_checks_are_valid(self):
        for case in EVAL_CASES:
            for key, check in case["expected"].items():
                if "range" in key:
                    assert check(5) is True, f"Range check failed for value 5"
                    assert check(0) is False, f"Range check failed for value 0"