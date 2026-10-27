---
alwaysApply: true
description: "Pure Discipline Patterns（纪律框架）"
---

# Pure Discipline Patterns（纪律框架）

> **定位**：跨场景的行为纪律层。workflow.md 管"做什么"，这里管"怎么做才不翻车"。
> 每条规则挂来源（workflow.md 条款 / workflow-patterns.md P-编号）和具体翻车实例。
> 新规则必须有 Learned From；没有实例的规则 = 空话，不收录。

三层结构：
- **Tier 1 — 分析纪律**：做分析/诊断时的认知约束（防止"查错方向"）
- **Tier 2 — 输出纪律**：生成内容/交付物时的质量约束（防止"交错东西"）
- **Tier 3 — 流程纪律**：多步工作流的执行约束（防止"做到一半丢了"）

---

## Tier 1 — Analysis Discipline（分析纪律）

做分析时的思维约束。核心问题：**在开始分析之前，我该先做什么？**

### D-A1: 工具优先，手动垫底

分析 log 先跑已有的解析/分析脚本，不要手动 grep 拼凑。有专用 log 分析 subagent 时 → delegate（完整 playbook 在其 prompt）。

- **来源**: P005
- **翻车**: 手动 grep 漏了关联的 issue，工具一跑全出来了
- **检查**: 收到 job ID → 第一反应是不是调工具？

### D-A2: 有路径就直读，禁止验证性搜索

用户给了文件路径 → `cat` / `ls`，不 find、不 grep 确认、不问"是不是这个"。

- **来源**: P-DIRECT-PATH, workflow.md File Search Strategy Step -1
- **翻车**: 3+ 次违反（数据文件、配置 profile、工具输出），每次都是多余 find 浪费 5+ 轮
- **严重度**: Red Line 级

### D-A3: 找工具输出 → 读源码路径常量

需要定位脚本输出文件 → `grep "OUT\|DIR\|PATH" bin/<script>.py | head`，一步到位。

- **来源**: P-TOOLPATH
- **翻车**: 2026-08-05 找脚本输出 xlsx 盲猜 5 个目录，正确路径在脚本头 3 行

### D-A4: 搜索失败 2 次 → 换策略，不加第 3 次

连续两次 grep/find 无结果 → 停。换 fastcontext / 换关键词 / 问用户。

- **来源**: P004, workflow.md File Search Strategy
- **翻车**: 多次 grep 变体越搜越偏，最终用户给了正确路径

### D-A5: 0 结果 ≠ 不存在

grep 返回空不能下"没有这个 error"的结论。先检查 keyword 拼写、大小写、正则。

- **来源**: P006
- **翻车**: Hive NULL 等价问题 — 查询无结果 ≠ 数据不存在，可能是查询本身有问题

### D-A6: 长 session 上下文漂移 → 显式复述

超过 10 轮后做对比/判断前，重新声明 build、cluster、TC name、时间范围。

- **来源**: P007
- **翻车**: 2026-07-23 日期漂移 — 前半段分析 build A，后半段无感切到 build B

### D-A7: 松问题先收束再分析

模糊请求（"帮我看看""为什么挂了"）→ 5 维快检：对象、目标、冲突、约束、反馈。缺 2+ 维追问，缺 0-1 维直接做。

- **来源**: P-QUESTION
- **翻车**: 不追问直接分析 → 方向跑偏 → 用户说"我不是问这个"
- **翻车 2026-10-20**: "SBI counter 检查都做了吗" 连续两次答偏（先答脚本是否中断、再答脚本是否含该步），用户纠正"我说的是分析"/"不是脚本，是 case result"。对象维度没收束：job 结果 vs 工具 vs 脚本

### D-A8: 进入分析场景 → 先读绑定 md

analysis-checklist.md trigger table 中有匹配 → 读对应 tips 文件再开始。

- **来源**: workflow.md Analysis Execution Rules
- **翻车**: 不读对应领域 skill 文件直接分析 → 漏了关键判断步骤

### D-A9: 搜索优先级：已知 > grep > fastcontext > fallback

1. 单个已知文件 → read（零成本）
2. 精确 pattern → 单次 grep
3. 多文件/不确定 → fastcontext
4. fastcontext 失败 → 静默 fallback 到 grep

- **来源**: workflow.md File Search Strategy
- **绝对禁止**: 在大型共享/网络挂载目录上跑 find；dump 500+ 行 git log

---

## Tier 2 — Output Discipline（输出纪律）

生成交付物时的质量约束。核心问题：**交出去之前，我该检查什么？**

### D-O1: 写前去重（Prewrite Dedup）

创建新 tip 前必须搜现有覆盖：grep → 有则 UPDATE → 部分重叠则 MERGE → 真正新增才 ADD + 注册。

- **来源**: workflow.md Prewrite Dedup
- **判断输出**: `ADD` / `UPDATE` / `MERGE` / `NOOP`
- **翻车**: 同一个工具写了两个 tips 文件，一个过时一个新，互相矛盾

### D-O2: 发现即写入，先写后说

发现新认证方式/访问方法 → 立刻写 tips + 注册 trigger → 然后才回复用户。

- **来源**: P-WRITE-FIRST
- **翻车**: 2026-08-04 某 wiki API 认证，说"记住了"但没写文件，下次又忘

### D-O3: 纠正后直接执行，不解释旧错

用户纠正 → 执行正确操作。不花 token 解释"之前为什么没想到"。

- **来源**: P003
- **翻车**: 多次。解释旧错 = 浪费用户时间 + 显得在找借口

### D-O4: 中文内容去 AI 味

面向人阅读的中文文本 → 自动避免 `tips/thinking/de-ai-writing.md` 中的 AI 味 pattern。

- **来源**: P-DEAI
- **检查项**: 无"首先/其次/最后"堆叠、无"值得注意的是"、无过度 emoji

### D-O5: Tips 必须接口卡片格式

新建/改造 tips → 用途一句话 + 触发场景 + 表格核心 + 调用模板 + 限制/坑。禁止叙述性段落。

- **来源**: analysis-checklist.md Tips 格式标准
- **翻车**: 早期 tips 写成散文，找关键信息要读 3 遍

### D-O6: 删除操作 — 确认 + 路径限制

所有删除必须告知确切内容并等用户确认（例外：自己 scratch 目录**内部**，见 workflow.md Red Lines）。只允许删 `CBP_DELETE_ALLOW` 白名单路径下的文件。装了 action gate 时由 `gate-policy.json` 在代码里强制。

- **来源**: workflow.md Red Lines
- **严重度**: Red Line，无例外

### D-O7: 承诺必须落文件

用户要求行为变更 → 写入规则文件并 commit。不说"下次我会..."，未写入 = 未承诺。

- **来源**: workflow.md Red Lines "No verbal promises"
- **翻车**: 口头答应改行为 → 下个 session 完全忘记

### D-O8: 改动 rules/tips/workflow 后 → 跑结构校验

编辑了 `.codebuddy/rules/`、`contexts/tips/`、`workflow.md` 或 `analysis-checklist.md`
后，收尾前 delegate 给 `health-checker`（Function 2 校验 / `cbp-validate.py`）
或直接跑，确认没改坏：引用未断、D-*/P-* 编号连续无重复、决策格式合规、tips 非空。

- **来源**: health-checker Function 2（事件驱动校验）
- **时机**: 改动后 / session-end（D-P12 #5 一并做）
- **对比**: 运营体检（doctor）是时间驱动（周一），结构校验是事件驱动（改动后）

---

## Tier 3 — Process Discipline（流程纪律）

多步工作流的执行约束。核心问题：**流程开始后，怎么不丢步骤？**

### D-P1: 多步流程原子执行

daily-flow / sync / session-end 等有步骤序列的流程 → 必须连续完成。中间被打断 → "我先完成 X 的最后一步"。

- **来源**: P-ATOMIC-FLOW
- **翻车**: 2026-08-21 daily report 做到一半被 repo 阅读打断 → index card 更新丢失

### D-P2: docs 部署必须预览确认

改 `docs/` → 起 http server → 告知 URL → 等用户确认 → 再 commit + push。

- **来源**: P-CONFIRM-BEFORE-PUSH, rules/sync.md
- **翻车**: 2026-08-24 直接 push 未预览，用户指出

### D-P3: 内部链接 → 用 API/脚本，不说"无法访问"

CI / code review / issue tracker 链接 → 先查对应 API / MCP / 脚本的 tips 文件。

- **来源**: P001, P002
- **翻车**: 2026-07-22 CI job 链接说"我无法访问"，忘了已有脚本支持 job ID

### D-P4: 受限网段 SSH 必须走跳板

目标节点不可直连 → `ssh -J <jump-host> <target>`，跳板名从环境 tips 查，不猜。

- **来源**: P-SSH-JUMP
- **翻车**: 2026-08-20 直连业务节点失败 → 跳板跳转成功

### D-P5: Expect/heredoc 中禁用方括号

kubectl jsonpath 等带 `[]` 的命令 → 不要放进 expect heredoc（Tcl 解释器会吃掉）。改用 sshpass 或临时脚本。

- **来源**: P-HEREDOC-TCL
- **翻车**: 2026-08-20 `{.spec.rules[0].host}` 被 Tcl 解释

### D-P6: Git — 单任务单 commit，推前自检

每完成一个任务 commit 一次。push 前自检 diff。最多 2 push/hour。用户没说 push 就问一次。

- **来源**: rules/git-workflow.md
- **翻车**: 多任务堆一个 commit → 回滚时连带无关改动

### D-P7: 执行力自检 — 诊断不做激励

用户设了目标但迟迟没动 → 直接问"是不知道怎么做，还是在回避？"不做打鸡血。

- **来源**: P-EXEC
- **诊断信号**: 模拟器/思考替代/方向跳跃/知识上瘾/完美主义/外归因

### D-P8: 多角度决策辅助

纠结型决策 → 提议"开个聊天室"：3 位视角互补的专家各 200 字 → 总结盲区 + 可执行建议。

- **来源**: P-CHATROOM

### D-P9: 并行 ≠ 乱序

独立操作 → 并行 tool call。有依赖 → 严格串行，不猜 placeholder。

- **来源**: preferences.md Parallelism Rule
- **翻车**: call B 用了 A 的猜测值 → 结果全错

### D-P10: "先等等 push" — 用户的 review 窗口

用户没显式说 push → 问一次。"先等等 push" = 暂停推送，等 go-ahead。

- **来源**: preferences.md Work Rhythm
- **翻车**: 自动 push 了用户还想改的内容

### D-P11: pre-push hook 报错 → 修完再推，禁止 --no-verify

hook 检查失败 → 按报错内容修复（README stale → 更新 README，sensitive files → 移除）。修完再 push。不用 `--no-verify` 绕过，除非用户显式说"跳过"。

- **来源**: rules/git-workflow.md pre-push hook
- **翻车**: 2026-08-28 hook 报 README stale，直接 `--no-verify` 绕过两次，用户指出

### D-P12: Session-End 自检清单

会话结束 / 用户示意收尾时，自检（缺 #1 或 #4 = 丢上下文）：

1. 完成了明确任务 → 写 `history/YYYY-MM/YYYY-MM-DD.md`
2. 新建脚本/工具 → 确认已执行验证可用（见 preferences "create+run+verify"）
3. 用了新工具/API/技巧 → 查 `tips/` 是否需新增/更新（见 D-O2）
4. 未决决策 / pending 项 → 写 `memory.md`
5. 改了 rules/preferences/workflow → 确认与现有规则一致
6. 用户纠正过我 → 是否揭示可复用 pattern → 写 `workflow-patterns.md`（见 D-O3）
7. 同类错误出现 2+ 次 → 立即提炼 pattern，不等 session end

**Correction Capture**：用户纠正（"你不是可以…"/"用 API"/"之前分析过了"）→ 立即执行正确操作（D-O3）→ 收尾时判断新 pattern 还是违反旧规则 → 新则 append workflow-patterns.md，旧则 +confidence + 新 Learned From 日期。

- **来源**: rules/session-end.md（已并入本条）, P-ATOMIC-FLOW
- **非可选**：缺 #1/#4 = 未来 session 上下文丢失

---

## 使用方式

1. **进入分析场景** → 扫 Tier 1，检查 D-A1~A9 有没有适用的
2. **准备输出/写文件** → 扫 Tier 2，检查 D-O1~O7
3. **执行多步流程 / 会话收尾** → 扫 Tier 3，检查 D-P1~P12（收尾看 D-P12 清单）
4. **翻车了** → 找到对应条目，+1 violation count，补 Learned From

## 新增规则标准

- 必须有 **Learned From**（具体日期 + 翻车描述）
- 必须归入 Tier 1/2/3 之一
- 如果跨 tier，放在主要影响的 tier，在其他 tier 加交叉引用
- 编号规则：D-A{n} / D-O{n} / D-P{n}，顺序追加
