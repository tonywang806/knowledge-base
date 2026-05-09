"""validate.ts 插件的静态回归测试。"""

from pathlib import Path


PLUGIN_PATH = Path(".opencode/plugins/validate.ts")


def test_validate_plugin_uses_opencode_shell_injection() -> None:
    """校验插件使用 OpenCode 注入的 shell，避免依赖未声明的 zx 包。"""
    source = PLUGIN_PATH.read_text(encoding="utf-8")

    assert 'from "zx"' not in source
    assert "async ({ $" in source
