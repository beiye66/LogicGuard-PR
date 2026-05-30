"""llm_client 模块的单元测试。

覆盖多模型路由（provider 选择 / 模型名推断）与两个后端的 complete / 异常包装，
通过 patch 各自 SDK 的客户端类，不发起真实网络请求。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from openai import OpenAIError

from llm_client import (
    AnthropicClient,
    LLMError,
    OpenAICompatibleClient,
    create_llm_client,
)


# ---------------------------------------------------------------------------
# 路由：create_llm_client
# ---------------------------------------------------------------------------


def _clear_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("LLM_PROVIDER", "LLM_MODEL", "LLM_API_KEY", "LLM_BASE_URL", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(key, raising=False)


def test_create_defaults_to_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    """未设 provider 且模型名非 claude 时，默认走 OpenAI 兼容后端。"""
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_API_KEY", "dummy")
    with patch("llm_client.OpenAI"):
        client = create_llm_client()
    assert isinstance(client, OpenAICompatibleClient)


def test_create_infers_anthropic_from_model_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """未设 provider 但模型名以 claude 开头时，自动推断为 anthropic。"""
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_MODEL", "claude-sonnet-4-6")
    monkeypatch.setenv("LLM_API_KEY", "dummy")
    with patch("llm_client.anthropic.Anthropic"):
        client = create_llm_client()
    assert isinstance(client, AnthropicClient)


def test_explicit_provider_overrides_model_inference(monkeypatch: pytest.MonkeyPatch) -> None:
    """显式 LLM_PROVIDER 优先于模型名推断。"""
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "claude-sonnet-4-6")  # 名字像 claude，但被 provider 覆盖
    monkeypatch.setenv("LLM_API_KEY", "dummy")
    with patch("llm_client.OpenAI"):
        client = create_llm_client()
    assert isinstance(client, OpenAICompatibleClient)


def test_anthropic_prefers_dedicated_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """anthropic 后端优先使用 ANTHROPIC_API_KEY。"""
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ak")
    with patch("llm_client.anthropic.Anthropic") as mock_cls:
        create_llm_client()
    assert mock_cls.call_args.kwargs["api_key"] == "ak"


def test_missing_openai_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """openai 后端缺少 LLM_API_KEY 时抛出 LLMError。"""
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    with pytest.raises(LLMError):
        create_llm_client()


def test_unsupported_provider_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """不支持的 provider 抛出 LLMError。"""
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "gemini")  # 非法值
    with pytest.raises(LLMError):
        create_llm_client()


# ---------------------------------------------------------------------------
# 后端：complete 与异常包装
# ---------------------------------------------------------------------------


@patch("llm_client.OpenAI")
def test_openai_complete_returns_text(mock_openai_cls: MagicMock) -> None:
    """OpenAI 后端 complete 返回去空白后的文本。"""
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    msg = MagicMock()
    msg.content = "  hello  "
    mock_client.chat.completions.create.return_value = MagicMock(choices=[MagicMock(message=msg)])

    client = OpenAICompatibleClient(api_key="k", model="m", base_url="http://x")
    assert client.complete("sys", "user") == "hello"


@patch("llm_client.OpenAI")
def test_openai_complete_wraps_error(mock_openai_cls: MagicMock) -> None:
    """OpenAI 后端调用失败时包装为 LLMError。"""
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.side_effect = OpenAIError("boom")

    client = OpenAICompatibleClient(api_key="k", model="m", base_url="http://x")
    with pytest.raises(LLMError):
        client.complete("sys", "user")


@patch("llm_client.anthropic.Anthropic")
def test_anthropic_complete_joins_text_blocks(mock_anthropic_cls: MagicMock) -> None:
    """Anthropic 后端 complete 拼接文本块并去空白。"""
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    block1 = MagicMock(type="text", text="hello ")
    block2 = MagicMock(type="text", text="world")
    mock_client.messages.create.return_value = MagicMock(content=[block1, block2])

    client = AnthropicClient(api_key="k", model="claude-sonnet-4-6")
    assert client.complete("sys", "user") == "hello world"
    # 校验 system 作为顶层参数传入（而非消息角色）。
    assert mock_client.messages.create.call_args.kwargs["system"] == "sys"
