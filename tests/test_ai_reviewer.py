"""ai_reviewer 模块的单元测试。

通过注入 mock 的 LLMClient，验证 Prompt 组装与流程编排，不依赖真实 Key / 网络。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_reviewer import AIReviewer
from llm_client import LLMClient, LLMError

_SAMPLE_DIFF = [{"filename": "a.py", "patch": "@@ -1 +1 @@\n+x = 1 / 0"}]


def _reviewer_with_mock_client() -> tuple[AIReviewer, MagicMock]:
    """构造一个注入了 mock LLMClient 的 AIReviewer。"""
    mock_client = MagicMock(spec=LLMClient)
    return AIReviewer(llm_client=mock_client), mock_client


def test_analyze_pr_returns_markdown() -> None:
    """analyze_pr 应返回 LLM 输出的 Markdown，并以 system+user 提示调用 complete。"""
    reviewer, mock_client = _reviewer_with_mock_client()
    mock_client.complete.return_value = (
        "## 变更总结\n修复除零问题。\n\n## 风险审查\n未发现明显的高风险问题。"
    )

    result = reviewer.analyze_pr(_SAMPLE_DIFF)

    assert "## 变更总结" in result
    assert "## 风险审查" in result
    args, _ = mock_client.complete.call_args
    system_prompt, user_prompt = args
    assert "风险审查" in system_prompt  # 系统提示包含审查任务约束
    assert "x = 1 / 0" in user_prompt   # 用户提示包含 diff 内容


def test_analyze_pr_empty_diff_skips_llm() -> None:
    """diff 为空时应直接返回提示，且不调用 LLM。"""
    reviewer, mock_client = _reviewer_with_mock_client()

    result = reviewer.analyze_pr([])

    assert "未包含可分析的代码变更" in result
    mock_client.complete.assert_not_called()


def test_analyze_pr_wraps_llm_error() -> None:
    """LLM 调用失败（LLMError）时应包装为 RuntimeError 抛出。"""
    reviewer, mock_client = _reviewer_with_mock_client()
    mock_client.complete.side_effect = LLMError("boom")

    with pytest.raises(RuntimeError):
        reviewer.analyze_pr(_SAMPLE_DIFF)
