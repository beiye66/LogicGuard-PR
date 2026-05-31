## LogicGuard – AI PR Reviewer v1.0.0 🎉

首个正式版本。一个全自动的 AI 代码评审 GitHub Action：当开发者提交 Pull Request 时，
自动抓取代码变更、用大语言模型审查，并将「变更总结 + 风险清单」回帖到 PR 评论区。

### ✨ 核心能力
- 🔍 **聚焦高风险**：并发竞态、内存/资源、逻辑错误、边界情况；定位到**文件 + 行号**，**低误报**（无问题不瞎报）
- 🧩 **多模型路由**：OpenAI / DeepSeek / Gemini / 豆包（OpenAI 兼容）+ Claude（Anthropic），配置即切换
- ♻️ **增量审查**：PR 多次推送只审新增改动，节省 token
- 💬 **评论防刷屏**：原地更新同一条评论，而非反复新建

### 🚀 快速使用
在你的仓库新建 `.github/workflows/ai-review.yml`：

```yaml
name: AI PR Review
on:
  pull_request:
    types: [opened, reopened, synchronize]
permissions:
  contents: read
  pull-requests: write
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: beiye66/LogicGuard-PR@v1.0.0
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          llm-api-key: ${{ secrets.LLM_API_KEY }}
          llm-base-url: ${{ vars.LLM_BASE_URL }}   # 例：https://api.deepseek.com
          llm-model: ${{ vars.LLM_MODEL }}          # 例：deepseek-chat
```

再到仓库 **Settings → Secrets and variables → Actions** 配置 `LLM_API_KEY` 即可。

### ⚙️ 输入参数
| 输入 | 必填 | 说明 |
|---|---|---|
| `github-token` | 是 | 一般传 `secrets.GITHUB_TOKEN` |
| `llm-api-key` | 是 | 大模型 API Key |
| `llm-base-url` | 否 | OpenAI 兼容端点（留空默认 DeepSeek）|
| `llm-model` | 否 | 模型 ID（留空默认 deepseek-chat）|
| `llm-provider` | 否 | `openai` / `anthropic`（留空按模型名推断）|
