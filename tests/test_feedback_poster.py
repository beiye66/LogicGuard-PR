"""feedback_poster 模块的单元测试。

通过 mock 假冒 PyGithub 客户端，不依赖真实 GITHUB_TOKEN、不发起网络请求。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from github import GithubException

from feedback_poster import FeedbackPoster


def test_missing_token_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """未配置 GITHUB_TOKEN 时，初始化应抛出 ValueError。"""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(ValueError):
        FeedbackPoster()


@patch("feedback_poster.Github")
def test_post_review_creates_issue_comment(
    mock_github_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """无既有评论时，post_review 应新建评论，正文含标题/标记，并返回 html_url。"""
    monkeypatch.setenv("GITHUB_TOKEN", "dummy-token")

    mock_client = MagicMock()
    mock_github_cls.return_value = mock_client
    mock_pr = MagicMock()
    mock_pr.get_issue_comments.return_value = []  # 没有既有的机器人评论
    mock_comment = MagicMock()
    mock_comment.html_url = "https://github.com/owner/repo/pull/1#issuecomment-1"
    mock_pr.create_issue_comment.return_value = mock_comment
    mock_client.get_repo.return_value.get_pull.return_value = mock_pr

    poster = FeedbackPoster()
    url = poster.post_review("owner/repo", 1, "## 变更总结\n做了改动。")

    assert url == "https://github.com/owner/repo/pull/1#issuecomment-1"
    mock_client.get_repo.assert_called_once_with("owner/repo")
    mock_client.get_repo.return_value.get_pull.assert_called_once_with(1)

    # 校验发布的正文经过包装：含隐藏标记与标题，且保留原始审查内容。
    posted_body = mock_pr.create_issue_comment.call_args.args[0]
    assert "<!-- autonomous-pr-reviewer -->" in posted_body
    assert "🤖 Autonomous PR Reviewer" in posted_body
    assert "做了改动。" in posted_body


@patch("feedback_poster.Github")
def test_post_review_updates_existing_comment(
    mock_github_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """存在带隐藏标记的既有评论时，应更新（edit）而非新建。"""
    monkeypatch.setenv("GITHUB_TOKEN", "dummy-token")

    mock_client = MagicMock()
    mock_github_cls.return_value = mock_client
    mock_pr = MagicMock()

    existing = MagicMock()
    existing.body = "<!-- autonomous-pr-reviewer -->\n## 🤖 Autonomous PR Reviewer\n旧内容"
    existing.html_url = "https://github.com/owner/repo/pull/1#issuecomment-old"
    other = MagicMock()
    other.body = "一条普通的人工评论"
    mock_pr.get_issue_comments.return_value = [other, existing]
    mock_client.get_repo.return_value.get_pull.return_value = mock_pr

    poster = FeedbackPoster()
    url = poster.post_review("owner/repo", 1, "## 变更总结\n新内容。")

    assert url == "https://github.com/owner/repo/pull/1#issuecomment-old"
    existing.edit.assert_called_once()
    mock_pr.create_issue_comment.assert_not_called()
    assert "新内容。" in existing.edit.call_args.args[0]


@patch("feedback_poster.Github")
def test_post_review_rejects_empty_review(
    mock_github_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """审查内容为空时应抛出 ValueError，且不调用 API。"""
    monkeypatch.setenv("GITHUB_TOKEN", "dummy-token")
    mock_client = MagicMock()
    mock_github_cls.return_value = mock_client

    poster = FeedbackPoster()
    with pytest.raises(ValueError):
        poster.post_review("owner/repo", 1, "   ")

    mock_client.get_repo.assert_not_called()


@patch("feedback_poster.Github")
def test_post_review_reraises_api_error(
    mock_github_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GitHub API 出错时应记录日志后向上抛出 GithubException。"""
    monkeypatch.setenv("GITHUB_TOKEN", "dummy-token")
    mock_client = MagicMock()
    mock_github_cls.return_value = mock_client
    mock_client.get_repo.side_effect = GithubException(403, {"message": "Forbidden"}, {})

    poster = FeedbackPoster()
    with pytest.raises(GithubException):
        poster.post_review("owner/repo", 1, "## 变更总结\nok")
