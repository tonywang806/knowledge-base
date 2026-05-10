"""pipeline.py 的回归测试。"""

from pipeline import pipeline


def test_step_analyze_uses_valid_fallback_summary_on_llm_failure(monkeypatch):
    """LLM 失败时也应生成满足 JSON 校验长度的摘要。"""

    def raise_error(_messages):
        raise RuntimeError("llm unavailable")

    monkeypatch.setattr(pipeline, "chat_with_retry", raise_error)

    result = pipeline.step_analyze([
        {
            "id": "raw-id",
            "title": "Test Agent Repo",
            "source": "github-search",
            "url": "https://github.com/example/test-agent-repo",
            "description": "A framework for building AI agents with tools.",
            "raw_content": "Test Agent Repo\nA framework for building AI agents with tools.",
            "collected_at": "2026-05-09T00:00:00",
        }
    ])

    assert len(result) == 1
    assert len(result[0]["summary"]) >= 20
    assert result[0]["summary"] != "[分析失败]"


def test_build_fallback_summary_is_always_validation_safe():
    """标题和描述都很短时，兜底摘要仍应满足最小长度。"""

    summary = pipeline.build_fallback_summary({"title": "AI"})

    assert len(summary) >= 20
