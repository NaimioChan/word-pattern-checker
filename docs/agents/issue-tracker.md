# Issue tracker：GitHub

本仓库的 issue 与 spec 都是 GitHub Issues，全部用 `gh` CLI 操作。

## 一条约定：谁写什么

- **issue 是长期工作面**：需求、缺陷、待办、决策记录都挂在 issue 上，跨会话可见。
- **`docs/agent-log.md` 是每会话的流水**：本次做了什么、验了什么、留下什么，收工前写一条。
- 两者都要写，不是二选一。会话开场先读 `docs/agent-log.md` 顶部几条，再动手。

## 常用操作

- **新建 issue**：`gh issue create --title "..." --body "..."`，多行 body 用 heredoc。
- **读 issue**：`gh issue view <number> --json number,title,body,labels,comments`。
- **列 issue**：`gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'`，按需加 `--label` / `--state`。
- **设子 issue**：`gh issue create --parent <parent> ...`，或 `gh issue edit <parent> --add-sub-issue <child>`（gh 2.94+）。旧版用 `gh api --method POST repos/<owner>/<repo>/issues/<parent>/sub_issues -F sub_issue_id=<child-db-id>`（数据库 id，不是 `#number`）。不支持子 issue 时，在子 issue body 顶部写 `Part of #<parent>`。
- **评论**：`gh issue comment <number> --body "..."`
- **加/去标签**：`gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **关闭**：`gh issue close <number> --comment "..."`

仓库从 `git remote -v` 推断，在 clone 内直接跑 `gh` 即可。GitHub 走代理：`export HTTPS_PROXY=http://127.0.0.1:7897`。

## PR 作为请求入口

**PR 作为请求入口：否。** _（若本仓库把外部 PR 当需求来源，改成「是」，`/triage` 会读这个标记。）_

设为「是」时，PR 与 issue 走同一套标签和状态：

- 读 PR：`gh pr view <number> --comments`，看 diff 用 `gh pr diff <number>`。
- 列外部 PR：`gh api --paginate 'repos/{owner}/{repo}/pulls?state=open' --jq '.[] | select(.author_association | IN("OWNER","MEMBER","COLLABORATOR") | not) | {number, title, author: .user.login, author_association, labels: [.labels[].name]}'`。
- 评论 / 标签 / 关闭：`gh pr comment`、`gh pr edit --add-label`/`--remove-label`、`gh pr close`。

## 技能说「发布到 issue tracker」时

新建一个 GitHub issue。

## 技能说「取出对应 ticket」时

按上面的「读 issue」读。

## 寻路操作

`/wayfinder` 使用。**地图**是一个 issue，**子 ticket** 是它的子 issue。

- **地图**：带 `wayfinder:map` 标签的单个 issue，正文放 Notes / 已定决策 / 迷雾。`gh issue create --label wayfinder:map`。
- **子 ticket**：挂到地图下的 GitHub 子 issue。不支持子 issue 时，在地图正文放任务清单，并在子 ticket 正文顶部写 `Part of #<map>`。标签：`wayfinder:<type>`（`research`/`prototype`/`grilling`/`task`）。认领后 assign 给执行者。
- **阻塞**：用 GitHub 原生依赖边，`gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`，`<blocker-db-id>` 是阻塞方的数据库 id（`gh api repos/<owner>/<repo>/issues/<n> --jq .id`），不是 `#number` 也不是 `node_id`。状态看 `issue_dependencies_summary.blocked_by`。不支持依赖时，在子 ticket 正文顶部写 `Blocked by: #<n>`；所有阻塞方关闭即解除。
- **前沿查询**：在地图打开的子 issue 里，剔除有未关闭阻塞方或有 assignee 的，按地图顺序取第一个。
- **认领**：`gh issue edit <n> --add-assignee @me`，本会话的第一次写。
- **结项**：`gh issue comment <n> --body "<答案>"`，再 `gh issue close <n>`，然后把上下文指针（结论 + 链接）追加到地图的「已定决策」。
