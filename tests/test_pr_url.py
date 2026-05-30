"""pr_url 模块的单元测试（纯解析逻辑，无外部依赖）。"""

from __future__ import annotations

import pytest

from pr_url import parse_pr_url


def test_parse_standard_url() -> None:
    """标准 PR 链接应正确解析出 owner/repo 与 PR 号。"""
    assert parse_pr_url("https://github.com/octocat/Hello-World/pull/42") == (
        "octocat/Hello-World",
        42,
    )


def test_parse_url_with_suffix_and_spaces() -> None:
    """带 /files 后缀及首尾空白的链接也应正确解析。"""
    assert parse_pr_url("  https://github.com/owner/repo/pull/7/files  ") == (
        "owner/repo",
        7,
    )


def test_empty_url_raises() -> None:
    """空链接应抛出 ValueError。"""
    with pytest.raises(ValueError):
        parse_pr_url("   ")


def test_invalid_url_raises() -> None:
    """非 PR 链接应抛出 ValueError。"""
    with pytest.raises(ValueError):
        parse_pr_url("https://github.com/owner/repo/issues/1")
