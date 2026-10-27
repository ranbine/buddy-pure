---
title: "渐进授权（Progressive Authorization）"
category: thinking
keywords:
  - methodology
  - risk-tier
  - shadow
  - enforce
  - autonomy
  - gate
---

# 渐进授权：给 agent 放权的方法论

> 从 action gate 的设计与迭代中提炼。核心思路：agent 能做什么由证据一步步放开，而这条边界 agent 自己改不了。
> 实现见 `tips/tools/action-gate.md`。
## 何时用

给 agent 或自动化脚本新增一类**有副作用**的能力时：写文件、删除、push、发邮件，k8s/helm 操作，工单 / 代码评审系统的写操作，cron 自动化，子 agent 预算。

## 循环

```
分级 → 观察(shadow) → 重放验证 → 人工确认 → 执行(enforce) → 审计 → 提议 → 回到分级
```

自动化只能**收紧**规则；放松必须经过：脚本提出提议 → reviewer 判断 → 人在真实终端 apply，而且只能新增规则。L3 永不自动降级。

## 8 条原则

| # | 原则 | 检查问题 | gate 中的实例 |
|---|---|---|---|
| 1 | 按可逆性和影响范围分级，不按工具分 | 做错了能撤销吗？影响谁？ | 同一个 `rm`：scratch 内是 L1，allow-list 内是 L3，其余路径是 DENY |
| 2 | 先观察再拦截 | 有误报数据了吗？ | shadow 期看 `cbp-gate stats`，再决定切不切 enforce |
| 3 | 读操作失败就放行，写操作失败就阻止 | 守卫自己坏了会怎样？ | hook 只挂在写工具上；enforce 下任何异常都按阻止处理 |
| 4 | 机制、策略、身份分三层 | 换个人用，要改几处？ | 代码 / `gate-policy.json` 模板 / `config/`（local.env + overlay） |
| 5 | 被管的一方不能改管它的规则 | agent 能不能改守卫、替自己审批？ | 策略、gate 代码、`config/` 受保护；approve/apply/mode 只能在 tty 执行；代码切换由用户在终端执行 |
| 6 | agent 能影响的输入一律不可信 | 环境变量、配置、搜索路径，谁能写？ | 忽略 env；用 `python3 -I`（`PYTHONPATH` 注入实测可让 gate 全部放行）；`~` 按 passwd 展开 |
| 7 | 每个绕过方式都要变成回归测试 | 这个漏洞以后还会再出现吗？ | 多轮 reviewer 找到的绕过 → 回归测试（`tests/`） |
| 8 | 改规则前先重放真实日志 | 新版比旧版松了吗？ | 硬性要求"变松 = 0"；迁移时重放约 400 条真实判定：0 条变松 |

## 落到新场景的步骤

1. 列出这类能力的所有动作，按原则 1 打上 L0–L3/DENY，写成策略数据，不要硬编码进脚本。
2. 先只记录（shadow），至少观察 1 周或 100 次判定。
3. 统计 L2 占比和 L3 命中，找出误报。
4. 调整规则时，用积累的日志新旧对比重放，确认变松 = 0。
5. 切到 enforce，人工审批只针对 L3，审批一次性生效并绑定参数。
6. 每周审计：提议 → reviewer → 人工 apply。

## 已知边界

- 字符串匹配是**防误操作的护栏**，不是沙箱，挡不住刻意构造的绕过（例如在脚本内部拼接命令）。
- 先在 shadow 模式积累数据；enforce 阶段的效果要用自己的日志验证。
- L2（未审核的灰区）在早期可能占三分之一左右，是最大的盲区，周回顾时应优先缩小。

## 候选应用（未实施）

| 场景 | L1 | L3 |
|---|---|---|
| 测试集群 kubectl/helm、测试配置 | 本地验证用的改动 | 要合入的改动、helm upgrade/uninstall |
| 工单 / 代码评审系统 | 读、草稿 | 评论、状态流转、+2 |
| 自动化 cron / 自动发邮件 | 发给自己 | 发给外部、群发 |

---
> **Local overlay** — if `contexts/local/tips/thinking/progressive-authorization.md` exists, read it too (install-specific notes and evidence).
