"""context_builder.py —— 上下文融合模块。

本模块是 Autonomous-PR-Reviewer 工作流的 Step 2（Context Fusion）。
职责：接收 Step 1（github_service）输出的 diff 文件列表，在给定的 token 预算下，
将各文件的 diff 拼装成一段可安全喂给 LLM 的上下文文本，防止超出大模型的 token 限制。

策略（字符启发估算 + 逐文件预算）：
    - token 估算：采用 ``字符数 / chars_per_token`` 的粗略启发式，不引入 tiktoken 等重依赖。
    - 逐文件预算：为整体设置 max_total_tokens 上限；单个文件 diff 过长时截断到 max_file_tokens；
      当某文件即使截断后仍放不进剩余预算，则跳过（记为 omitted），继续尝试后续较小的文件。

设计原则：
    - 日志记录：使用 logging 记录融合过程中的截断 / 省略情况，而非 print。
    - 类型注解 + 中文 Docstring。
    - 防御性：对空输入、非法参数做校验与兜底。
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

# 配置全局日志：INFO 级别（与 github_service 保持一致；重复调用为无操作）。
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

# 单个文件被截断时追加的标记，便于 LLM 与人类识别该 diff 不完整。
_TRUNCATION_MARKER = "\n...[此文件 diff 过长，已截断]..."


@dataclass
class FusedContext:
    """上下文融合结果。

    Attributes:
        text: 拼装好的、可直接喂给 LLM 的上下文文本（Markdown 格式）。
        estimated_tokens: 对 ``text`` 的估算 token 数。
        included_files: 完整或截断后被纳入上下文的文件名列表。
        truncated_files: 因单文件过长而被截断的文件名列表（included_files 的子集）。
        omitted_files: 因总预算不足而被整体省略的文件名列表。
    """

    text: str
    estimated_tokens: int
    included_files: list[str] = field(default_factory=list)
    truncated_files: list[str] = field(default_factory=list)
    omitted_files: list[str] = field(default_factory=list)


class ContextBuilder:
    """上下文融合器。

    将多个文件的 diff 在 token 预算约束下拼装为单段上下文文本。
    一个实例的预算配置可重复用于多个 PR。
    """

    def __init__(
        self,
        max_total_tokens: int = 12000,
        max_file_tokens: int = 3000,
        chars_per_token: int = 4,
    ) -> None:
        """初始化融合器并校验预算参数。

        Args:
            max_total_tokens: 整段上下文允许的最大估算 token 数。
            max_file_tokens: 单个文件 diff 允许的最大估算 token 数，超出则截断。
            chars_per_token: 估算时每个 token 约对应的字符数（启发式，默认 4）。

        Raises:
            ValueError: 当任一参数不是正整数，或 max_file_tokens 大于 max_total_tokens 时抛出。
        """
        if max_total_tokens <= 0 or max_file_tokens <= 0 or chars_per_token <= 0:
            raise ValueError("max_total_tokens / max_file_tokens / chars_per_token 必须为正整数。")
        if max_file_tokens > max_total_tokens:
            raise ValueError("max_file_tokens 不应大于 max_total_tokens。")

        self.max_total_tokens: int = max_total_tokens
        self.max_file_tokens: int = max_file_tokens
        self.chars_per_token: int = chars_per_token

    def estimate_tokens(self, text: str) -> int:
        """用字符启发式估算文本的 token 数。

        Args:
            text: 待估算的文本。

        Returns:
            估算的 token 数（向上取整），空文本返回 0。
        """
        if not text:
            return 0
        return math.ceil(len(text) / self.chars_per_token)

    def _truncate_to_tokens(self, text: str, max_tokens: int) -> tuple[str, bool]:
        """将文本截断到不超过指定 token 数。

        Args:
            text: 原始文本。
            max_tokens: 允许的最大估算 token 数。

        Returns:
            ``(处理后的文本, 是否发生了截断)`` 二元组。
        """
        max_chars = max_tokens * self.chars_per_token
        if len(text) <= max_chars:
            return text, False
        # 为截断标记预留空间，避免截断后整体又超出预算。
        keep = max(0, max_chars - len(_TRUNCATION_MARKER))
        return text[:keep] + _TRUNCATION_MARKER, True

    def build_context(self, diff_files: list[dict]) -> FusedContext:
        """将 diff 文件列表融合为受 token 预算约束的上下文文本。

        遍历每个文件：单文件 diff 过长则先截断到 max_file_tokens；
        若该文件（截断后）放不进剩余总预算，则整体省略并记录，继续尝试后续文件。

        Args:
            diff_files: 形如 ``[{"filename": str, "patch": str}, ...]`` 的列表
                （通常来自 ``GitHubPRFetcher.get_pr_diff`` 的输出）。

        Returns:
            :class:`FusedContext`，包含融合文本及纳入 / 截断 / 省略的文件统计。
        """
        # 防御性：兜底处理空输入。
        if not diff_files:
            logger.info("传入的 diff 文件列表为空，返回空上下文。")
            return FusedContext(text="", estimated_tokens=0)

        blocks: list[str] = []
        included: list[str] = []
        truncated: list[str] = []
        omitted: list[str] = []
        running_tokens: int = 0

        for item in diff_files:
            filename = item.get("filename", "<unknown>")
            patch = item.get("patch") or ""
            if not patch:
                # Step 1 通常已过滤，此处再兜底跳过无内容文件。
                logger.info("跳过无 diff 内容的文件：%s", filename)
                continue

            # 1) 单文件层面：过长则截断。
            patch_body, was_truncated = self._truncate_to_tokens(patch, self.max_file_tokens)

            # 2) 组装该文件的 Markdown 区块。
            block = f"### 文件: {filename}\n```diff\n{patch_body}\n```\n"
            block_tokens = self.estimate_tokens(block)

            # 3) 总预算层面：放不下则省略当前文件，继续尝试后续较小文件。
            if running_tokens + block_tokens > self.max_total_tokens:
                logger.info(
                    "总预算不足，省略文件：%s（需 %d tokens，剩余 %d）",
                    filename,
                    block_tokens,
                    self.max_total_tokens - running_tokens,
                )
                omitted.append(filename)
                continue

            blocks.append(block)
            running_tokens += block_tokens
            included.append(filename)
            if was_truncated:
                truncated.append(filename)
                logger.info("文件 diff 过长已截断：%s", filename)

        text = "\n".join(blocks)
        result = FusedContext(
            text=text,
            estimated_tokens=self.estimate_tokens(text),
            included_files=included,
            truncated_files=truncated,
            omitted_files=omitted,
        )
        logger.info(
            "上下文融合完成：纳入 %d 个文件（截断 %d，省略 %d），估算 %d tokens。",
            len(included),
            len(truncated),
            len(omitted),
            result.estimated_tokens,
        )
        return result


# ---------------------------------------------------------------------------
# 本地测试桩：用合成数据演示融合效果，无需 Token / 网络
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # 构造一批合成 diff 文件：其中一个超长，用于演示截断与省略。
    sample_files: list[dict] = [
        {"filename": "src/a.py", "patch": "@@ -1,2 +1,3 @@\n+print('hello')\n-pass"},
        {"filename": "src/big.py", "patch": "@@ huge diff @@\n" + ("+x = 1\n" * 5000)},
        {"filename": "src/b.py", "patch": "@@ -10 +10 @@\n-old\n+new"},
    ]

    # 故意调小预算，便于观察截断 / 省略行为。
    builder = ContextBuilder(max_total_tokens=800, max_file_tokens=300)
    fused = builder.build_context(sample_files)

    print(f"估算 tokens：{fused.estimated_tokens}")
    print(f"纳入文件：{fused.included_files}")
    print(f"截断文件：{fused.truncated_files}")
    print(f"省略文件：{fused.omitted_files}")
    print("\n===== 融合后的上下文 =====")
    print(fused.text)
