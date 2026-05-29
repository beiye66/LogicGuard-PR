"""github_service.py —— GitHub 数据接入模块。

本模块是 Autonomous-PR-Reviewer 工作流的 Step 1（Data Fetching）。
职责：通过 GitHub Token 连接 GitHub，抓取指定仓库、指定 PR 的所有文件差异（diff/patch），
并过滤掉二进制文件以及没有实际文本变更的文件，只返回包含 patch 的文件列表。

设计原则：
    - 防御性编程：所有 GitHub API 调用都包裹在 try-except 中，失败时通过 logging 记录并向上抛出。
    - 日志记录：使用标准库 logging，而非 print。
    - 类型注解 + 中文 Docstring：便于团队协作与后续维护。
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from github import Github, GithubException

# ---------------------------------------------------------------------------
# 基础配置
# ---------------------------------------------------------------------------

# 从项目根目录的 .env 文件加载环境变量（GITHUB_TOKEN / LLM_API_KEY 等）。
# 若 .env 不存在，load_dotenv 会静默跳过，不会抛错。
load_dotenv()

# 配置全局日志：INFO 级别，统一时间 / 级别 / 模块名 / 信息的输出格式。
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# 模块级 logger，名称即当前模块名，便于在大型项目中定位日志来源。
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 核心类：GitHubPRFetcher
# ---------------------------------------------------------------------------


class GitHubPRFetcher:
    """GitHub PR 数据抓取器。

    负责初始化 GitHub 客户端，并提供获取指定 PR 文件差异（diff）的能力。
    一个实例对应一份 GITHUB_TOKEN 凭证，可重复用于抓取多个仓库 / 多个 PR。
    """

    def __init__(self) -> None:
        """初始化 GitHub 客户端。

        从环境变量 ``GITHUB_TOKEN`` 读取凭证并构造 :class:`github.Github` 客户端。

        Raises:
            ValueError: 当环境变量 ``GITHUB_TOKEN`` 未设置或为空时抛出，
                避免后续以匿名身份调用 API 触发难以排查的限流 / 403 错误。
        """
        token: str | None = os.getenv("GITHUB_TOKEN")
        if not token:
            # 缺少 Token 属于配置错误，应尽早暴露，而不是等到请求时才失败。
            logger.error("环境变量 GITHUB_TOKEN 未设置，无法初始化 GitHub 客户端。")
            raise ValueError("未检测到 GITHUB_TOKEN，请在 .env 文件中配置后重试。")

        # 使用 Token 构造已认证的 GitHub 客户端。
        self._client: Github = Github(token)
        logger.info("GitHub 客户端初始化成功。")

    def get_pr_diff(self, repo_name: str, pr_number: int) -> list[dict]:
        """获取指定 PR 的所有文件差异（diff/patch）。

        遍历目标 PR 的变更文件，仅保留包含 ``patch`` 内容的文件
        （即有实际文本变更的文件），自动跳过二进制文件以及无 diff 的文件。

        Args:
            repo_name: 仓库全名，格式为 ``"owner/repo"``，例如 ``"octocat/Hello-World"``。
            pr_number: Pull Request 的编号（即 PR 页面 URL 中的数字）。

        Returns:
            一个字典列表，每个元素形如
            ``{"filename": <文件路径>, "patch": <该文件的 diff 文本>}``。
            若 PR 不包含任何文本变更文件，则返回空列表。

        Raises:
            github.GithubException: 当仓库不存在、PR 不存在、Token 无效 / 权限不足
                或其它 GitHub API 错误时抛出（已记录日志后向上抛出，便于调用方处理）。
        """
        # 用于收集所有包含 diff 的文件信息。
        diff_files: list[dict] = []

        try:
            # 1) 定位仓库与 PR。任何一步出错都会抛出 GithubException。
            logger.info("正在获取仓库 %s 的 PR #%d ...", repo_name, pr_number)
            repo = self._client.get_repo(repo_name)
            pull_request = repo.get_pull(pr_number)

            # 2) 遍历 PR 的变更文件，提取 patch。
            for file in pull_request.get_files():
                # file.patch 为 None 时通常表示二进制文件或无文本变更（如纯重命名），过滤掉。
                if not file.patch:
                    logger.info("跳过无 diff 文件（二进制或无文本变更）：%s", file.filename)
                    continue

                diff_files.append({"filename": file.filename, "patch": file.patch})

            logger.info(
                "PR #%d 抓取完成，共提取 %d 个含 diff 的文件。",
                pr_number,
                len(diff_files),
            )

        except GithubException as exc:
            # 捕获 GitHub API 层面的错误（404 仓库/PR 不存在、401/403 Token 无效或权限不足等）。
            logger.error(
                "获取 PR diff 失败（repo=%s, pr=%d）：status=%s, data=%s",
                repo_name,
                pr_number,
                getattr(exc, "status", "N/A"),
                getattr(exc, "data", str(exc)),
            )
            # 记录日志后向上抛出，交由调用方决定重试 / 终止流程。
            raise

        return diff_files


# ---------------------------------------------------------------------------
# 本地测试桩：直接运行本文件可快速验证抓取逻辑
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # TODO: 运行前请将下面两个变量替换为你要测试的真实仓库与 PR 号。
    repo_name: str = "owner/repo"  # 例如 "octocat/Hello-World"
    pr_number: int = 1             # 例如 1

    # 初始化抓取器并获取 diff。
    fetcher = GitHubPRFetcher()
    files = fetcher.get_pr_diff(repo_name=repo_name, pr_number=pr_number)

    # 打印抓取结果概览。
    print(f"共获取到 {len(files)} 个含 diff 的文件。")
    if files:
        first = files[0]
        print(f"\n===== 第一个文件：{first['filename']} =====")
        print(first["patch"])
    else:
        print("该 PR 没有包含文本变更的文件（可能全部为二进制文件，或 PR 为空）。")
