"""pr_url.py —— GitHub PR 链接解析工具。

供 Web 体验端（app.py）使用：将用户粘贴的 PR 链接解析为 ``owner/repo`` 与 PR 号。
单独成模块以便单元测试（不依赖 Streamlit / 网络）。
"""

from __future__ import annotations

import re

# 匹配形如 https://github.com/owner/repo/pull/123 的链接（允许 http/https、结尾带 /files 等）。
_PR_URL_RE = re.compile(
    r"github\.com/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+)/pull/(?P<number>\d+)",
    re.IGNORECASE,
)


def parse_pr_url(url: str) -> tuple[str, int]:
    """从 GitHub PR 链接中解析出仓库全名与 PR 号。

    Args:
        url: 形如 ``https://github.com/owner/repo/pull/123`` 的 PR 链接。

    Returns:
        ``(repo_full_name, pr_number)`` 二元组，例如 ``("owner/repo", 123)``。

    Raises:
        ValueError: 当链接为空或格式不符合预期时抛出（附友好中文提示）。
    """
    if not url or not url.strip():
        raise ValueError("请输入一个 GitHub PR 链接。")

    match = _PR_URL_RE.search(url.strip())
    if not match:
        raise ValueError(
            "链接格式不正确，请输入形如 https://github.com/owner/repo/pull/123 的公开 PR 链接。"
        )

    repo_full_name = f"{match.group('owner')}/{match.group('repo')}"
    pr_number = int(match.group("number"))
    return repo_full_name, pr_number
