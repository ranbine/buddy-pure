---
alwaysApply: false
description: "Workflow Patterns (行为模式暂存区)"
---

# Workflow Patterns (行为模式暂存区)

> **定位**：pattern 的**暂存区 / staging area**。新观察到的行为模式先落这里，
> 达标后升级到正式层（`discipline.md`），或下沉到 `tips/`（如果是具体命令而非纪律）。
> `discipline.md` = 正式纪律层；这里 = 未定型的原始 pattern。

## 采集规则

- **When**: 同类错误出现 2× OR 用户纠正我
- **Action**: 先在此文件登记，格式 `Trigger → Behavior → Confidence → Learned From (+ Violation count)`
- 不等第 3 次 —— 2 次即提炼

## 升级 / 下沉规则（memory-dream Phase 2 自动扫描）

| 条件 | 动作 | 去向 |
|------|------|------|
| confidence >= 1.0 **且** violation >= 3 | 🔴 强制升级 | → `discipline.md` 对应 Tier（D-A/O/P） |
| confidence >= 0.95 **且** Learned From > 30 天 | 🟡 建议升级 | → `discipline.md`（用户确认） |
| pattern 本质是具体命令/接口（非纪律） | ⬇️ 下沉 | → `tips/<category>/*.md` |
| confidence < 0.8 **且** 最后 Learned From > 60 天 | 🟡 建议归档 | 标记低活跃 |

升级动作：从本文件删除该条 → 写入目标文件 → 在下方 Ledger 记一行。

## 当前暂存（Active Staging）

| Pattern | Trigger → Behavior | Confidence | Learned From (Violation×) |
|---------|-------------------|:---:|---|
| P-CRED-READ-FIRST | 处理某服务凭据/API（token 失效、401、换 endpoint）前，**或声称"没有工具访问 X"前** → 先 grep 该服务的 `tips/tools|infra/*.md`，别凭记忆试/下结论 | 0.95 | 2026-09-24 401 修复：把 A 服务的 token 当 B 服务试，对应 tips 早写明 PAT 不通用 (×1)；2026-10-20 声称"无法访问内网 wiki"，用户提示已有现成方式，对应 tips 早有记录 (×2) |
| P-NO-INNER-MARKER | 生成回复时 → 内部思考/盘算标记（如 `count`、草稿前缀）不得出现在用户可见回复里；推演留思考区，回复只含结论+行动。**发送前自查：回复里有无 `count`/裸盘算行** | 1.0 | 2026-09-29 用户两次指出：回复里多条以 `count` 开头（内部盘算外露），且记录该 pattern 的同一回复里再犯 (×2) |
| P-SYNC-WHATSNEW | 部署 HTML 到 docs/（sync）→ 更新分区卡片**和** What's New 是**两件独立的事**；加完分区卡片必跑 `bin/update-whats-new.py` 并自查 URL 在 whats-new 块内。两者别混为一步 | 0.9 | 2026-10-16 用户发现 Pages 的 What's New 没更新：我加了 Daily/Tech 分区卡片但漏了 What's New，连 sync 自检步 d 都没执行 (×1)。已加 reviewer 兜底(index-sync 查 whats-new) + 自检步 d 红线化 |
| P-GATE-VIA-AGENT | 生成报告/HTML 后把关 → **必须走 `run-agent.sh reviewer`（真起 agent 进程）**，不得用直调 `review-artifact.py` 脚本替代。脚本是下限（机械检查），agent 是上限（判断：内容稀疏/重复、译文、过度宣称）。只有 agent 失败才回退脚本且明确告知用户 | 0.9 | 2026-10-16 生成 9 月月报全程只调脚本没走 reviewer agent，脚本 structure 盲点放行了「内容双份+JS裸露」的坏版本，靠用户肉眼发现 (×1)。已改 report-generation step 4 把关权归 agent + 补脚本 structure 检查 |
| P-DELEGATE-SCOPE | 委派子 agent（run-agent.sh）前 → prompt 里写明交付物 + 禁止项（**验证只跑 review-artifact.py、不做浏览器渲染/截图；简报里的事实不重新探索**）；timeout 按任务量（改文件 300s / 新页面 600s），超时=任务没切好→拆小或主 context 直接改；等待前一句话告知用户。小改动直接在主 context 改，不委派 | 0.9 | 委派页面任务：首轮无视简报重新探索仓库→超时 (×1)；改完后自发浏览器验证→超时，用户以为卡死 (×2)。已改 html-generator prompt + report-generation「Delegation budget」 |

## 升级台账（Promotion Ledger）

历史 P001–P007 + P-* 系列共 19 条已全部毕业：

| 原 Pattern | 去向 | 备注 |
|-----------|------|------|
| P001 内网链接用 API | D-P3 | 内网链接 → API/脚本 |
| P002 Issue-tracker Bearer token | tips/tools/<tracker>-api.md | 具体命令，下沉 |
| P003 纠正后直接执行 | D-O3 | |
| P004 搜索 2 次换策略 | D-A4 | |
| P005 log 先跑工具 | D-A1 | + log 分析 subagent |
| P006 0 结果 ≠ 不存在 | D-A5 | |
| P007 长 session 复述变量 | D-A6 | |
| P-EXEC 执行力自检 | D-P7 | |
| P-QUESTION 松问题追问 | D-A7 | |
| P-CHATROOM 多角度决策 | D-P8 | |
| P-DEAI 中文去 AI 味 | D-O4 | |
| P-WRITE-FIRST 先写后说 | D-O2 | |
| P-TOOLPATH 读源码路径常量 | D-A3 | |
| P-DIRECT-PATH 有路径直读 | D-A2 | |
| P-ATOMIC-FLOW 多步原子执行 | D-P1 | |
| P-CONFIRM-BEFORE-PUSH docs 预览 | D-P2 | |
| P-SSH-JUMP 跳板跳转 | D-P4 | |
| P-HEREDOC-TCL 方括号禁用 | D-P5 | |

> 台账用途：防止已毕业 pattern 被重复登记。新 pattern 若与台账某条同源，直接更新目标文件的 Learned From，不在暂存区重开。
