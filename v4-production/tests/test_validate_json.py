"""validate_json.py 的全分支测试。"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from hooks.validate_json import ID_PATTERN, JsonValidator, validate_files, main


def _write_json(tmp_path: Path, name: str, data: dict) -> Path:
    """写入临时 JSON 文件并返回路径。"""
    p = tmp_path / name
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def _valid_entry(**overrides) -> dict:
    """返回一个合法的知识条目，可按需覆盖字段。"""
    entry = {
        "id": "github-20260301-001",
        "title": "Test Title",
        "source_url": "https://github.com/example/project",
        "summary": "A" * 25,
        "tags": ["python", "ai"],
        "status": "draft",
    }
    entry.update(overrides)
    return entry


# ─── _check_parse 分支 ───


class TestCheckParse:
    def test_parse_valid_json(self, tmp_path: Path):
        p = _write_json(tmp_path, "ok.json", _valid_entry())
        v = JsonValidator(p)
        assert v.validate() is True
        assert v.errors == []

    def test_parse_json_error_with_lineno_col(self, tmp_path: Path):
        p = tmp_path / "bad.json"
        p.write_text("{invalid json", encoding="utf-8")
        v = JsonValidator(p)
        v.validate()
        has_parse = any("json_parse_error" in e for e in v.errors)
        assert has_parse

    def test_parse_json_error_without_colno(self, tmp_path: Path):
        p = tmp_path / "bad2.json"
        p.write_text('{"key": }', encoding="utf-8")
        v = JsonValidator(p)
        v.validate()
        has_parse = any("json_parse_error" in e for e in v.errors)
        assert has_parse

    def test_parse_os_error(self):
        v = JsonValidator(Path("/nonexistent/path/no_such_file.json"))
        v.validate()
        has_file_error = any("file_error" in e for e in v.errors)
        assert has_file_error

    def test_parse_root_not_dict(self, tmp_path: Path):
        p = tmp_path / "array.json"
        p.write_text("[1, 2, 3]", encoding="utf-8")
        v = JsonValidator(p)
        assert v._check_parse() is None
        assert any("根节点必须是 JSON 对象" in e for e in v.errors)


# ─── _check_required_fields 分支 ───


class TestRequiredFields:
    def test_all_required_fields_present(self, tmp_path: Path):
        p = _write_json(tmp_path, "all_ok.json", _valid_entry())
        v = JsonValidator(p)
        assert v.validate() is True

    def test_missing_required_fields(self, tmp_path: Path):
        p = _write_json(tmp_path, "empty.json", {})
        v = JsonValidator(p)
        v.validate()
        missing = [e for e in v.errors if "missing_field" in e]
        assert len(missing) == 6

    def test_type_error_on_required_field(self, tmp_path: Path):
        p = _write_json(tmp_path, "type_err.json", _valid_entry(summary=12345))
        v = JsonValidator(p)
        v.validate()
        has_type = any("type_error" in e and "summary" in e for e in v.errors)
        assert has_type

    def test_summary_min_length_violated(self, tmp_path: Path):
        p = _write_json(tmp_path, "short.json", _valid_entry(summary="hi"))
        v = JsonValidator(p)
        v.validate()
        has_min = any("constraint_error" in e and "summary" in e and "最少" in e for e in v.errors)
        assert has_min

    def test_tags_min_items_violated(self, tmp_path: Path):
        p = _write_json(tmp_path, "empty_tags.json", _valid_entry(tags=[]))
        v = JsonValidator(p)
        v.validate()
        has_min = any("constraint_error" in e and "tags" in e and "至少" in e for e in v.errors)
        assert has_min

    def test_status_allowed_constraint(self, tmp_path: Path):
        p = _write_json(tmp_path, "bad_status.json", _valid_entry(status="unknown"))
        v = JsonValidator(p)
        v.validate()
        has_allowed = any("constraint_error" in e and "status" in e and "之一" in e for e in v.errors)
        assert has_allowed

    def test_id_format_invalid(self, tmp_path: Path):
        p = _write_json(tmp_path, "bad_id.json", _valid_entry(id="INVALID-ID"))
        v = JsonValidator(p)
        v.validate()
        has_id = any("constraint_error" in e and "id" in e and "格式错误" in e for e in v.errors)
        assert has_id

    def test_source_url_format_invalid(self, tmp_path: Path):
        p = _write_json(tmp_path, "bad_url.json", _valid_entry(source_url="ftp://bad.url"))
        v = JsonValidator(p)
        v.validate()
        has_url = any("constraint_error" in e and "source_url" in e and "格式错误" in e for e in v.errors)
        assert has_url

    def test_data_is_none_reports_missing(self):
        v = JsonValidator(Path("/nonexistent.json"))
        v._data = None
        v._check_required_fields()
        missing = [e for e in v.errors if "missing_field" in e]
        assert len(missing) == 6

    def test_multiple_errors_collected(self, tmp_path: Path):
        data = _valid_entry(summary="hi", tags=[], status="bad", id="bad-id", source_url="nope")
        p = _write_json(tmp_path, "multi.json", data)
        v = JsonValidator(p)
        v.validate()
        assert len(v.errors) >= 5


# ─── _check_optional_fields 分支 ───


class TestOptionalFields:
    def test_optional_fields_valid(self, tmp_path: Path):
        p = _write_json(tmp_path, "opt_ok.json", _valid_entry(score=7, audience="advanced"))
        v = JsonValidator(p)
        assert v.validate() is True

    def test_optional_fields_absent_is_ok(self, tmp_path: Path):
        p = _write_json(tmp_path, "no_opt.json", _valid_entry())
        v = JsonValidator(p)
        assert v.validate() is True

    def test_optional_score_too_low(self, tmp_path: Path):
        p = _write_json(tmp_path, "low.json", _valid_entry(score=0))
        v = JsonValidator(p)
        v.validate()
        has_min = any("constraint_error" in e and "score" in e and "最小值" in e for e in v.errors)
        assert has_min

    def test_optional_score_too_high(self, tmp_path: Path):
        p = _write_json(tmp_path, "high.json", _valid_entry(score=11))
        v = JsonValidator(p)
        v.validate()
        has_max = any("constraint_error" in e and "score" in e and "最大值" in e for e in v.errors)
        assert has_max

    def test_optional_audience_invalid(self, tmp_path: Path):
        p = _write_json(tmp_path, "aud.json", _valid_entry(audience="expert"))
        v = JsonValidator(p)
        v.validate()
        has_allowed = any("constraint_error" in e and "audience" in e and "之一" in e for e in v.errors)
        assert has_allowed

    def test_optional_type_error(self, tmp_path: Path):
        p = _write_json(tmp_path, "otype.json", _valid_entry(score="seven"))
        v = JsonValidator(p)
        v.validate()
        has_type = any("type_error" in e and "score" in e for e in v.errors)
        assert has_type

    def test_optional_data_none_skips(self):
        v = JsonValidator(Path("/nonexistent.json"))
        v._data = None
        v._check_optional_fields()
        assert v.errors == []


# ─── validate_files 分支 ───


class TestValidateFiles:
    def test_validate_all_pass(self, tmp_path: Path):
        p1 = _write_json(tmp_path, "a.json", _valid_entry(id="github-20260301-001"))
        p2 = _write_json(tmp_path, "b.json", _valid_entry(id="github-20260301-002"))
        pass_c, fail_c, err_c = validate_files([p1, p2])
        assert pass_c == 2
        assert fail_c == 0
        assert err_c == 0

    def test_validate_mixed(self, tmp_path: Path, capsys):
        good = _write_json(tmp_path, "good.json", _valid_entry())
        bad = _write_json(tmp_path, "bad.json", {"bad": "data"})
        pass_c, fail_c, err_c = validate_files([good, bad])
        assert pass_c == 1
        assert fail_c == 1
        assert err_c > 0


# ─── main() 分支 ───


class TestMain:
    def test_main_no_args(self):
        with patch.object(sys, "argv", ["prog"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

    def test_main_existing_file(self, tmp_path: Path):
        p = _write_json(tmp_path, "ok.json", _valid_entry())
        with patch.object(sys, "argv", ["prog", str(p)]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0

    def test_main_glob_match(self, tmp_path: Path, monkeypatch):
        _write_json(tmp_path, "a.json", _valid_entry(id="github-20260301-001"))
        _write_json(tmp_path, "b.json", _valid_entry(id="github-20260301-002"))
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["prog", "*.json"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0

    def test_main_file_not_found(self):
        with patch.object(sys, "argv", ["prog", "nonexistent_file.json"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

    def test_main_failure_exit_code(self, tmp_path: Path):
        p = _write_json(tmp_path, "bad.json", {"bad": "data"})
        with patch.object(sys, "argv", ["prog", str(p)]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1


# ─── ID_PATTERN 单元测试 ───


class TestIDPattern:
    @pytest.mark.parametrize(
        "id_str,valid",
        [
            ("github-20260301-001", True),
            ("hn-20260101-999", True),
            ("arxiv-20260301-001", True),
            ("multi-word-src-20260301-001", True),
            ("INVALID", False),
            ("github-2026-001", False),
            ("github-20260301-1", False),
            ("GITHUB-20260301-001", False),
            ("github_20260301_001", False),
            ("", False),
        ],
    )
    def test_id_pattern(self, id_str: str, valid: bool):
        assert bool(ID_PATTERN.match(id_str)) is valid