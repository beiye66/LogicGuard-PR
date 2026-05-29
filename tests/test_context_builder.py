"""context_builder 模块的单元测试。

纯计算逻辑，无外部依赖、无网络，可在 CI 中稳定运行。
"""

from __future__ import annotations

import pytest

from context_builder import ContextBuilder


def test_estimate_tokens() -> None:
    """token 估算应为 字符数 / chars_per_token 的向上取整。"""
    builder = ContextBuilder(chars_per_token=4)
    assert builder.estimate_tokens("") == 0
    assert builder.estimate_tokens("abcd") == 1
    assert builder.estimate_tokens("abcde") == 2  # ceil(5 / 4)


def test_invalid_params_raise() -> None:
    """非法预算参数应在初始化时抛出 ValueError。"""
    with pytest.raises(ValueError):
        ContextBuilder(max_total_tokens=0)
    with pytest.raises(ValueError):
        ContextBuilder(max_file_tokens=5000, max_total_tokens=1000)


def test_empty_input_returns_empty() -> None:
    """空输入应返回空上下文。"""
    result = ContextBuilder().build_context([])
    assert result.text == ""
    assert result.estimated_tokens == 0
    assert result.included_files == []
    assert result.truncated_files == []
    assert result.omitted_files == []


def test_all_included_within_budget() -> None:
    """预算充足时，所有文件都应被完整纳入，无截断无省略。"""
    builder = ContextBuilder()
    files = [
        {"filename": "a.py", "patch": "@@ -1 +1 @@\n+x"},
        {"filename": "b.py", "patch": "@@ -1 +1 @@\n-y"},
    ]
    result = builder.build_context(files)

    assert result.included_files == ["a.py", "b.py"]
    assert result.truncated_files == []
    assert result.omitted_files == []
    assert "### 文件: a.py" in result.text
    assert "### 文件: b.py" in result.text


def test_skips_files_without_patch() -> None:
    """无 patch（空串或 None）的文件应被跳过。"""
    builder = ContextBuilder()
    files = [
        {"filename": "a.py", "patch": ""},
        {"filename": "b.py", "patch": None},
        {"filename": "c.py", "patch": "+ok"},
    ]
    result = builder.build_context(files)
    assert result.included_files == ["c.py"]


def test_truncates_oversized_file() -> None:
    """单个文件 diff 超过 max_file_tokens 时应被截断并标记。"""
    builder = ContextBuilder(max_total_tokens=10000, max_file_tokens=100, chars_per_token=4)
    big = {"filename": "big.py", "patch": "x" * 1000}  # 1000 字符 ≈ 250 tokens > 100
    result = builder.build_context([big])

    assert "big.py" in result.included_files
    assert "big.py" in result.truncated_files
    assert "[此文件 diff 过长，已截断]" in result.text


def test_omits_files_when_total_budget_exceeded() -> None:
    """总预算不足时，放不下的文件应被省略，且纳入+省略=总数。"""
    builder = ContextBuilder(max_total_tokens=40, max_file_tokens=40, chars_per_token=4)
    files = [{"filename": f"f{i}.py", "patch": "+code\n" * 10} for i in range(5)]
    result = builder.build_context(files)

    assert len(result.omitted_files) >= 1
    assert len(result.included_files) + len(result.omitted_files) == 5
    assert result.estimated_tokens <= 40
