"""main 编排模块的单元测试。

通过 mock 替换 Step 1/3/4 的实现类，验证目标解析与流程编排，不依赖真实凭证 / 网络。
"""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

import pytest

import main as main_module
from main import main, resolve_target, run_review


def _ns(repo: str | None, pr: int | None) -> argparse.Namespace:
    """构造一个模拟命令行参数的 Namespace。"""
    return argparse.Namespace(repo=repo, pr=pr)


def test_resolve_target_prefers_cli_args(monkeypatch: pytest.MonkeyPatch) -> None:
    """命令行参数优先于环境变量。"""
    monkeypatch.setenv("GITHUB_REPOSITORY", "env/repo")
    monkeypatch.setenv("PR_NUMBER", "99")
    assert resolve_target(_ns("cli/repo", 7)) == ("cli/repo", 7)


def test_resolve_target_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """命令行缺省时回退到环境变量，并将 PR 号转为 int。"""
    monkeypatch.setenv("GITHUB_REPOSITORY", "env/repo")
    monkeypatch.setenv("PR_NUMBER", "42")
    assert resolve_target(_ns(None, None)) == ("env/repo", 42)


def test_resolve_target_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """仓库或 PR 号缺失时抛出 ValueError。"""
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("PR_NUMBER", raising=False)
    with pytest.raises(ValueError):
        resolve_target(_ns(None, None))


def test_resolve_target_non_int_pr_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """PR 号非整数时抛出 ValueError。"""
    monkeypatch.setenv("PR_NUMBER", "abc")
    with pytest.raises(ValueError):
        resolve_target(_ns("env/repo", None))


@patch("main.FeedbackPoster")
@patch("main.AIReviewer")
@patch("main.GitHubPRFetcher")
def test_run_review_wires_pipeline(
    mock_fetcher_cls: MagicMock,
    mock_reviewer_cls: MagicMock,
    mock_poster_cls: MagicMock,
) -> None:
    """run_review 应依次串联 抓取→审查→发布，并返回评论 url。"""
    mock_fetcher_cls.return_value.get_pr_diff.return_value = [{"filename": "a.py", "patch": "+x"}]
    mock_reviewer_cls.return_value.analyze_pr.return_value = "## 变更总结\nok"
    mock_poster_cls.return_value.post_review.return_value = "https://example/comment"

    url = run_review("owner/repo", 1)

    assert url == "https://example/comment"
    mock_fetcher_cls.return_value.get_pr_diff.assert_called_once_with("owner/repo", 1)
    mock_reviewer_cls.return_value.analyze_pr.assert_called_once_with(
        [{"filename": "a.py", "patch": "+x"}]
    )
    mock_poster_cls.return_value.post_review.assert_called_once_with(
        "owner/repo", 1, "## 变更总结\nok"
    )


@patch("main.FeedbackPoster")
@patch("main.AIReviewer")
@patch("main.GitHubPRFetcher")
def test_run_review_skips_when_no_diff(
    mock_fetcher_cls: MagicMock,
    mock_reviewer_cls: MagicMock,
    mock_poster_cls: MagicMock,
) -> None:
    """无可分析变更时应跳过审查与发布，返回 None。"""
    mock_fetcher_cls.return_value.get_pr_diff.return_value = []

    assert run_review("owner/repo", 1) is None
    mock_reviewer_cls.return_value.analyze_pr.assert_not_called()
    mock_poster_cls.return_value.post_review.assert_not_called()


def test_main_returns_zero_on_success() -> None:
    """main 成功时返回退出码 0。"""
    with patch.object(main_module, "resolve_target", return_value=("owner/repo", 1)), patch.object(
        main_module, "run_review", return_value="https://example/comment"
    ):
        assert main(["--repo", "owner/repo", "--pr", "1"]) == 0


def test_main_returns_one_on_failure() -> None:
    """main 遇到异常时返回退出码 1。"""
    with patch.object(main_module, "resolve_target", side_effect=ValueError("boom")):
        assert main([]) == 1
