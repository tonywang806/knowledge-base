#!/usr/bin/env python3
"""校验知识条目 JSON 文件的格式和内容。

支持单文件和多文件（通配符）输入模式，检查必填字段、类型、
ID 格式、URL 格式、状态枚举、摘要和标签约束，以及可选字段的值域。
"""

from __future__ import annotations

import json
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any


# 必填字段: 名 -> (类型, 约束)
# 约束为可选 dict，不同字段支持不同的约束条件
REQUIRED_FIELDS: dict[str, tuple[type, dict[str, Any] | None]] = {
    "id": (str, None),
    "title": (str, None),
    "source_url": (str, None),
    "summary": (str, {"min_length": 20}),
    "tags": (list, {"min_items": 1}),
    "status": (str, {"allowed": ["draft", "review", "published", "archived"]}),
}

# 可选字段
OPTIONAL_FIELDS: dict[str, tuple[type, dict[str, Any] | None]] = {
    "score": (int, {"min": 1, "max": 10}),
    "audience": (str, {"allowed": ["beginner", "intermediate", "advanced"]}),
}

# ID 格式: {source}-{YYYYMMDD}-{NNN}
ID_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*-\d{8}-\d{3}$")

# URL 格式
URL_PATTERN = re.compile(r"^https?://")


class JsonValidator:
    """单文件 JSON 校验器，收集所有错误并提供校验结果。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.errors: list[str] = []

    def _add_error(self, line: int | None, code: str, detail: str) -> None:
        # line 为 None 表示顶层（如文件级错误、缺失字段）
        line_label = "?" if line is None else str(line)
        self.errors.append(f"[{line_label}] {code}: {detail}")

    def validate(self) -> bool:
        """执行全部检查，返回是否通过。"""
        errors_before = len(self.errors)
        self._check_parse()
        self._check_required_fields()
        self._check_optional_fields()
        success = len(self.errors) == errors_before
        return success

    def _check_parse(self) -> None:
        """检查文件是否正常解析为 JSON。"""
        try:
            text = self.path.read_text(encoding="utf-8")
            self._data = json.loads(text)
        except json.JSONDecodeError as exc:
            line = getattr(exc, "lineno", None)
            col = getattr(exc, "colno", None)
            detail = f"{exc.msg}"
            if line is not None:
                detail += f" (line {line}"
                if col is not None:
                    detail += f", col {col}"
                detail += ")"
            self._add_error(line, "json_parse_error", detail)
            self._data = None
            return
        except OSError as exc:
            self._add_error(0, "file_error", f"{exc}")
            self._data = None
            return

        if not isinstance(self._data, dict):
            self._add_error(0, "json_parse_error", "根节点必须是 JSON 对象 (dict)")

    def _check_required_fields(self) -> None:
        if self._data is None or not isinstance(self._data, dict):
            for field_name in REQUIRED_FIELDS:
                self._add_error(0, "missing_field", f"缺少必填字段: {field_name}")
            return

        for field_name, (field_type, constraint) in REQUIRED_FIELDS.items():
            if field_name not in self._data:
                self._add_error(0, "missing_field", f"缺少必填字段: {field_name}")
                continue

            value = self._data[field_name]
            if not isinstance(value, field_type):
                self._add_error(0, "type_error",
                                f"{field_name} 期望类型 {field_type.__name__}, "
                                f"实际类型 {type(value).__name__}")
                continue

            # 逐个约束检查
            if constraint is not None:
                if isinstance(value, str):
                    min_len = constraint.get("min_length")
                    if min_len is not None and len(value) < min_len:
                        self._add_error(0, "constraint_error",
                                        f"{field_name} 最少 {min_len} 字, 实际 {len(value)} 字")

                if isinstance(value, list):
                    min_items = constraint.get("min_items")
                    if min_items is not None and len(value) < min_items:
                        self._add_error(0, "constraint_error",
                                        f"{field_name} 至少 {min_items} 项, 实际 {len(value)} 项")

                allowed = constraint.get("allowed")
                if allowed is not None and value not in allowed:
                    self._add_error(0, "constraint_error",
                                    f"{field_name} 必须为 {allowed} 之一, "
                                    f"实际为 '{value}'")

        # 额外校验: ID 格式
        if "id" in self._data and isinstance(self._data["id"], str):
            if not ID_PATTERN.match(self._data["id"]):
                self._add_error(0, "constraint_error",
                                f"id 格式错误: 应为 {{source}}-{{YYYYMMDD}}-{{NNN}}, "
                                f"实际 '{self._data['id']}'")

        # 额外校验: source_url 格式
        if "source_url" in self._data and isinstance(self._data["source_url"], str):
            if not URL_PATTERN.match(self._data["source_url"]):
                self._add_error(0, "constraint_error",
                                f"source_url 格式错误: 应为 https?://..., "
                                f"实际 '{self._data['source_url']}'")

    def _check_optional_fields(self) -> None:
        if self._data is None or not isinstance(self._data, dict):
            return

        for field_name, (field_type, constraint) in OPTIONAL_FIELDS.items():
            if field_name not in self._data:
                continue

            value = self._data[field_name]
            if not isinstance(value, field_type):
                self._add_error(0, "type_error",
                                f"{field_name} 期望类型 {field_type.__name__}, "
                                f"实际类型 {type(value).__name__}")
                continue

            if constraint is not None:
                allowed = constraint.get("allowed")
                if allowed is not None and value not in allowed:
                    self._add_error(0, "constraint_error",
                                    f"{field_name} 必须为 {allowed} 之一, "
                                    f"实际为 '{value}'")

                min_val = constraint.get("min")
                if min_val is not None and value < min_val:
                    self._add_error(0, "constraint_error",
                                    f"{field_name} 最小值为 {min_val}, 实际 {value}")

                max_val = constraint.get("max")
                if max_val is not None and value > max_val:
                    self._add_error(0, "constraint_error",
                                    f"{field_name} 最大值为 {max_val}, 实际 {value}")


def validate_files(file_paths: list[Path]) -> tuple[int, int, int]:
    """批量校验文件，返回 (通过数, 失败数, 错误总数)。"""
    pass_count = 0
    fail_count = 0
    total_errors = 0

    for fp in file_paths:
        validator = JsonValidator(fp)
        passed = validator.validate()

        if passed:
            print(f"PASS {fp} (0 errors)", end="")
            pass_count += 1
        else:
            print(f"FAIL {fp} ({len(validator.errors)} errors)", end="")
            for error in validator.errors:
                total_errors += 1
                print(f"\n  {error}")
            fail_count += 1

    # 如果失败数量>0 则返回 1 作为退出码
    return (pass_count, fail_count, total_errors)


def main() -> None:
    """入口函数。"""
    if len(sys.argv) < 2:
        print(f"用法: {sys.argv[0]} <json_file> [json_file2 ...]", file=sys.stderr)
        sys.exit(1)

    file_paths: list[Path] = []
    for spec in sys.argv[1:]:
        p = Path(spec)
        if p.exists():
            file_paths.append(p)
        else:
            # 作为 glob 模式匹配
            matched = sorted(Path(".").glob(spec))
            if matched:
                file_paths.extend(matched)
            else:
                print(f"错误: 文件不存在: {spec}", file=sys.stderr)
                sys.exit(1)

    if not file_paths:
        print("错误: 没有匹配到任何文件", file=sys.stderr)
        sys.exit(1)

    pass_count, fail_count, total_errors = validate_files(file_paths)
    total = pass_count + fail_count

    print(f"\n结果: {pass_count}/{total} 文件通过, {fail_count} 个失败, {total_errors} 个错误")

    sys.exit(1 if fail_count > 0 else 0)


if __name__ == "__main__":
    main()
