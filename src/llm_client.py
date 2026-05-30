"""llm_client.py —— 多模型路由 / LLM 客户端抽象层。

将「调用哪家大模型」与「如何审查」解耦：上层（AIReviewer）只依赖 :class:`LLMClient`
抽象接口，由本模块根据配置路由到具体后端：

    - :class:`OpenAICompatibleClient` —— 走 openai SDK，兼容 OpenAI / DeepSeek / Gemini 等。
    - :class:`AnthropicClient`        —— 走 anthropic SDK，调用 Claude。

路由规则（:func:`create_llm_client`）：
    1. 优先读环境变量 ``LLM_PROVIDER``（openai / anthropic）。
    2. 未显式设置时，按模型名自动推断：``claude*`` → anthropic，其余 → openai 兼容。

两个后端都启用各自 SDK 的内置 ``max_retries`` 重试，并将各自的 SDK 异常统一包装为
:class:`LLMError`，便于上层统一处理。
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod

import anthropic
from openai import OpenAI, OpenAIError

logger = logging.getLogger(__name__)

# 各后端的默认接口地址与模型。
_DEFAULT_OPENAI_BASE_URL = "https://api.deepseek.com"
_DEFAULT_OPENAI_MODEL = "deepseek-chat"
_DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-6"

# Anthropic 接口要求显式 max_tokens；此处给一个对审查结果足够的上限。
_ANTHROPIC_MAX_TOKENS = 2048


class LLMError(RuntimeError):
    """LLM 调用失败的统一异常（包装各厂商 SDK 的底层异常）。"""


class LLMClient(ABC):
    """LLM 客户端抽象接口。

    具体后端只需实现 :meth:`complete`：给定系统提示与用户提示，返回模型输出的文本。
    """

    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """调用模型并返回纯文本结果。

        Args:
            system_prompt: 系统提示词（角色 / 约束）。
            user_prompt: 用户提示词（实际待审查的内容）。

        Returns:
            模型返回的文本。

        Raises:
            LLMError: 当底层调用失败（重试耗尽）时抛出。
        """
        raise NotImplementedError


class OpenAICompatibleClient(LLMClient):
    """OpenAI 兼容后端（OpenAI / DeepSeek / Gemini 等）。"""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        timeout: float = 60.0,
        max_retries: int = 3,
        temperature: float = 0.2,
    ) -> None:
        """初始化 openai 客户端。

        Args:
            api_key: API Key。
            model: 模型 ID。
            base_url: OpenAI 兼容端点地址。
            timeout: 单次请求超时（秒）。
            max_retries: SDK 内置重试次数。
            temperature: 采样温度（低温降低臆造）。
        """
        self._model = model
        self._temperature = temperature
        self._client = OpenAI(
            api_key=api_key, base_url=base_url, timeout=timeout, max_retries=max_retries
        )
        logger.info("LLM 后端：OpenAI 兼容（base_url=%s, model=%s）。", base_url, model)

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """调用 chat.completions 接口并返回文本。"""
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self._temperature,
            )
        except OpenAIError as exc:
            logger.error("OpenAI 兼容接口调用失败：%s", exc)
            raise LLMError(f"OpenAI 兼容接口调用失败：{exc}") from exc

        return (response.choices[0].message.content or "").strip()


class AnthropicClient(LLMClient):
    """Anthropic（Claude）后端。"""

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float = 60.0,
        max_retries: int = 3,
        temperature: float = 0.2,
        max_tokens: int = _ANTHROPIC_MAX_TOKENS,
    ) -> None:
        """初始化 anthropic 客户端。

        Args:
            api_key: Anthropic API Key。
            model: Claude 模型 ID（如 claude-sonnet-4-6）。
            timeout: 单次请求超时（秒）。
            max_retries: SDK 内置重试次数。
            temperature: 采样温度。
            max_tokens: 单次回复最大 token 数（Anthropic 接口必填）。
        """
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._client = anthropic.Anthropic(
            api_key=api_key, timeout=timeout, max_retries=max_retries
        )
        logger.info("LLM 后端：Anthropic（model=%s）。", model)

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """调用 messages 接口并返回拼接后的文本。"""
        try:
            message = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                system=system_prompt,  # Anthropic 的系统提示是顶层参数，而非消息角色
                messages=[{"role": "user", "content": user_prompt}],
            )
        except anthropic.AnthropicError as exc:
            logger.error("Anthropic 接口调用失败：%s", exc)
            raise LLMError(f"Anthropic 接口调用失败：{exc}") from exc

        # content 为内容块列表，拼接其中所有文本块。
        parts = [block.text for block in message.content if getattr(block, "type", None) == "text"]
        return "".join(parts).strip()


def _infer_provider(model: str | None) -> str:
    """根据模型名推断厂商：claude* → anthropic，其余 → openai。"""
    if model and model.strip().lower().startswith("claude"):
        return "anthropic"
    return "openai"


def create_llm_client(timeout: float = 60.0, max_retries: int = 3) -> LLMClient:
    """根据环境变量配置创建对应的 LLM 客户端（多模型路由入口）。

    读取的环境变量：
        - ``LLM_PROVIDER``：openai / anthropic；未设置时按 ``LLM_MODEL`` 自动推断。
        - ``LLM_MODEL``：模型 ID（缺省时按厂商取默认值）。
        - openai 兼容：``LLM_API_KEY``、``LLM_BASE_URL``。
        - anthropic：``ANTHROPIC_API_KEY``（缺省回退 ``LLM_API_KEY``）。

    Args:
        timeout: 单次请求超时（秒）。
        max_retries: SDK 内置重试次数。

    Returns:
        与配置匹配的 :class:`LLMClient` 实例。

    Raises:
        LLMError: 当 provider 不受支持或缺少必要的 API Key 时抛出。
    """
    model = os.getenv("LLM_MODEL")
    provider = (os.getenv("LLM_PROVIDER") or "").strip().lower()
    if not provider:
        provider = _infer_provider(model)

    if provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("LLM_API_KEY")
        return build_llm_client(
            "anthropic", api_key, model, timeout=timeout, max_retries=max_retries
        )

    if provider == "openai":
        return build_llm_client(
            "openai",
            os.getenv("LLM_API_KEY"),
            model,
            base_url=os.getenv("LLM_BASE_URL"),
            timeout=timeout,
            max_retries=max_retries,
        )

    raise LLMError(f"不支持的 LLM_PROVIDER：{provider!r}（仅支持 openai / anthropic）。")


def build_llm_client(
    provider: str,
    api_key: str | None,
    model: str | None,
    base_url: str | None = None,
    timeout: float = 60.0,
    max_retries: int = 3,
) -> LLMClient:
    """根据显式配置构建 LLM 客户端（供 Web 端 BYOK「自带 Key」模式使用）。

    Args:
        provider: ``openai``（OpenAI 兼容：OpenAI / DeepSeek / Gemini / 豆包等）或 ``anthropic``。
        api_key: API Key（必填）。
        model: 模型 ID；为空时按厂商取默认值。
        base_url: OpenAI 兼容端点地址；为空时默认 DeepSeek（anthropic 忽略此项）。
        timeout: 单次请求超时（秒）。
        max_retries: SDK 内置重试次数。

    Returns:
        与配置匹配的 :class:`LLMClient` 实例。

    Raises:
        LLMError: 当缺少 API Key 或 provider 不受支持时抛出。
    """
    if not api_key or not api_key.strip():
        raise LLMError("缺少 API Key，无法初始化 LLM 客户端。")

    provider = (provider or "").strip().lower()
    if provider == "anthropic":
        return AnthropicClient(
            api_key=api_key,
            model=model or _DEFAULT_ANTHROPIC_MODEL,
            timeout=timeout,
            max_retries=max_retries,
        )
    if provider == "openai":
        return OpenAICompatibleClient(
            api_key=api_key,
            model=model or _DEFAULT_OPENAI_MODEL,
            base_url=base_url or _DEFAULT_OPENAI_BASE_URL,
            timeout=timeout,
            max_retries=max_retries,
        )
    raise LLMError(f"不支持的 provider：{provider!r}（仅支持 openai / anthropic）。")
