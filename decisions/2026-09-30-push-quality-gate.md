# 2026-09-30 — Push quality gate: script measures, reviewer decides

## Decision
新增 push 质量门禁：`review-artifact.py --type push` 做**机械量具**（文件数、
README/index staleness、rate limit、HTML 模板/创作分类），reviewer agent 拿读数
做**决策**（PUSH / PUSH-NOW / BATCH / DEFER-TIME / NEEDS-HUMAN / BLOCK）；
DEFER 用两个语义不同的独立队列管理（时间窗口 vs 质量）。

## Alternatives Considered
- A: 纯脚本自动 push（评分达标直接推）— 快，但「是不是新机制/是不是安全修复/
  创作类满不满意」需要判断，脚本给不了；且绕过用户的 push 复核窗口习惯。
- B: 纯 agent 判所有（含机械检查）— agent 判 bilingual 泄漏/文件数不稳定、费 token、
  不可复现。
- C（选中）: 分层——脚本出客观读数，reviewer 出决策。复用现有「reviewer 是统一质检员 +
  review-artifact.py 多 profile」模式，push 是第 4 个 profile。
- 队列：单队列混装 vs 双队列。选双队列——时间窗口型「等时钟」可自动重试，质量型
  「等修完」永不自动推，混装会导致「时间到了但质量没过也推」的错误放行。

## Reason
- 机械可判定的走脚本（快、零 token、可复现），需要判断的上抛 agent —— 符合
  「脚本量具 + agent 质检员」分层，也和 log/html profile 一致。
- 模板类（在册 style-registry）第一版 PUBLISH-OK 即可发（例行报告不该反复确认）；
  创作类（slides/一次性可视化）永远 NEEDS-HUMAN（人满意 + 底线检查双条件）——
  机器判不了「好不好看」。判定来源 = 是否在 style-registry publish_dir 下（客观）。
- 双队列区分「下个周期」两义：时间窗口→下个窗口自动推；质量→修完重审才推。

## Revisit If
- 攒批阈值（≥3 文件 / 有新机制）在实际使用中频繁误判（该推的被攒 / 该攒的被推）。
- 路径法分类误判率高（reports/reviews/ 下模板与创作混放，如 architecture-evolution
  被判 template）——若语义层覆盖不住，改用文件名模式白名单。
- time 队列自动重试出现「质量在入队后失效仍被推」的情况（需入队即冻结快照）。

## Outcome
- 复盘日期: 2026-11-29 (决策后 60 天)
- 实际结果: (空=待复盘)
- 当前结论: 维持
