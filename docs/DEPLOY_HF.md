# 部署 Web 体验端到 Hugging Face Spaces

本文档说明如何把 `app.py`（Streamlit）部署为公网可访问的在线体验端，让评委**零配置**直接试用。
选择 Hugging Face Spaces 的原因：免费、自带公网 URL、**服务器在海外**（可正常连通 Gemini 等接口）。

## 步骤

### 1. 创建 Space
- 登录 https://huggingface.co/ → 右上角 **New → Space**。
- **Space name**：自定义（如 `autonomous-pr-reviewer`）。
- **SDK**：选择 **Streamlit**。
- **Hardware**：免费的 CPU basic 即可。
- 可见性选 **Public**。

### 2. 上传代码
把本项目的以下内容放进 Space 仓库（Space 本身就是一个 git 仓库）：
- `app.py`（必须在根目录）
- `src/` 整个目录
- `requirements.txt`

最简单的方式：在 Space 页面 **Files → Add file → Upload files**，把上述文件/目录拖进去；
或用 git 把 Space 远程添加为 remote 后 push。

> Space 启动时会自动 `pip install -r requirements.txt` 并运行 `app.py`。

### 3. 配置密钥（关键）
进入 Space 的 **Settings → Variables and secrets**，添加：

| 类型 | 名称 | 值 |
|---|---|---|
| Secret | `GITHUB_TOKEN` | 你的 GitHub Token（读取公开 PR 即可，权限要求很低）|
| Secret | `LLM_API_KEY` | 你的大模型 API Key |
| Variable | `LLM_BASE_URL` | 如 Gemini：`https://generativelanguage.googleapis.com/v1beta/openai/` |
| Variable | `LLM_MODEL` | 如 `gemini-2.5-flash` |
| Variable | `LLM_PROVIDER`（可选）| `openai` / `anthropic`；留空按模型名推断 |

> 这些会作为环境变量注入容器，代码用 `os.getenv` 读取，**不会出现在代码里**。

### 4. 等待构建并访问
保存后 Space 会自动重新构建（约 1–3 分钟），完成后即可通过
`https://huggingface.co/spaces/<你的用户名>/<space名>` 访问。
把这个链接填进项目 README 顶部的「在线体验」位置。

## 注意事项
- **示例 PR 用公开仓库**：`app.py` 中 `EXAMPLE_PRS` 请指向**公开** PR，确保评委点击即可访问。
- **模型配额**：若用 Gemini 免费层，注意每日配额；评委集中试用时可能触发限流（已做结果缓存缓解）。
  如需更稳，可改用已充值的厂商或更高配额的模型。
- Web 端只展示审查结果，**不会向 GitHub 发布评论**（无需写权限）。
