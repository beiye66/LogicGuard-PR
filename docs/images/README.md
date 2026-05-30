# 演示截图目录

本目录存放 README 中引用的演示截图。请按下表的**文件名**保存截图（README 已按这些名字引用，放进来即可显示）。

| 文件名 | 内容 | 如何获取 |
|---|---|---|
| `action-run-success.png` | GitHub Action「AI PR Review」运行成功的日志（能看到 Step1→4 依次执行、最后发布评论的链接） | 在触发过审查的 PR → 点 **Checks / Details** → 展开「运行 AI 审查」步骤截图 |
| `bot-review-comment.png` | `github-actions[bot]` 在 PR 下自动发布的审查评论（含变更总结 + 风险清单 + 行号定位） | 打开该 PR 会话区，截取 Bot 评论 |
| `ci-tests-passing.png` | 单元测试全部通过（28 passed）或 CI 绿勾 | 本地运行 `pytest -v` 截图，或 PR 上「CI / test」绿勾的 Details 截图 |

> 复现这些截图的完整步骤见 [`../TEST_PLAN.md`](../TEST_PLAN.md)。
>
> 提示：图片建议宽度 1000px 左右，PNG 格式；命名务必与上表一致，否则 README 中会显示为裂图。
