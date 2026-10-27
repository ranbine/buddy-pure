# 2026-09-29 · 统一质检员 reviewer agent（设计定案，未转正）

## 决策
新增第 4 个子 agent「reviewer」作为**统一质量门禁**，审核其他 agent 的产出，
让 agent 产出足够可靠、把人从 go/no-go 决策中最大化解放出来。

实现载体：`bin/review-artifact.py`（多 profile 单脚本），reviewer agent 调用它。

## 关键设计
- **多 profile 单 agent**（非每类产出一个 agent）：`--type html|log`，扩展 = 加 profile。
- **审核标准从现有 rule 客观导出**，不主观拍：
  - html profile ← sync.md 的 mandatory/no-exceptions 流程
  - log profile ← log-analyzer-prompt.md 的 Output Format + 自检清单
- **可靠性分三层**：L1 机械可验证（脚本）/ L2 可查证事实（查数据源，如 issue key 去 tracker 核实）/
  L3 语义判断（LLM）。
- **核心策略：L3 → L1**。把"结论可不可信"这类语义问题，转化为可机械验证的
  **证据结构规则**。例：log 结论「自信 Root Cause 必须附带可定位证据
  （时间戳/文件/行号/数值），否则须标『未确定』，二者必居其一，否则打回」。
- **决策模型**（user-set）：硬门禁任一 FAIL = 自动 BLOCK；软维度加权，综合 ≥ 90 才 PUBLISH-OK。
  - html 硬门禁：structure / links / compliance / bilingual
  - **bilingual（EN 模式露中文）= 硬门禁**（含 SVG `<text>` 内 CJK，因 SVG 不受 lang toggle 控制）
  - size 分档：<50KB=100 / 50–55KB=70 / ≥55KB=0
  - log 硬门禁：fields / classification（合法标签）/ evidence（证据规则）

## 备选（未采用）
- 每类产出一个专职 reviewer（复用性差，否决）
- FAIL 软提醒（否决，用硬门禁 + ≥90 才放行，更能减少人参与）

## 可靠性边界（诚实记录）
L1/L2 可高可信自动放行；**L3 语义由 LLM 审 LLM，有天花板**——故尽量把 L3 转成
可验证的证据规则，拿不准的极少数升级为 NEEDS-HUMAN，而非假装 LLM 能兜底。

## 实证有效
- html profile 抓到 monthly-review-2026-08 EN 模式的 `<pre><code>` 中文泄漏（人工没发现）。
- log profile 抓到「无证据的自信断言」+ 非法 Classification。

## 现状 / 待办（转正 revisit）
- ✅ 脚本 `bin/review-artifact.py`（html + log profile）可用、已验证
- ✅ 草案 `agents/reviewer.json.draft` + `reviewer-prompt.md.draft`
- ⏭️ 转正：`.draft` → 正式 agent；写 tips + 注册 script-output-index；
  接入 report-generation.md（生成后自动 review，PUBLISH-OK 才发布）；更新 README；提交
- ⏭️ 可选：扩 text profile（邮件/日报）

## Revisit 条件
下次要生成报告 / 分析 log 时，考虑先接入 reviewer 作为发布前门禁；或用户主动要求转正。
