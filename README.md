# Autonomous-PR-Reviewer

全自动 AI 代码评审工具（最终形态为 GitHub Action）。当开发者在 GitHub 提交 Pull Request 时，
系统自动抓取代码变更（Diff），利用大语言模型（LLM）进行智能审查，并将审查建议自动回复到该 PR 的评论区。

## 核心工作流（Pipeline）

1. **Data Fetching** —— 通过 GitHub Token 获取指定仓库、指定 PR 的所有文件 Diff，过滤二进制与无变更文件。
2. **Context Fusion** —— 对过长 Diff 截断、提取关键上下文，防止超出 LLM 的 token 限制。
3. **AI Analysis** —— 组装两套 Prompt：Task A 生成 PR 总结；Task B 识别严重隐患（低误报）。
4. **Feedback Posting** —— 将结果格式化为 Markdown，通过 GitHub API 发布为 PR 评论。

## 技术栈

- Python 3.10+
- [PyGithub](https://github.com/PyGithub/PyGithub) —— 与 GitHub 通信
- [requests](https://requests.readthedocs.io/) —— 调用外部接口
- [python-dotenv](https://github.com/theskumar/python-dotenv) —— 管理 Token / API Key
- DeepSeek / OpenAI API —— LLM 推理

## 快速开始

```bash
# 1. 创建并激活虚拟环境
python -m venv .venv
# Windows PowerShell:  .\.venv\Scripts\Activate.ps1
# Windows CMD:         .venv\Scripts\activate.bat
# Mac/Linux:           source .venv/bin/activate

# 2. 安装依赖（国内可加清华镜像：-i https://pypi.tuna.tsinghua.edu.cn/simple）
pip install -r requirements.txt

# 3. 配置环境变量
#    复制 .env.example 为 .env，并填入 GITHUB_TOKEN 与 LLM_API_KEY
```

## 目录结构

```
LogicGuard-PR/
├── .env.example           # 环境变量模板
├── requirements.txt       # 依赖清单
└── src/
    └── github_service.py  # Step 1：GitHub 数据接入
```
