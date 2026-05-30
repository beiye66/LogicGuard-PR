"""ai_reviewer.py —— AI 分析引擎模块。

本模块是 Autonomous-PR-Reviewer 工作流的 Step 3（AI Analysis）。
职责：接收 Step 1（github_service）输出的 diff 文件列表，先经 Step 2（ContextBuilder）做
token 预算截断融合，再组装 Prompt 调用 LLM，产出可直接用于 PR 评论的 Markdown 审查结果。

模型客户端：
    使用 openai 官方 SDK 调用「OpenAI 兼容」的接口（DeepSeek / OpenAI / Gemini 兼容端点均可），
    通过 base_url 切换厂商。利用 SDK 内置的 max_retries 重试与规范化异常类（OpenAIError）
    来保证 Pipeline 的鲁棒性。

设计原则：
    - 防御性编程：缺失配置早失败；LLM 调用捕获 OpenAIError 并记录后抛出明确错误。
    - 日志记录：使用 logging。
    - 类型注解 + 中文 Docstring。
    - 模块化：截断逻辑复用 ContextBuilder，本模块只负责「组装 Prompt + 调用 LLM」。
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

from context_builder import ContextBuilder

# 加载 .env 中的 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL 等配置。
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

# 默认指向 DeepSeek 的 OpenAI 兼容端点；可通过环境变量覆盖以切换其它厂商。
_DEFAULT_BASE_URL = "https://api.deepseek.com"
_DEFAULT_MODEL = "deepseek-chat"

# 系统提示词：定义审查专家角色、两项任务，以及「低误报」硬约束与纯 Markdown 输出要求。
_SYSTEM_PROMPT = """你是一名经验丰富的资深软件工程师，正在对一个 GitHub Pull Request 的代码变更（diff）进行审查。
请严格按下面两个任务输出，且**只输出纯 Markdown 内容**（不要用代码块把整个回答包起来，不要输出与审查无关的客套话）：

## 变更总结
用简短的一句话总结这个 PR 的主要变更（做了什么）。

## 风险审查
严格审查代码，只指出**确实存在**的潜在逻辑错误、内存风险、并发冲突或未处理的边界情况。
极其重要的约束：
- 如果代码没有严重问题，请直接输出一行：未发现明显的高风险问题。
- 绝不允许为了凑字数而捏造问题，也不要提出琐碎的代码风格、命名或格式建议。
- 对每条确实存在的风险，请简述：问题是什么、可能造成的后果、涉及的文件或代码位置。
"""


class AIReviewer:
    """AI 代码审查器。

    封装 LLM 客户端与 Prompt 组装逻辑，对外提供 :meth:`analyze_pr` 方法，
    将 diff 数据转换为 Markdown 格式的审查结论。
    """

    def __init__(
        self,
        context_builder: ContextBuilder | None = None,
        timeout: float = 60.0,
        max_retries: int = 3,
    ) -> None:
        """初始化 AI 审查器。

        从环境变量读取 LLM 配置并构造 openai 客户端：
        ``LLM_API_KEY``（必填）、``LLM_BASE_URL``（选填，默认 DeepSeek）、
        ``LLM_MODEL``（选填，默认 deepseek-chat）。

        Args:
            context_builder: 用于截断 / 融合 diff 的 ContextBuilder 实例；
                传 None 时使用默认配置新建一个。
            timeout: 单次请求超时时间（秒）。
            max_retries: SDK 内置的失败重试次数（针对网络 / 限流等可重试错误）。

        Raises:
            ValueError: 当环境变量 ``LLM_API_KEY`` 未设置或为空时抛出。
        """
        api_key: str | None = os.getenv("LLM_API_KEY")
        if not api_key:
            logger.error("环境变量 LLM_API_KEY 未设置，无法初始化 AI 审查器。")
            raise ValueError("未检测到 LLM_API_KEY，请在 .env 文件中配置后重试。")

        self._base_url: str = os.getenv("LLM_BASE_URL") or _DEFAULT_BASE_URL
        self._model: str = os.getenv("LLM_MODEL") or _DEFAULT_MODEL

        # 利用 SDK 内置的超时与重试机制保证鲁棒性。
        self._client: OpenAI = OpenAI(
            api_key=api_key,
            base_url=self._base_url,
            timeout=timeout,
            max_retries=max_retries,
        )
        self._builder: ContextBuilder = context_builder or ContextBuilder()
        logger.info("AI 审查器初始化成功（base_url=%s, model=%s）。", self._base_url, self._model)

    def _build_messages(self, context_text: str) -> list[dict[str, str]]:
        """组装发送给 LLM 的对话消息。

        Args:
            context_text: 经 ContextBuilder 融合 / 截断后的 diff 上下文文本。

        Returns:
            符合 openai chat.completions 接口的 messages 列表（system + user）。
        """
        user_prompt = f"以下是本次 PR 的代码变更（diff）：\n\n{context_text}"
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

    def analyze_pr(self, diff_data: list[dict]) -> str:
        """分析 PR 的代码变更，返回 Markdown 格式的审查结论。

        流程：先用 ContextBuilder 将 diff_data 融合并截断到 token 预算内（Step 2），
        再组装 Prompt 调用 LLM 完成 Task A（总结）与 Task B（风险审查）。

        Args:
            diff_data: 形如 ``[{"filename": str, "patch": str}, ...]`` 的 diff 列表
                （通常来自 ``GitHubPRFetcher.get_pr_diff``）。

        Returns:
            LLM 返回的 Markdown 审查文本；若无可分析的变更则返回提示信息。

        Raises:
            RuntimeError: 当 LLM 调用在重试后仍失败时抛出（已记录详细日志）。
        """
        # Step 2：融合 + 截断。若没有任何可分析内容则提前返回，避免空调用。
        fused = self._builder.build_context(diff_data)
        if not fused.text.strip():
            logger.info("无可分析的 diff 内容，跳过 LLM 调用。")
            return "## 审查结果\n\n本次 PR 未包含可分析的代码变更。"

        messages = self._build_messages(fused.text)

        try:
            logger.info("正在调用 LLM 进行 PR 审查（model=%s）...", self._model)
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0.2,  # 低温度，减少臆造、提升稳定性，契合「低误报」要求
            )
        except OpenAIError as exc:
            # SDK 内置重试耗尽后仍失败，记录规范化异常并抛出明确错误。
            logger.error("调用 LLM 失败：%s", exc)
            raise RuntimeError(f"调用 LLM 失败：{exc}") from exc

        content = (response.choices[0].message.content or "").strip()
        if not content:
            logger.warning("LLM 返回了空内容。")
            return "## 审查结果\n\nLLM 未返回有效内容，请稍后重试。"

        logger.info("LLM 审查完成，返回 %d 字符。", len(content))
        return content


# ---------------------------------------------------------------------------
# 本地测试桩：用一段刻意写错的 diff 验证 AI 审查效果（需真实 LLM_API_KEY）
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # 伪造一段带有明显隐患的 diff：
    #   1) 多线程共享变量自增未加锁（并发竞争）
    #   2) 除法未校验除数是否为 0（潜在 ZeroDivisionError）
    fake_diff_data: list[dict] = [
        {
            "filename": "worker.py",
            "patch": (
                "@@ -1,3 +1,12 @@\n"
                "+import threading\n"
                "+\n"
                "+counter = 0\n"
                "+\n"
                "+def worker():\n"
                "+    global counter\n"
                "+    for _ in range(100000):\n"
                "+        counter += 1  # 多线程并发调用，未加锁\n"
                "+\n"
                "+threads = [threading.Thread(target=worker) for _ in range(8)]\n"
            ),
        },
        {
            "filename": "calc.py",
            "patch": (
                "@@ -1,2 +1,4 @@\n"
                "+def average(total, count):\n"
                "+    # 未检查 count 是否为 0\n"
                "+    return total / count\n"
            ),
        },
    ]

    reviewer = AIReviewer()
    review_markdown = reviewer.analyze_pr(fake_diff_data)
    print("\n===== AI 审查结果（Markdown）=====\n")
    print(review_markdown)
