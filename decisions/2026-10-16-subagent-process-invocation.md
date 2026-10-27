# 2026-10-16 — 以进程边界调用 subagent（曲线救国）

## Decision
当主上下文缺少原生「委托 subagent」调度能力时，用 `cbp-cli chat --agent <name> --no-interactive` 以独立进程启动同一份 agent 定义来实现等价委托，封装为通用脚本 `bin/run-agent.sh`。

## Alternatives Considered
- A: 直调底层脚本（如 review-artifact.py）— 快、确定，但跳过 agent 的 prompt 角色逻辑、工具沙箱、上下文隔离，拿不到脚本之外的判断。
- B: 进程方式起 agent（run-agent.sh）— 加载真实 agent 定义，带隔离/权限收敛/可组合；代价是延迟（数十秒）、依赖 token/网络、输出非确定需结构化解析。
- C: 直接改 report-generation 流程硬编码走 agent 进程 — 复用性差，且无通用保护（深度/超时/回退）。

## Reason
B 固化成通用 run-agent.sh 复用性最高（任意 subagent 可用），且方法论清晰：agent 定义=可执行单元，进程=调用边界，结构化 stdout=返回契约，agent allowedTools=安全沙箱。最佳形态是「agent 包脚本」——脚本保下限（机械检查），agent 补上限（角色判断，如 reviewer 主动提醒 EN 译文准确性脚本查不了）。

## 实现踩坑（已固化到 tips/tools/run-agent.md）
- `--agent` 必须传**名字**不是 JSON 路径（传路径报 `failed to set agent: Internal error`）。
- **不要**加 `--trust-all-tools`（非交互已注入信任，重复报 `cannot be used multiple times`）。
- 存在性校验用 `$CBP_CLI_HOME/agents/<name>.json`（渲染后的 agent 只装在 cbp-cli 目录）。
- 深度保护 `CBP_AGENT_DEPTH`（默认 max=1）防递归；超时 exit 124 → 调用方回退脚本。

## Revisit If
- cbp-cli 推出原生 in-process subagent 委托 API（届时优先用原生，run-agent.sh 降级为后备）。
- 进程启动延迟/token 失败率高到使链路不可用（则退回直调脚本 + 人工判断）。

## Outcome
- 复盘日期: 2026-12-15 (决策后 ~60 天)
- 实际结果: (空=待复盘)
- 当前结论: 维持

## v2 增强（2026-10-16 同日落地）
把 agent 从「对话工具」升级为「软件组件」，三条工程契约：
- **输入契约**：裸 args（兼容）或 stdin JSON（task/contract/session_id）。
- **输出契约**：agent 吐 `RESULT=<payload>`，脚本 `grep -o` 行内抠取（CLI 常把叙述与 RESULT 拼同行），stdout 只回纯载荷；无 RESULT→exit 3 回退末行。
- **流分离**：stdout=最终结果（给程序），stderr=叙述+[tool]日志+banner（给人）。CLI 本就把 [tool] 日志走 stderr，脚本再剥叙述到 stderr。
- **状态**：多轮用 CLI 原生 `--resume-id`（session_id 透传），不自建 Redis（YAGNI）。
四模式测试全绿（verdict/json/stdin/raw）。
