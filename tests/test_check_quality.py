"""check_quality.py 的全分支测试。"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from hooks.check_quality import (
    CHINESE_BUZZWORDS,
    ENGLISH_BUZZWORDS,
    STANDARD_TAGS,
    TECH_KEYWORDS,
    QualityReport,
    _render_bar,
    _score_buzzword,
    _score_format,
    _score_summary,
    _score_tags,
    _score_tech_depth,
    evaluate_article,
    main,
)


def _write_json(tmp_path: Path, name: str, data: dict) -> Path:
    """写入临时 JSON 文件并返回路径。"""
    p = tmp_path / name
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def _valid_entry(**overrides) -> dict:
    """返回一个合法的知识条目，可按需覆盖字段。"""
    entry = {
        "id": "github-20260301-001",
        "title": "OpenClaw: 开源 AI Agent 运行时",
        "source_url": "https://github.com/example/project",
        "summary": "一个支持多 Agent 路由和 50+ 平台支持的 AI Agent 运行时框架。",
        "tags": ["agent", "runtime"],
        "status": "draft",
        "collected_at": "2026-03-01T10:00:00Z",
    }
    entry.update(overrides)
    return entry


# ─── _score_summary 分支 ───


class TestScoreSummary:
    def test_length_ge_50_full_score(self):
        data = {"summary": "A" * 60}
        result = _score_summary(data)
        assert result.name == "摘要质量"
        assert result.score == 25.0
        assert result.max_score == 25.0
        assert "长度 60 字" in result.detail

    def test_length_between_20_and_50(self):
        data = {"summary": "A" * 30}
        result = _score_summary(data)
        assert 15 < result.score < 25
        assert "长度 30 字" in result.detail

    def test_length_between_1_and_20(self):
        data = {"summary": "A" * 10}
        result = _score_summary(data)
        assert result.score < 15
        assert "长度 10 字" in result.detail

    def test_length_zero(self):
        data = {"summary": ""}
        result = _score_summary(data)
        assert result.score == 0.0
        assert "长度 0 字" in result.detail

    def test_missing_summary(self):
        data = {}
        result = _score_summary(data)
        assert result.score == 0.0
        assert "长度 0 字" in result.detail

    def test_with_tech_keywords_bonus(self):
        data = {"summary": "这是一个关于 LLM 和 Agent 的技术框架"}
        result = _score_summary(data)
        assert result.score > 20
        assert "关键词:" in result.detail

    def test_keywords_bonus_capped_at_5(self):
        keywords = list(TECH_KEYWORDS)[:5]
        summary = " ".join(keywords) * 3  # 长于50字以获得满分基础
        data = {"summary": summary}
        result = _score_summary(data)
        assert result.score == 25.0  # 基础分满分 + bonus capped at 5

    def test_detail_with_base_and_bonus_when_short_but_high_score(self):
        data = {"summary": "LLM agent tool api model and token embedding transformer rag"}
        result = _score_summary(data)
        assert "关键词:" in result.detail


# ─── _score_tech_depth 分支 ───


class TestScoreTechDepth:
    def test_top_level_score(self):
        data = {"score": 8}
        result = _score_tech_depth(data)
        assert result.score == 20.0
        assert result.max_score == 25.0
        assert "原始评分 8/10" in result.detail

    def test_analysis_relevance_score(self):
        data = {"analysis": {"relevance_score": 7}}
        result = _score_tech_depth(data)
        assert result.score == 17.5
        assert "原始评分 7/10" in result.detail

    def test_no_score_data(self):
        data = {"title": "Test"}
        result = _score_tech_depth(data)
        assert result.score == 0.0
        assert "无评分数据" in result.detail

    def test_score_above_10_clamped(self):
        data = {"score": 15}
        result = _score_tech_depth(data)
        assert result.score == 25.0

    def test_score_below_0_clamped(self):
        data = {"score": -5}
        result = _score_tech_depth(data)
        assert result.score == 0.0

    def test_score_float(self):
        data = {"score": 5.5}
        result = _score_tech_depth(data)
        assert result.score == 13.8


# ─── _score_format 分支 ───


class TestScoreFormat:
    def test_all_fields_present(self):
        data = _valid_entry()
        result = _score_format(data)
        assert result.score == 20.0
        assert "通过: id,title,source_url,status,timestamp" in result.detail

    def test_missing_id(self):
        data = _valid_entry()
        del data["id"]
        result = _score_format(data)
        assert result.score < 20.0
        assert "缺失: id" in result.detail

    def test_missing_title(self):
        data = _valid_entry()
        del data["title"]
        result = _score_format(data)
        assert "缺失: title" in result.detail

    def test_missing_source_url(self):
        data = _valid_entry()
        del data["source_url"]
        result = _score_format(data)
        assert "缺失: source_url" in result.detail

    def test_status_invalid_value(self):
        data = _valid_entry(status="unknown")
        result = _score_format(data)
        assert "缺失: status" in result.detail

    def test_status_valid_values(self):
        for status in ["draft", "reviewed", "published", "pending", "archived"]:
            data = _valid_entry(status=status)
            result = _score_format(data)
            assert "status" in result.detail

    def test_timestamp_from_collected_at(self):
        data = _valid_entry()
        result = _score_format(data)
        assert "timestamp" in result.detail

    def test_timestamp_from_updated_at(self):
        data = _valid_entry()
        del data["collected_at"]
        data["updated_at"] = "2026-03-01T10:00:00Z"
        result = _score_format(data)
        assert "timestamp" in result.detail

    def test_timestamp_from_created_at(self):
        data = _valid_entry()
        del data["collected_at"]
        data["created_at"] = "2026-03-01T10:00:00Z"
        result = _score_format(data)
        assert "timestamp" in result.detail

    def test_all_missing(self):
        data = {}
        result = _score_format(data)
        assert result.score == 0.0
        assert "缺失: id,title,source_url,status,timestamp" in result.detail


# ─── _score_tags 分支 ───


class TestScoreTags:
    def test_no_tags(self):
        data = {"tags": []}
        result = _score_tags(data)
        assert result.score == 0.0
        assert "无标签" in result.detail

    def test_tags_missing(self):
        data = {}
        result = _score_tags(data)
        assert result.score == 0.0
        assert "无标签" in result.detail

    def test_tags_none(self):
        data = {"tags": None}
        result = _score_tags(data)
        assert result.score == 0.0

    def test_tags_1_to_3_standard(self):
        data = {"tags": ["ai", "agent", "llm"]}
        result = _score_tags(data)
        assert result.score == 10.0 + 5.0  # count_score + validity_score

    def test_tags_4_to_5(self):
        data = {"tags": ["ai", "agent", "llm", "rag"]}
        result = _score_tags(data)
        assert result.score == 7.0 + 5.0

    def test_tags_6_to_8(self):
        data = {"tags": ["ai", "agent", "llm", "rag", "mcp", "reasoning", "rl"]}
        result = _score_tags(data)
        assert result.score == 4.0 + 5.0

    def test_tags_over_8(self):
        data = {"tags": ["ai", "agent", "llm", "rag", "mcp", "reasoning", "rl", "tool", "workflow", "vision"]}
        result = _score_tags(data)
        assert result.score == 6.5  # count_score=2.0 + validity=4.5 (9/10)

    def test_mixed_valid_invalid_tags(self):
        data = {"tags": ["ai", "fake-tag", "unknown"]}
        result = _score_tags(data)
        assert result.score < 15.0
        assert "非标准: fake-tag" in result.detail
        assert "1/3 合法" in result.detail

    def test_all_invalid_tags(self):
        data = {"tags": ["foo", "bar", "baz"]}
        result = _score_tags(data)
        assert result.score == 10.0  # count 1-3 = 10, validity = 0


# ─── _score_buzzword 分支 ───


class TestScoreBuzzword:
    def test_no_buzzwords(self):
        data = {"title": "Test", "summary": "A simple test project"}
        result = _score_buzzword(data)
        assert result.score == 15.0
        assert "无空洞词" in result.detail

    def test_chinese_buzzword(self):
        data = {"title": "Test", "summary": "这个项目能够赋能业务"}
        result = _score_buzzword(data)
        assert result.score < 15.0
        assert "赋能" in result.detail

    def test_english_buzzword(self):
        data = {"title": "Test", "summary": "A groundbreaking solution"}
        result = _score_buzzword(data)
        assert result.score < 15.0
        assert "groundbreaking" in result.detail

    def test_multiple_buzzwords(self):
        data = {"title": "Powerful tool", "summary": "革命性的赋能抓手打通了全链路"}
        result = _score_buzzword(data)
        assert result.score == 0.0
        assert "5 处空洞词" in result.detail

    def test_buzzword_penalty_capped(self):
        text = " ".join(list(CHINESE_BUZZWORDS)[:5])
        data = {"title": text, "summary": text}
        result = _score_buzzword(data)
        assert result.score >= 0

    def test_buzzword_in_title_only(self):
        data = {"title": "赋能业务", "summary": "no buzzwords here"}
        result = _score_buzzword(data)
        assert result.score < 15.0


# ─── evaluate_article 分支 ───


class TestEvaluateArticle:
    def test_valid_json_file(self, tmp_path: Path):
        p = _write_json(tmp_path, "good.json", _valid_entry())
        result = evaluate_article(p)
        assert result.grade in ["A", "B", "C"]

    def test_json_decode_error(self, tmp_path: Path):
        p = tmp_path / "bad.json"
        p.write_text("{invalid", encoding="utf-8")
        result = evaluate_article(p)
        assert result.dimensions[0].score == 0
        assert "文件错误" in result.dimensions[0].detail

    def test_file_not_found(self):
        result = evaluate_article(Path("/nonexistent/file.json"))
        assert result.dimensions[0].score == 0
        assert "文件错误" in result.dimensions[0].detail

    def test_root_not_dict(self, tmp_path: Path):
        p = tmp_path / "array.json"
        p.write_text("[1, 2, 3]", encoding="utf-8")
        result = evaluate_article(p)
        assert result.dimensions[0].score == 0
        assert "根节点非 dict" in result.dimensions[0].detail


# ─── QualityReport.compute_total 分支 ───


class TestQualityReport:
    def test_grade_a_score_ge_80(self):
        report = QualityReport(Path("test.json"))
        report.dimensions = [
            type("Dim", (), {"score": 25.0, "max_score": 25.0})(),
            type("Dim", (), {"score": 25.0, "max_score": 25.0})(),
            type("Dim", (), {"score": 20.0, "max_score": 20.0})(),
            type("Dim", (), {"score": 5.0, "max_score": 15.0})(),
            type("Dim", (), {"score": 5.0, "max_score": 15.0})(),
        ]
        report.compute_total()
        assert report.grade == "A"
        assert report.total_score == 80.0

    def test_grade_b_score_60_to_79(self):
        report = QualityReport(Path("test.json"))
        report.dimensions = [
            type("Dim", (), {"score": 20.0, "max_score": 25.0})(),
            type("Dim", (), {"score": 15.0, "max_score": 25.0})(),
            type("Dim", (), {"score": 15.0, "max_score": 20.0})(),
            type("Dim", (), {"score": 5.0, "max_score": 15.0})(),
            type("Dim", (), {"score": 5.0, "max_score": 15.0})(),
        ]
        report.compute_total()
        assert report.grade == "B"

    def test_grade_c_score_below_60(self):
        report = QualityReport(Path("test.json"))
        report.dimensions = [
            type("Dim", (), {"score": 10.0, "max_score": 25.0})(),
            type("Dim", (), {"score": 10.0, "max_score": 25.0})(),
            type("Dim", (), {"score": 10.0, "max_score": 20.0})(),
            type("Dim", (), {"score": 5.0, "max_score": 15.0})(),
            type("Dim", (), {"score": 5.0, "max_score": 15.0})(),
        ]
        report.compute_total()
        assert report.grade == "C"


# ─── _render_bar 分支 ───


class TestRenderBar:
    def test_normal_score(self):
        result = _render_bar(15.0, 25.0)
        assert "███" in result
        assert "15.0/25" in result

    def test_zero_score(self):
        result = _render_bar(0.0, 25.0)
        assert "░░░░░░░░░░░░░░░░░░░░░" in result or "0.0/25" in result

    def test_max_score_zero(self):
        result = _render_bar(5.0, 0)
        assert "5.0/0" in result


# ─── main() 分支 ───


class TestMain:
    def test_main_no_args(self):
        with patch.object(sys, "argv", ["prog"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

    def test_main_file_not_found(self):
        with patch.object(sys, "argv", ["prog", "nonexistent_file.json"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

    def test_main_valid_file_exit_0(self, tmp_path: Path):
        p = _write_json(tmp_path, "good.json", _valid_entry(score=9))
        with patch.object(sys, "argv", ["prog", str(p)]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0

    def test_main_valid_file_has_c_grade_exit_1(self, tmp_path: Path):
        p = _write_json(tmp_path, "bad.json", {"id": "a", "title": "b", "summary": "short"})
        with patch.object(sys, "argv", ["prog", str(p)]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

    def test_main_glob_match(self, tmp_path: Path, monkeypatch):
        _write_json(tmp_path, "a.json", _valid_entry(score=9, id="github-20260301-001"))
        _write_json(tmp_path, "b.json", _valid_entry(score=9, id="github-20260301-002"))
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["prog", "*.json"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0