---
title: "交互式学习模式"
category: thinking
verified_at: 2026-08-21
keywords:
  - methodology
  - writing
  - learning
  - interactive
---

# 交互式学习模式

> 用途：把一个学习课题拆成自适应连续文章，根据反馈动态调整
> 触发：启动新学习计划时（如 C++ / 新技术栈 / 新领域）
> 来源：dbs-learning skill (rnskill)

## 结构

```
learning/<课题名>/
├── 00-学习计划.md    ← 总览、目标、预估时间
├── 01.md             ← 第一篇（末尾有反馈区）
├── 02.md             ← 根据 01 反馈动态生成
├── ...
└── assets/
```

## 流程

1. 确认课题 → 生成 `00-学习计划.md`（目标、边界、预估篇数）
2. 写第一篇 → 末尾留反馈区模板
3. 用户填反馈（哪里懂了/卡了/想深入什么）
4. 读取反馈 → 调整下一篇的难度、角度、展开方式
5. 循环

## 每篇末尾反馈区模板

```markdown
---
## 学习反馈（写完后告诉 Pure）
- 看懂了：
- 没看懂/卡住的：
- 想继续深入的方向：
- 节奏感受（太快/刚好/太慢）：
```

## 规则

- 没有反馈不写下一篇 — 先问
- 不跳号：01 → 02 → 03
- 自适应：每篇根据上一篇反馈动态调整，不是预设固定内容
- 完成判断：能做出交付物（项目/代码/文档）= 课题完成

---
> **Local overlay** — if `contexts/local/tips/thinking/interactive-learning.md` exists, read it too (install-specific notes and evidence).
