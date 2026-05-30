"""ai_reviewer 模块的单元测试。

通过 mock 假冒 openai 客户端，不依赖真实 LLM_API_KEY、不发起网络请求，可在 CI 中稳定运行。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from openai import OpenAIError

from ai_reviewer import AIReviewer


def _mock_completion(content: str) -> MagicMock:
    """构造一个模拟的 chat.completions.create 返回对象。"""
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


_SAMPLE_DIFF = [{"filename": "a.py", "patch": "@@ -1 +1 @@\n+x = 1 / 0"}]


def test_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """未配置 LLM_API_KEY 时，初始化应抛出 ValueError。"""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(ValueError):
        AIReviewer()


@patch("ai_reviewer.OpenAI")
def test_analyze_pr_returns_markdown(
    mock_openai_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """analyze_pr 应返回 LLM 输出的 Markdown，并以正确 model 调用接口。"""
    monkeypatch.setenv("LLM_API_KEY", "dummy-key")
    monkeypatch.setenv("LLM_MODEL", "deepseek-chat")

    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_completion(
        "## 变更总结\n修复除零问题。\n\n## 风险审查\n未发现明显的高风险问题。"
    )

    reviewer = AIReviewer()
    result = reviewer.analyze_pr(_SAMPLE_DIFF)

    assert "## 变更总结" in result
    assert "## 风险审查" in result
    _, kwargs = mock_client.chat.completions.create.call_args
    assert kwargs["model"] == "deepseek-chat"
    assert isinstance(kwargs["messages"], list) and len(kwargs["messages"]) == 2


@patch("ai_reviewer.OpenAI")
def test_analyze_pr_empty_diff_skips_llm(
    mock_openai_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """diff 为空时应直接返回提示，且不调用 LLM。"""
    monkeypatch.setenv("LLM_API_KEY", "dummy-key")
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client

    reviewer = AIReviewer()
    result = reviewer.analyze_pr([])

    assert "未包含可分析的代码变更" in result
    mock_client.chat.completions.create.assert_not_called()


@patch("ai_reviewer.OpenAI")
def test_analyze_pr_wraps_openai_error(
    mock_openai_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """LLM 调用失败（OpenAIError）时应包装为 RuntimeError 抛出。"""
    monkeypatch.setenv("LLM_API_KEY", "dummy-key")
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.side_effect = OpenAIError("boom")

    reviewer = AIReviewer()
    with pytest.raises(RuntimeError):
        reviewer.analyze_pr(_SAMPLE_DIFF)
