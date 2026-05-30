"""main.py —— Autonomous-PR-Reviewer 编排入口。

串联完整工作流：
    Step 1 GitHubPRFetcher.get_pr_diff   抓取 PR diff
    Step 2 ContextBuilder（封装在 Step 3 内）  token 预算融合 / 截断
    Step 3 AIReviewer.analyze_pr          LLM 智能审查
    Step 4 FeedbackPoster.post_review     发布 / 更新 PR 评论

运行目标（仓库与 PR 号）来源优先级：命令行参数 > 环境变量。
    - 仓库：``--repo`` 或环境变量 ``GITHUB_REPOSITORY``（GitHub Actions 自动注入 owner/repo）。
    - PR 号：``--pr`` 或环境变量 ``PR_NUMBER``（workflow 中由 ${{ github.event.pull_request.number }} 注入）。

凭证与模型配置统一从环境变量 / .env 读取（GITHUB_TOKEN / LLM_API_KEY / LLM_BASE_URL / LLM_MODEL）。
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from ai_reviewer import AIReviewer
from feedback_poster import FeedbackPoster
from github_service import GitHubPRFetcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析命令行参数。

    Args:
        argv: 参数列表；为 None 时使用 ``sys.argv``。

    Returns:
        解析后的 Namespace，含 ``repo`` 与 ``pr`` 两个可选项。
    """
    parser = argparse.ArgumentParser(description="Autonomous-PR-Reviewer 编排入口")
    parser.add_argument("--repo", help="仓库全名 owner/repo；缺省读环境变量 GITHUB_REPOSITORY")
    parser.add_argument("--pr", type=int, help="Pull Request 编号；缺省读环境变量 PR_NUMBER")
    return parser.parse_args(argv)


def resolve_target(args: argparse.Namespace) -> tuple[str, int]:
    """根据「命令行 > 环境变量」的优先级解析出审查目标。

    Args:
        args: 命令行参数 Namespace。

    Returns:
        ``(repo_name, pr_number)`` 二元组。

    Raises:
        ValueError: 当仓库或 PR 号缺失、或 PR 号非整数时抛出。
    """
    repo_name = args.repo or os.getenv("GITHUB_REPOSITORY")
    raw_pr = args.pr if args.pr is not None else os.getenv("PR_NUMBER")

    if not repo_name:
        raise ValueError("缺少仓库信息：请用 --repo 或设置环境变量 GITHUB_REPOSITORY。")
    if raw_pr is None or str(raw_pr).strip() == "":
        raise ValueError("缺少 PR 号：请用 --pr 或设置环境变量 PR_NUMBER。")

    try:
        pr_number = int(raw_pr)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"PR 号必须为整数，收到：{raw_pr!r}") from exc

    return repo_name, pr_number


def run_review(repo_name: str, pr_number: int) -> str | None:
    """对指定 PR 执行完整审查流程并发布结果。

    Args:
        repo_name: 仓库全名 ``owner/repo``。
        pr_number: Pull Request 编号。

    Returns:
        发布 / 更新评论的 html_url；若 PR 无可分析的代码变更则返回 None（跳过发布）。
    """
    # Step 1：抓取 diff。
    fetcher = GitHubPRFetcher()
    diff_data = fetcher.get_pr_diff(repo_name, pr_number)
    if not diff_data:
        logger.info("PR #%d 无可分析的文本变更，跳过审查与评论。", pr_number)
        return None

    # Step 2 + 3：AIReviewer 内部复用 ContextBuilder 做截断融合，再调用 LLM。
    reviewer = AIReviewer()
    review_markdown = reviewer.analyze_pr(diff_data)

    # Step 4：发布 / 更新评论。
    poster = FeedbackPoster()
    url = poster.post_review(repo_name, pr_number, review_markdown)
    return url


def main(argv: list[str] | None = None) -> int:
    """命令行入口。

    Args:
        argv: 参数列表；为 None 时使用 ``sys.argv``。

    Returns:
        进程退出码：0 成功，1 失败（配置缺失或运行期异常）。
    """
    args = _parse_args(argv)
    try:
        repo_name, pr_number = resolve_target(args)
        logger.info("开始审查：%s PR #%d", repo_name, pr_number)
        url = run_review(repo_name, pr_number)
        if url:
            logger.info("审查完成，评论地址：%s", url)
        else:
            logger.info("审查结束：无需发布评论。")
        return 0
    except Exception as exc:  # noqa: BLE001 —— 入口处统一兜底，记录后以非零码退出
        logger.error("审查流程失败：%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
