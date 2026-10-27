# UI Animation & Design Rules (Emil Kowalski + Apple Design)

> Source: emilkowalski/skills (GitHub)
> Applied: 2026-08-26
> Scope: Pure Lab HTML reports, dashboards, index page

## Easing Variables (已写入 cbp-base.css)

```css
--kb-ease-out: cubic-bezier(0.23, 1, 0.32, 1);      /* 进入/退出 */
--kb-ease-in-out: cubic-bezier(0.77, 0, 0.175, 1);  /* 屏幕内移动 */
--kb-ease-drawer: cubic-bezier(0.32, 0.72, 0, 1);   /* 抽屉/sheet */
```

## 核心规则（生成 HTML 时遵守）

### 必须
- 只动 `transform` + `opacity`（不动 width/height/margin）
- 入场用 `ease-out`（自定义 curve），永不用 `ease-in`
- UI 动画 ≤ 300ms
- 从 `scale(0.95) + opacity:0` 开始，永不 `scale(0)`
- 指定具体 transition 属性，永不 `transition: all`
- `prefers-reduced-motion` 处理：去掉位移/弹性，保留 opacity

### 推荐
- Card 入场加 stagger（60ms 间隔）
- Details 非对称时序：展开 350ms / 收起瞬时
- 按钮/pill 加 `:active { transform: scale(0.95) }` 反馈
- 大标题 `letter-spacing: -0.02em`
- `translateY` 用百分比（100%）不用硬编码 px
- 主题切换加 `filter: blur(3px)` bridge

### 不适用于 Pure Lab
- Spring 动画（无拖拽交互）
- Velocity handoff（无连续手势）
- Rubber-banding（无自定义滚动边界）
- Momentum projection（无 swipe/carousel）

## Duration 参考

| 元素 | 时长 |
|------|------|
| 按钮反馈 | 100-160ms |
| Tooltip / popover | 125-200ms |
| Dropdown / select | 150-250ms |
| Modal / drawer | 200-500ms |
| Card stagger 间隔 | 30-80ms |

## Apple Design 已应用

| 原则 | 实现 |
|------|------|
| Materials & Depth | Nav `backdrop-filter: blur(20px) saturate(180%)` |
| Typography | 标题 `letter-spacing: -0.02em` |
| Spatial Consistency | TOC pill 有方向感过渡 |
| Response | `:active` 即时反馈 |

## 自检表（生成报告前）

- [ ] 无 `transition: all`
- [ ] 无 `scale(0)` 起始
- [ ] 入场用 ease-out，无 ease-in
- [ ] UI 动画 ≤ 300ms
- [ ] 只动 transform + opacity
- [ ] details 展开有 animation
- [ ] 有 prefers-reduced-motion 处理
- [ ] 大标题有负 tracking

---
> **Local overlay** — if `contexts/local/tips/design/ui-animation-rules.md` exists, read it too (install-specific notes and evidence).
