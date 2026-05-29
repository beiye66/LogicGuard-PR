"""github_service 模块的单元测试。

全部使用 unittest.mock 假冒 PyGithub 客户端，
因此不依赖真实 GITHUB_TOKEN、不发起任何网络请求，可在 CI 中稳定运行。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from github import GithubException

from github_service import GitHubPRFetcher


def _make_file(filename: str, patch_content: str | None) -> MagicMock:
    """构造一个模拟的 PR 变更文件对象。

    Args:
        filename: 文件路径。
        patch_content: 该文件的 diff 文本；传 None 模拟二进制文件。

    Returns:
        带有 .filename 与 .patch 属性的 Mock 对象。
    """
    mock_file = MagicMock()
    mock_file.filename = filename
    mock_file.patch = patch_content
    return mock_file


def test_missing_token_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """未配置 GITHUB_TOKEN 时，初始化应抛出 ValueError（早失败）。"""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(ValueError):
        GitHubPRFetcher()


@patch("github_service.Github")
def test_get_pr_diff_filters_files(
    mock_github_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """get_pr_diff 应只保留含 patch 的文件，过滤二进制与空 diff 文件。"""
    monkeypatch.setenv("GITHUB_TOKEN", "dummy-token")

    # 组装 mock：client -> repo -> pull -> get_files()
    mock_client = MagicMock()
    mock_github_cls.return_value = mock_client
    mock_pr = MagicMock()
    mock_pr.get_files.return_value = [
        _make_file("src/a.py", "@@ -1 +1 @@\n+changed"),  # 有 diff，应保留
        _make_file("assets/logo.png", None),               # 二进制（patch=None），应过滤
        _make_file("src/empty.py", ""),                     # 空 diff（falsy），应过滤
    ]
    mock_client.get_repo.return_value.get_pull.return_value = mock_pr

    fetcher = GitHubPRFetcher()
    result = fetcher.get_pr_diff("owner/repo", 1)

    assert result == [{"filename": "src/a.py", "patch": "@@ -1 +1 @@\n+changed"}]
    mock_client.get_repo.assert_called_once_with("owner/repo")
    mock_client.get_repo.return_value.get_pull.assert_called_once_with(1)


@patch("github_service.Github")
def test_get_pr_diff_reraises_api_error(
    mock_github_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GitHub API 出错（如 404）时，应记录日志后向上抛出 GithubException。"""
    monkeypatch.setenv("GITHUB_TOKEN", "dummy-token")

    mock_client = MagicMock()
    mock_github_cls.return_value = mock_client
    mock_client.get_repo.side_effect = GithubException(404, {"message": "Not Found"}, {})

    fetcher = GitHubPRFetcher()
    with pytest.raises(GithubException):
        fetcher.get_pr_diff("owner/does-not-exist", 999)


@patch("github_service.Github")
def test_get_pr_diff_empty_when_no_text_changes(
    mock_github_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """当 PR 全部为二进制/无文本变更文件时，应返回空列表。"""
    monkeypatch.setenv("GITHUB_TOKEN", "dummy-token")

    mock_client = MagicMock()
    mock_github_cls.return_value = mock_client
    mock_pr = MagicMock()
    mock_pr.get_files.return_value = [_make_file("a.bin", None)]
    mock_client.get_repo.return_value.get_pull.return_value = mock_pr

    fetcher = GitHubPRFetcher()
    assert fetcher.get_pr_diff("owner/repo", 1) == []
