"""Formatter 模块测试。"""

import json
import tempfile
import unittest
from pathlib import Path

from distribution.formatter import (
    _empty_digest,
    _escape_telegram,
    _feishu_header_template,
    _normalize_score,
    _score_emoji,
    generate_daily_digest,
    json_to_feishu,
    json_to_markdown,
    json_to_telegram,
)


class TestNormalizeScore(unittest.TestCase):
    """评分归一化测试。"""

    def test_decimal_format(self):
        self.assertAlmostEqual(_normalize_score(0.9), 0.9)
        self.assertAlmostEqual(_normalize_score(0.5), 0.5)

    def test_percentage_format(self):
        self.assertAlmostEqual(_normalize_score(90), 0.9)
        self.assertAlmostEqual(_normalize_score(50), 0.5)

    def test_capped_at_one(self):
        self.assertAlmostEqual(_normalize_score(150), 1.0)
        self.assertAlmostEqual(_normalize_score(200), 1.0)


class TestScoreEmoji(unittest.TestCase):
    """评分 emoji 测试。"""

    def test_high_score(self):
        self.assertEqual(_score_emoji(1.0), "🟢")
        self.assertEqual(_score_emoji(0.8), "🟢")
        self.assertEqual(_score_emoji(0.85), "🟢")

    def test_medium_score(self):
        self.assertEqual(_score_emoji(0.79), "🟡")
        self.assertEqual(_score_emoji(0.6), "🟡")
        self.assertEqual(_score_emoji(0.7), "🟡")

    def test_low_score(self):
        self.assertEqual(_score_emoji(0.59), "🔴")
        self.assertEqual(_score_emoji(0.0), "🔴")


class TestEscapeTelegram(unittest.TestCase):
    """Telegram 转义测试。"""

    def test_all_special_chars(self):
        text = r"_*[]()~`>#+-=|{}.!"
        result = _escape_telegram(text)
        for char in text:
            self.assertEqual(result.count(f"\\{char}"), 1)

    def test_no_special_chars(self):
        self.assertEqual(_escape_telegram("普通文本"), "普通文本")

    def test_mixed_content(self):
        result = _escape_telegram("测试[link](url) _bold_")
        self.assertIn(r"\[", result)
        self.assertIn(r"\]", result)
        self.assertIn(r"\_", result)


class TestFeishuHeaderTemplate(unittest.TestCase):
    """飞书 header 颜色测试。"""

    def test_green_header(self):
        self.assertEqual(_feishu_header_template(1.0), "green")
        self.assertEqual(_feishu_header_template(0.9), "green")
        self.assertEqual(_feishu_header_template(0.8), "green")

    def test_yellow_header(self):
        self.assertEqual(_feishu_header_template(0.79), "yellow")
        self.assertEqual(_feishu_header_template(0.6), "yellow")

    def test_red_header(self):
        self.assertEqual(_feishu_header_template(0.59), "red")
        self.assertEqual(_feishu_header_template(0.0), "red")


class TestJsonToMarkdown(unittest.TestCase):
    """Markdown 格式化测试。"""

    def setUp(self):
        self.article = {
            "id": "test-001",
            "title": "Test Project",
            "source": "github",
            "source_url": "https://github.com/test/project",
            "collected_at": "2026-04-11T16:03:47+00:00",
            "summary": "This is a test summary.",
            "tags": ["AI", "LLM"],
            "analysis": {"relevance_score": 0.9},
        }

    def test_full_article(self):
        result = json_to_markdown(self.article)
        self.assertIn("# Test Project", result)
        self.assertIn("**来源**: github", result)
        self.assertIn("**日期**: 2026-04-11", result)
        self.assertIn("🟢", result)
        self.assertIn("90%", result)
        self.assertIn("AI / LLM", result)
        self.assertIn("## 摘要", result)
        self.assertIn("This is a test summary.", result)
        self.assertIn("[查看原文](https://github.com/test/project)", result)

    def test_missing_optional_fields(self):
        article = {
            "id": "test-002",
            "title": "Minimal Article",
            "summary": "No other fields",
        }
        result = json_to_markdown(article)
        self.assertIn("# Minimal Article", result)
        self.assertIn("**来源**: unknown", result)
        self.assertIn("**标签**: 无", result)
        self.assertIn("🔴 0%", result)

    def test_no_source_url(self):
        article = {"id": "test", "title": "No URL", "summary": "test"}
        result = json_to_markdown(article)
        self.assertNotIn("[查看原文]", result)

    def test_url_field_name_compatibility(self):
        article = {
            "id": "test",
            "title": "URL compat",
            "url": "https://example.com",
            "summary": "test",
        }
        result = json_to_markdown(article)
        self.assertIn("https://example.com", result)


class TestJsonToTelegram(unittest.TestCase):
    """Telegram 格式化测试。"""

    def setUp(self):
        self.article = {
            "id": "test-001",
            "title": "Test Project",
            "source": "github",
            "source_url": "https://github.com/test/project",
            "collected_at": "2026-04-11T16:03:47+00:00",
            "summary": "Test summary.",
            "tags": ["AI", "LLM"],
            "analysis": {"relevance_score": 0.9},
        }

    def test_full_article(self):
        result = json_to_telegram(self.article)
        self.assertIn("*Test Project*", result)
        self.assertIn("🟢", result)
        self.assertIn("90%", result)
        self.assertIn("📡", result)
        self.assertIn("🏷️", result)
        self.assertIn("AI_LLM", result)
        self.assertIn("[🔗 原文链接]", result)

    def test_special_chars_escaped(self):
        article = {
            "id": "test",
            "title": "Test [link](url) _bold_",
            "source": "test-source",
            "summary": "Test [content] _here_",
            "analysis": {"relevance_score": 0.8},
        }
        result = json_to_telegram(article)
        self.assertIn(r"\[", result)
        self.assertIn(r"\_", result)
        self.assertIn(r"\]", result)

    def test_no_url(self):
        article = {"id": "test", "title": "No URL", "summary": "test", "analysis": {}}
        result = json_to_telegram(article)
        self.assertNotIn("原文链接", result)

    def test_percentage_normalized(self):
        article = {"id": "test", "title": "Test", "summary": "test", "analysis": {"relevance_score": 90}}
        result = json_to_telegram(article)
        self.assertIn("90%", result)


class TestJsonToFeishu(unittest.TestCase):
    """飞书卡片格式化测试。"""

    def setUp(self):
        self.article = {
            "id": "test-001",
            "title": "Test Project",
            "source": "github",
            "source_url": "https://github.com/test/project",
            "collected_at": "2026-04-11T16:03:47+00:00",
            "summary": "This is a test summary.",
            "tags": ["AI", "LLM"],
            "analysis": {"relevance_score": 0.9},
        }

    def test_full_article(self):
        result = json_to_feishu(self.article)
        self.assertEqual(result["msg_type"], "interactive")
        self.assertEqual(result["card"]["header"]["template"], "green")
        self.assertIn("查看原文", str(result["card"]["elements"]))

    def test_yellow_header_medium_score(self):
        article = self.article.copy()
        article["analysis"] = {"relevance_score": 0.7}
        result = json_to_feishu(article)
        self.assertEqual(result["card"]["header"]["template"], "yellow")

    def test_red_header_low_score(self):
        article = self.article.copy()
        article["analysis"] = {"relevance_score": 0.3}
        result = json_to_feishu(article)
        self.assertEqual(result["card"]["header"]["template"], "red")

    def test_no_url_no_button(self):
        article = {
            "id": "test",
            "title": "No URL",
            "summary": "test",
            "source": "test",
            "analysis": {},
        }
        result = json_to_feishu(article)
        elements = result["card"]["elements"]
        button_elements = [e for e in elements if e.get("tag") == "action"]
        self.assertEqual(len(button_elements), 0)

    def test_title_truncated(self):
        article = self.article.copy()
        article["title"] = "A" * 100
        result = json_to_feishu(article)
        self.assertEqual(len(result["card"]["header"]["title"]["content"]), 50)


class TestGenerateDailyDigest(unittest.TestCase):
    """每日简报生成测试。"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.articles_dir = Path(self.temp_dir)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.temp_dir)

    def _write_article(self, filename: str, content: dict):
        with open(self.articles_dir / filename, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False)

    def test_with_articles(self):
        self._write_article(
            "github-20260509-001.json",
            {
                "id": "github-20260509-001",
                "title": "Article A",
                "source": "github",
                "source_url": "https://example.com/a",
                "collected_at": "2026-05-09T10:00:00+00:00",
                "summary": "Summary A",
                "tags": ["AI"],
                "analysis": {"relevance_score": 0.8},
            },
        )
        self._write_article(
            "github-20260509-002.json",
            {
                "id": "github-20260509-002",
                "title": "Article B",
                "source": "github",
                "source_url": "https://example.com/b",
                "collected_at": "2026-05-09T11:00:00+00:00",
                "summary": "Summary B",
                "tags": ["ML"],
                "analysis": {"relevance_score": 0.6},
            },
        )
        result = generate_daily_digest(str(self.articles_dir), date="2026-05-09", top_n=5)

        self.assertIn("2026-05-09", result["markdown"])
        self.assertIn("Article A", result["markdown"])
        self.assertIn("Article B", result["telegram"])
        self.assertEqual(result["feishu"]["msg_type"], "interactive")

    def test_top_n_limit(self):
        for i in range(10):
            self._write_article(
                f"github-20260509-{i:03d}.json",
                {
                    "id": f"github-20260509-{i:03d}",
                    "title": f"Article {i}",
                    "source": "github",
                    "source_url": f"https://example.com/{i}",
                    "collected_at": "2026-05-09T10:00:00+00:00",
                    "summary": f"Summary {i}",
                    "tags": ["test"],
                    "analysis": {"relevance_score": 0.5 + i * 0.05},
                },
            )

        result = generate_daily_digest(str(self.articles_dir), date="2026-05-09", top_n=3)
        self.assertIn("Top 3", result["markdown"])
        self.assertIn("Article 9", result["markdown"])  # highest score

    def test_sorted_by_score(self):
        for i, score in enumerate([0.3, 0.8, 0.5]):
            self._write_article(
                f"github-20260509-{i:03d}.json",
                {
                    "id": f"github-20260509-{i:03d}",
                    "title": f"Article Score {score}",
                    "source": "github",
                    "source_url": "https://example.com",
                    "collected_at": "2026-05-09T10:00:00+00:00",
                    "summary": f"Summary {i}",
                    "tags": ["test"],
                    "analysis": {"relevance_score": score},
                },
            )

        result = generate_daily_digest(str(self.articles_dir), date="2026-05-09", top_n=3)
        markdown = result["markdown"]
        idx_a = markdown.find("Article Score 0.3")
        idx_b = markdown.find("Article Score 0.5")
        idx_c = markdown.find("Article Score 0.8")
        self.assertTrue(idx_c >= 0 and idx_c < idx_a and idx_c < idx_b)

    def test_empty_date_no_articles(self):
        result = generate_daily_digest(str(self.articles_dir), date="2026-01-01", top_n=5)
        self.assertIn("📭 2026-01-01 暂无新增知识条目", result["markdown"])
        self.assertEqual(result["feishu"]["card"]["header"]["template"], "grey")

    def test_different_date(self):
        self._write_article(
            "github-20260421-001.json",
            {
                "id": "github-20260421-001",
                "title": "Old Article",
                "source": "github",
                "collected_at": "2026-04-21T10:00:00+00:00",
                "summary": "Old summary",
                "analysis": {"relevance_score": 0.9},
            },
        )
        result = generate_daily_digest(str(self.articles_dir), date="2026-05-09", top_n=5)
        self.assertIn("暂无新增知识条目", result["markdown"])

    def test_ignores_index_json(self):
        self._write_article("index.json", {"articles": []})
        self._write_article(
            "github-20260509-001.json",
            {
                "id": "github-20260509-001",
                "title": "Real Article",
                "source": "github",
                "collected_at": "2026-05-09T10:00:00+00:00",
                "summary": "test",
                "analysis": {"relevance_score": 0.8},
            },
        )
        result = generate_daily_digest(str(self.articles_dir), date="2026-05-09", top_n=5)
        self.assertIn("Real Article", result["markdown"])

    def test_nonexistent_directory(self):
        result = generate_daily_digest("/nonexistent/path", date="2026-05-09", top_n=5)
        self.assertIn("暂无新增知识条目", result["markdown"])

    def test_skips_invalid_json(self):
        (self.articles_dir / "invalid.json").write_text("not valid json")
        self._write_article(
            "github-20260509-001.json",
            {
                "id": "github-20260509-001",
                "title": "Valid Article",
                "source": "github",
                "collected_at": "2026-05-09T10:00:00+00:00",
                "summary": "test",
                "analysis": {"relevance_score": 0.8},
            },
        )
        result = generate_daily_digest(str(self.articles_dir), date="2026-05-09", top_n=5)
        self.assertIn("Valid Article", result["markdown"])

    def test_all_channels_present(self):
        self._write_article(
            "github-20260509-001.json",
            {
                "id": "github-20260509-001",
                "title": "Test",
                "source": "github",
                "collected_at": "2026-05-09T10:00:00+00:00",
                "summary": "test",
                "analysis": {"relevance_score": 0.8},
            },
        )
        result = generate_daily_digest(str(self.articles_dir), date="2026-05-09", top_n=5)
        self.assertIn("markdown", result)
        self.assertIn("telegram", result)
        self.assertIn("feishu", result)
        self.assertIsInstance(result["feishu"], dict)


class TestEmptyDigest(unittest.TestCase):
    """空简报测试。"""

    def test_empty_digest_format(self):
        result = _empty_digest("2026-05-09")
        self.assertEqual(result["markdown"], "# 📭 2026-05-09 暂无新增知识条目")
        self.assertEqual(result["telegram"], "📭 *2026-05-09 暂无新增知识条目*")
        self.assertEqual(result["feishu"]["card"]["header"]["template"], "grey")


if __name__ == "__main__":
    unittest.main()