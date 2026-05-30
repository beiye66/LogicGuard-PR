"""app.py —— Autonomous PR Reviewer 的 Web 体验端（Streamlit）。

面向评委 / 试用者：粘贴任意**公开** GitHub PR 链接，后端复用项目的完整 Pipeline
（GitHubPRFetcher → ContextBuilder → AIReviewer）跑一遍审查，并把 Markdown 结果渲染到页面。
Web 端只做"展示"，不调用 FeedbackPoster（不往 GitHub 发真实评论）。

部署：Hugging Face Spaces（Streamlit SDK）。密钥通过 Space Secrets 注入环境变量：
    GITHUB_TOKEN / LLM_API_KEY / LLM_BASE_URL / LLM_MODEL（可选 LLM_PROVIDER / ANTHROPIC_API_KEY）。
"""

from __future__ import annotations

import os
import pathlib
import sys

import streamlit as st

# 将 src 加入模块搜索路径，以复用项目的核心模块。
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "src"))

from ai_reviewer import AIReviewer  # noqa: E402
from github_service import GitHubPRFetcher  # noqa: E402
from pr_url import parse_pr_url  # noqa: E402

# 预设示例 PR（可替换为你的公开演示 PR；建议指向含明显隐患的公开 PR 以展示效果）。
EXAMPLE_PRS: list[tuple[str, str]] = [
    ("🐞 示例：含隐患的演示 PR", "https://github.com/beiye66/container-monitor/pull/1"),
]

st.set_page_config(page_title="Autonomous PR Reviewer", page_icon="🤖", layout="centered")


@st.cache_resource(show_spinner=False)
def _get_pipeline() -> tuple[GitHubPRFetcher, AIReviewer]:
    """构造并缓存数据抓取器与 AI 审查器（读取环境变量中的密钥与模型配置）。"""
    return GitHubPRFetcher(), AIReviewer()


@st.cache_data(show_spinner=False, ttl=3600)
def _run_review(repo_full_name: str, pr_number: int) -> dict:
    """对指定 PR 执行抓取 + AI 审查（结果缓存 1 小时，避免重复消耗模型配额）。

    Args:
        repo_full_name: 仓库全名 ``owner/repo``。
        pr_number: PR 号。

    Returns:
        含 ``file_count`` 与 ``markdown`` 的结果字典；无可分析变更时 ``file_count`` 为 0。
    """
    fetcher, reviewer = _get_pipeline()
    pr_diff = fetcher.get_pr_diff(repo_full_name, pr_number)
    if not pr_diff.files:
        return {"file_count": 0, "markdown": ""}
    markdown = reviewer.analyze_pr(pr_diff.files)
    return {"file_count": len(pr_diff.files), "markdown": markdown}


def _do_review(url: str) -> None:
    """解析链接、运行审查并渲染结果（含友好错误提示）。"""
    try:
        repo_full_name, pr_number = parse_pr_url(url)
    except ValueError as exc:
        st.error(f"⚠️ {exc}")
        return

    try:
        with st.spinner(f"🤖 正在抓取 `{repo_full_name}` PR #{pr_number} 的代码变更并调用大模型审查，请稍候…"):
            result = _run_review(repo_full_name, pr_number)
    except Exception as exc:  # noqa: BLE001 —— 体验端统一兜底，给出友好提示
        st.error(
            "❌ 审查失败：可能是链接对应的 PR 不存在、仓库非公开，或大模型接口暂时不可用。\n\n"
            f"错误详情：{exc}"
        )
        return

    if result["file_count"] == 0:
        st.info("该 PR 没有可分析的文本变更（可能全是二进制文件或为空 PR）。")
        return

    st.success(f"✅ 审查完成！共分析 {result['file_count']} 个文件。")
    st.markdown(result["markdown"])


def main() -> None:
    """渲染页面并处理交互。"""
    st.title("🤖 Autonomous PR Reviewer")
    st.caption("AI 自动代码评审工具 · 在线体验端")
    st.markdown(
        "粘贴任意**公开** GitHub PR 链接，AI 会自动抓取代码变更，给出 **变更总结** 与 "
        "**风险审查**（聚焦并发、内存、逻辑、边界等高风险问题，低误报）。\n\n"
        "> 无需登录、无需配置密钥，开箱即用。"
    )

    # 会话状态：输入框内容与"自动触发"标记。
    if "pr_url_input" not in st.session_state:
        st.session_state.pr_url_input = ""
    if "trigger" not in st.session_state:
        st.session_state.trigger = False

    st.write("**快速体验**（点击示例即自动开始）：")
    cols = st.columns(len(EXAMPLE_PRS))
    for i, (label, url) in enumerate(EXAMPLE_PRS):
        if cols[i].button(label, use_container_width=True):
            st.session_state.pr_url_input = url
            st.session_state.trigger = True
            st.rerun()

    st.text_input(
        "GitHub PR 链接",
        key="pr_url_input",
        placeholder="https://github.com/owner/repo/pull/1",
    )
    start = st.button("🚀 开始审查", type="primary", use_container_width=True)

    if start or st.session_state.trigger:
        st.session_state.trigger = False
        _do_review(st.session_state.pr_url_input)

    # 页脚：展示当前使用的模型，体现"云端服务已集成"。
    model = os.getenv("LLM_MODEL") or "deepseek-chat"
    st.divider()
    st.caption(
        f"由 Autonomous-PR-Reviewer 提供支持 · 当前模型：`{model}` · "
        "本页面仅展示审查结果，不会向 GitHub 发布评论。"
    )


if __name__ == "__main__":
    main()
