# 演示截图目录

本目录存放 README 中引用的演示截图。请按下表的**文件名**保存截图（README 已按这些名字引用，放进来即可显示）。

| 文件名 | 内容 | 如何获取 |
|---|---|---|
| `action-checks-passed.png` | 第三方仓库 PR 上「AI PR Review」检查通过（All checks have passed）的视图 | 该仓库 PR 页面底部「检查」区截图 |
| `action-external-repo.png` | 在第三方仓库（container-monitor）中，工作流详情里 `Run beiye66/LogicGuard-PR@main` 步骤成功执行 | 该仓库 PR → **Actions** → 进入 review 运行 → 截「Run beiye66/LogicGuard-PR@main」那张 |
| `review-issues-found.png` | 含多类隐患的 PR 中，`github-actions[bot]` 列出多条风险（并发/除零/资源泄漏/逻辑/边界）并带行号 | 打开含 bug 的 PR 会话区，截取 Bot 评论 |
| `review-passed.png` | 规范代码的 PR 中，Bot 回复"未发现明显的高风险问题"（低误报） | 打开干净的 PR 会话区，截取 Bot 评论 |

> 复现这些截图的完整步骤见 [`../TEST_PLAN.md`](../TEST_PLAN.md)。
>
> 提示：图片建议宽度 1000px 左右，PNG 格式；命名务必与上表一致，否则 README 中会显示为裂图。
