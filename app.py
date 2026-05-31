"""app.py —— LogicGuard – AI PR Reviewer 的 Web 体验端（Streamlit）。

面向评委 / 试用者：粘贴任意**公开** GitHub PR 链接，后端复用项目的完整 Pipeline
（GitHubPRFetcher → ContextBuilder → AIReviewer）跑一遍审查，并把 Markdown 结果渲染到页面。
Web 端只做"展示"，不调用 FeedbackPoster（不往 GitHub 发真实评论）。

模型来源支持两种：
    - 使用本站默认模型（服务器通过环境变量配置的密钥与模型）。
    - 自带 API Key（BYOK）：用户在侧边栏选厂商、填自己的 Key 与模型，本次审查走用户自己的额度。
      Key 仅用于本次请求，不存储、不记录。

部署：Hugging Face Spaces（Docker SDK）。默认模型的密钥通过 Space Secrets 注入环境变量：
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
from llm_client import LLMError, build_llm_client  # noqa: E402
from pr_url import parse_pr_url  # noqa: E402

# 预设示例 PR（可替换为你的公开演示 PR）。
EXAMPLE_PRS: list[tuple[str, str]] = [
    ("🐞 示例：含隐患的演示 PR", "https://github.com/beiye66/container-monitor/pull/1"),
]

# BYOK 厂商预设：名称 -> (provider, base_url, 默认模型)。
PROVIDER_PRESETS: dict[str, tuple[str, str, str]] = {
    "DeepSeek": ("openai", "https://api.deepseek.com", "deepseek-chat"),
    "Gemini": ("openai", "https://generativelanguage.googleapis.com/v1beta/openai/", "gemini-2.5-flash"),
    "豆包（火山方舟）": ("openai", "https://ark.cn-beijing.volces.com/api/v3", ""),
    "OpenAI": ("openai", "https://api.openai.com/v1", "gpt-4o"),
    "Claude（Anthropic）": ("anthropic", "", "claude-sonnet-4-6"),
    "自定义（OpenAI 兼容）": ("openai", "", ""),
}

st.set_page_config(page_title="LogicGuard – AI PR Reviewer", page_icon="🤖", layout="centered")


@st.cache_resource(show_spinner=False)
def _get_fetcher() -> GitHubPRFetcher:
    """构造并缓存 GitHub 数据抓取器（用服务器环境的 GITHUB_TOKEN 读取公开 PR）。"""
    return GitHubPRFetcher()


@st.cache_resource(show_spinner=False)
def _get_default_reviewer() -> AIReviewer:
    """构造并缓存"本站默认模型"的审查器（读取服务器环境变量中的密钥与模型）。"""
    return AIReviewer()


@st.cache_data(show_spinner=False, ttl=3600)
def _run_review(repo_full_name: str, pr_number: int, cache_label: str, _reviewer: AIReviewer) -> dict:
    """对指定 PR 执行抓取 + AI 审查（按 仓库/PR/模型 缓存 1 小时，避免重复消耗配额）。

    Args:
        repo_full_name: 仓库全名 ``owner/repo``。
        pr_number: PR 号。
        cache_label: 用于区分缓存的标签（含模型来源与模型名；不含密钥）。
        _reviewer: AI 审查器；下划线前缀使 Streamlit 不对其做哈希（不参与缓存键）。

    Returns:
        含 ``file_count`` 与 ``markdown`` 的结果字典；无可分析变更时 ``file_count`` 为 0。
    """
    pr_diff = _get_fetcher().get_pr_diff(repo_full_name, pr_number)
    if not pr_diff.files:
        return {"file_count": 0, "markdown": ""}
    markdown = _reviewer.analyze_pr(pr_diff.files)
    return {"file_count": len(pr_diff.files), "markdown": markdown}


def _render_sidebar() -> dict:
    """渲染左侧「模型设置」侧边栏并返回所选配置。"""
    with st.sidebar:
        st.header("⚙️ 模型设置")
        mode = st.radio("模型来源", ["使用本站默认模型", "自带 API Key（BYOK）"], index=0)

        if mode == "使用本站默认模型":
            st.caption(f"当前默认模型：`{os.getenv('LLM_MODEL') or 'deepseek-chat'}`")
            return {"mode": "default"}

        st.caption("🔒 你的 Key 仅用于本次审查，不会被存储或记录。")
        preset_name = st.selectbox("厂商", list(PROVIDER_PRESETS.keys()))
        provider, base_url, default_model = PROVIDER_PRESETS[preset_name]

        api_key = st.text_input("API Key", type="password", placeholder="粘贴你的 API Key")
        if preset_name == "豆包（火山方舟）":
            model = st.text_input("接入点 ID（Endpoint ID）", value=default_model, placeholder="ep-xxxxxxxx")
        else:
            model = st.text_input("模型", value=default_model)
        if preset_name == "自定义（OpenAI 兼容）":
            base_url = st.text_input("Base URL", value="", placeholder="https://...")

        return {
            "mode": "byok",
            "provider": provider,
            "api_key": api_key,
            "model": model,
            "base_url": base_url,
            "preset": preset_name,
        }


def _build_reviewer(config: dict) -> tuple[AIReviewer, str]:
    """根据侧边栏配置构建审查器，并返回用于缓存区分的标签。

    Raises:
        ValueError: BYOK 模式下未填 API Key。
        LLMError: 配置非法（如不支持的 provider）。
    """
    if config["mode"] == "default":
        return _get_default_reviewer(), f"default:{os.getenv('LLM_MODEL') or 'deepseek-chat'}"

    if not (config["api_key"] or "").strip():
        raise ValueError("请在左侧「模型设置」中填写你的 API Key。")

    client = build_llm_client(
        config["provider"], config["api_key"], config["model"], config["base_url"]
    )
    cache_label = f"byok:{config['provider']}:{config['model']}"
    return AIReviewer(llm_client=client), cache_label


def _do_review(url: str, reviewer: AIReviewer, cache_label: str) -> None:
    """解析链接、运行审查并渲染结果（含友好错误提示）。"""
    try:
        repo_full_name, pr_number = parse_pr_url(url)
    except ValueError as exc:
        st.error(f"⚠️ {exc}")
        return

    try:
        with st.spinner(f"🤖 正在抓取 `{repo_full_name}` PR #{pr_number} 的代码变更并调用大模型审查，请稍候…"):
            result = _run_review(repo_full_name, pr_number, cache_label, reviewer)
    except Exception as exc:  # noqa: BLE001 —— 体验端统一兜底，给出友好提示
        st.error(
            "❌ 审查失败：可能是 PR 不存在 / 仓库非公开，或大模型接口暂时不可用（如配额、Key 无效）。\n\n"
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
    config = _render_sidebar()

    st.title("🤖 LogicGuard – AI PR Reviewer")
    st.caption("AI 自动代码评审工具 · 在线体验端")
    st.markdown(
        "粘贴任意**公开** GitHub PR 链接，AI 会自动抓取代码变更，给出 **变更总结** 与 "
        "**风险审查**（聚焦并发、内存、逻辑、边界等高风险问题，低误报）。\n\n"
        "> 无需登录，开箱即用；也可在左侧「模型设置」**自带 API Key** 用你自己的模型。"
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
        try:
            reviewer, cache_label = _build_reviewer(config)
        except (ValueError, LLMError) as exc:
            st.warning(f"⚠️ {exc}")
        else:
            _do_review(st.session_state.pr_url_input, reviewer, cache_label)

    # 页脚：展示当前模型来源。
    if config["mode"] == "byok":
        source = f"你自带的模型（{config['preset']}：`{config['model'] or '默认'}`）"
    else:
        source = f"本站默认模型：`{os.getenv('LLM_MODEL') or 'deepseek-chat'}`"
    st.divider()
    st.caption(f"由 LogicGuard – AI PR Reviewer 提供支持 · {source} · 本页面仅展示审查结果，不发布评论。")


if __name__ == "__main__":
    main()
