"""feedback_poster.py —— 反馈发布模块。

本模块是 Autonomous-PR-Reviewer 工作流的 Step 4（Feedback Posting）。
职责：将 Step 3（ai_reviewer）产出的 Markdown 审查结果，通过 GitHub API
以「整体评论」（Issue Comment）的形式发布到目标 PR 的会话区。

MVP 决策：本阶段只做 Issue Comment（pr.create_issue_comment），不做行级 Review Comment，
以稳定性优先（避免 LLM 算错行号导致 GitHub API 报错）。

设计原则：
    - 防御性编程：API 调用 try-except 捕获 GithubException，记录日志后向上抛出。
    - 日志记录：使用 logging。
    - 类型注解 + 中文 Docstring。
    - 模块化：本模块只负责「格式化 + 发布评论」，不掺入抓取或 AI 调用逻辑。
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from github import Auth, Github, GithubException

# 加载 .env 中的 GITHUB_TOKEN。
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

# 隐藏标记：写在评论正文里（HTML 注释，渲染时不可见），便于未来识别 / 更新机器人评论。
_COMMENT_MARKER = "<!-- autonomous-pr-reviewer -->"

# 评论标题与签名。
_COMMENT_TITLE = "## 🤖 Autonomous PR Reviewer"
_COMMENT_FOOTER = "\n\n---\n<sub>本评论由 Autonomous-PR-Reviewer 自动生成。</sub>"


class FeedbackPoster:
    """PR 反馈发布器。

    负责初始化 GitHub 客户端，并将 Markdown 审查结果发布为 PR 的 Issue Comment。
    """

    def __init__(self) -> None:
        """初始化 GitHub 客户端。

        从环境变量 ``GITHUB_TOKEN`` 读取凭证并构造已认证的 :class:`github.Github` 客户端。

        Raises:
            ValueError: 当环境变量 ``GITHUB_TOKEN`` 未设置或为空时抛出。
        """
        token: str | None = os.getenv("GITHUB_TOKEN")
        if not token:
            logger.error("环境变量 GITHUB_TOKEN 未设置，无法初始化 GitHub 客户端。")
            raise ValueError("未检测到 GITHUB_TOKEN，请在 .env 文件中配置后重试。")

        self._client: Github = Github(auth=Auth.Token(token))
        logger.info("反馈发布器初始化成功。")

    def _format_comment(self, review_markdown: str) -> str:
        """将审查正文包装为最终的评论 Markdown。

        在审查内容外加上统一的标题、签名与隐藏标记，便于识别与未来扩展。

        Args:
            review_markdown: Step 3 产出的 Markdown 审查正文。

        Returns:
            可直接作为评论发布的完整 Markdown 文本。
        """
        return f"{_COMMENT_MARKER}\n{_COMMENT_TITLE}\n\n{review_markdown.strip()}{_COMMENT_FOOTER}"

    def _find_existing_comment(self, pull_request: object) -> object | None:
        """在 PR 已有评论中查找本工具上次发布的评论（按隐藏标记识别）。

        Args:
            pull_request: PyGithub 的 PullRequest 对象。

        Returns:
            匹配到隐藏标记的 IssueComment 对象；未找到则返回 None。
        """
        for comment in pull_request.get_issue_comments():
            if _COMMENT_MARKER in (comment.body or ""):
                return comment
        return None

    def post_review(
        self,
        repo_name: str,
        pr_number: int,
        review_markdown: str,
        update_existing: bool = True,
    ) -> str:
        """将审查结果作为 Issue Comment 发布 / 更新到指定 PR。

        当 ``update_existing`` 为 True 时，优先查找本工具上次发布的评论（按隐藏标记识别），
        找到则原地更新（edit）而非新建，避免在 PR 多次 push 时刷屏。

        Args:
            repo_name: 仓库全名，格式 ``"owner/repo"``。
            pr_number: 目标 Pull Request 编号。
            review_markdown: 待发布的 Markdown 审查正文（通常来自 AIReviewer.analyze_pr）。
            update_existing: 是否复用并更新已有的机器人评论；默认 True。

        Returns:
            评论的 HTML 链接（html_url），便于日志记录与跳转查看。

        Raises:
            ValueError: 当 review_markdown 为空时抛出，避免发布无意义的空评论。
            github.GithubException: 当仓库 / PR 不存在、Token 权限不足或其它 API 错误时抛出
                （已记录日志后向上抛出）。
        """
        if not review_markdown or not review_markdown.strip():
            logger.error("审查内容为空，拒绝发布空评论。")
            raise ValueError("review_markdown 不能为空。")

        body = self._format_comment(review_markdown)

        try:
            repo = self._client.get_repo(repo_name)
            pull_request = repo.get_pull(pr_number)

            existing = self._find_existing_comment(pull_request) if update_existing else None
            if existing is not None:
                logger.info("发现既有机器人评论，更新 %s 的 PR #%d 评论 ...", repo_name, pr_number)
                existing.edit(body)
                comment = existing
            else:
                logger.info("正在向 %s 的 PR #%d 发布审查评论 ...", repo_name, pr_number)
                comment = pull_request.create_issue_comment(body)
        except GithubException as exc:
            logger.error(
                "发布 PR 评论失败（repo=%s, pr=%d）：status=%s, data=%s",
                repo_name,
                pr_number,
                getattr(exc, "status", "N/A"),
                getattr(exc, "data", str(exc)),
            )
            raise

        logger.info("审查评论发布成功：%s", comment.html_url)
        return comment.html_url


# ---------------------------------------------------------------------------
# 本地测试桩：向指定 PR 发布一条示例评论（会真实写入 GitHub，请谨慎运行）
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # TODO: 运行前请填入真实仓库与 PR 号。注意：这会在该 PR 下真实创建一条评论。
    repo_name: str = "owner/repo"  # 例如 "beiye66/container-monitor"
    pr_number: int = 1

    sample_review = (
        "## 变更总结\n这是一条用于验证发布链路的示例审查。\n\n"
        "## 风险审查\n未发现明显的高风险问题。"
    )

    poster = FeedbackPoster()
    url = poster.post_review(repo_name=repo_name, pr_number=pr_number, review_markdown=sample_review)
    print(f"评论已发布：{url}")
