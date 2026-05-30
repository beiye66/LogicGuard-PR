# 测试计划（Test Plan）

本文件说明 Autonomous-PR-Reviewer 的测试策略：**自动化单元测试** + **端到端集成演示**，并给出用于 README / 视频讲解的**截图复现步骤**。

---

## 1. 测试目标

| 目标 | 验证内容 |
|---|---|
| 功能正确性 | 四步 Pipeline 各模块在正常 / 异常输入下行为符合预期 |
| 鲁棒性 | 缺失配置早失败、API 异常被捕获、网络错误自动重试 |
| 防回归 | 每次 PR / push 自动跑测试，保证 `main` 始终可运行 |
| 端到端 | 真实 PR 触发 → 自动抓取 → AI 审查 → 自动评论 全链路可用 |

---

## 2. 自动化单元测试（共 50 个用例）

全部使用 `unittest.mock` 假冒外部依赖，**不需要真实 Token / 网络**，可在 CI 稳定运行。

| 测试文件 | 用例数 | 覆盖要点 |
|---|---|---|
| `tests/test_github_service.py` | 7 | diff 过滤、缺 Token 早失败、API 异常抛出、**增量比较 / 无新提交 / force-push 回退全量** |
| `tests/test_context_builder.py` | 7 | token 估算、参数校验、预算内全纳入、单文件截断、超预算省略、空输入 |
| `tests/test_ai_reviewer.py` | 3 | 返回 Markdown、空 diff 跳过 LLM、LLMError 包装为 RuntimeError |
| `tests/test_llm_client.py` | 13 | 厂商路由（provider 选择 / 模型名推断 / 缺 Key / 非法 provider）、双后端 complete 与异常包装、**BYOK build_llm_client 显式构建** |
| `tests/test_feedback_poster.py` | 8 | 缺 Token 早失败、新建评论、**更新既有评论（upsert）**、空内容拒发、API 异常、**SHA 写入标记 / 读取上次 SHA** |
| `tests/test_main.py` | 8 | 目标解析（CLI 优先 / 环境变量回退 / 缺失 / 非整数）、流程编排（含增量）、无新增跳过、退出码 |
| `tests/test_pr_url.py` | 4 | PR 链接解析（标准 / 带后缀空白 / 空 / 非法） |

**运行方式：**

```bash
pytest -v          # 本地全部测试
python -m compileall src   # 语法编译检查（与 CI 一致）
```

CI 配置见 [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)，在 push 到 `main` 与任意 PR 时自动执行。

---

## 3. 端到端集成演示（用于截图 / 录屏）

> 目的：真实跑一遍"开 PR → 自动审查 → 自动评论"，并产出 README 所需截图。

### 前置条件
- 仓库已在 **Settings → Secrets and variables → Actions** 配置：
  - Secret `LLM_API_KEY`
  - Variable `LLM_BASE_URL`、`LLM_MODEL`

### 步骤
1. **准备一个含隐患的演示分支**（示例：`examples/payment_demo.py` 中故意埋入"未加锁的共享变量自增"与"未校验空列表的除法"）。
2. 基于该分支**开一个 PR**（base = `main`）。
3. 等待 **AI PR Review** Action 自动运行（约 20–40 秒）。
4. 刷新 PR 页面，查看 `github-actions[bot]` 自动发布的审查评论。

### 预期结果（验收标准）
- ✅ Action 运行成功（绿勾），日志中可见 Step1→4 依次执行并打印评论链接。
- ✅ Bot 评论包含「变更总结」与「风险审查」两部分。
- ✅ 风险审查**准确指出两处隐患**（并发竞态 + 除零）并**定位到文件与行号**。
- ✅ 对该 PR 再次 push 新 commit 时，**更新原评论**而非新建（防刷屏）。

> ⚠️ 演示 PR 含故意 bug，**验证完关闭即可，请勿合并进 `main`**。

---

## 4. 截图清单（对应 README）

完成上述演示后，按下列文件名保存截图到 [`images/`](images/) 目录：

| 截图 | 文件名 | 取自 |
|---|---|---|
| Action 运行成功日志 | `action-run-success.png` | PR 的 Checks → 运行 AI 审查步骤 |
| Bot 审查评论 | `bot-review-comment.png` | PR 会话区的 Bot 评论 |
| 测试通过 | `ci-tests-passing.png` | 本地 `pytest -v` 输出，或 CI 绿勾 |
