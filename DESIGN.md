# Outlook Fusion — Design System

## 调色板

| Token | Value | 用途 |
|-------|-------|------|
| `--c-primary` | `#2563eb` | 主色（按钮、链接、活跃态） |
| `--c-primary-dark` | `#1d4ed8` | 主色悬停 |
| `--c-primary-light` | `#dbeafe` | 主色背景 |
| `--c-success` | `#10b981` | 成功/active |
| `--c-error` | `#ef4444` | 错误/expired |
| `--c-warning` | `#f59e0b` | 警告/needs_reauth |
| `--c-bg` | `#f0f4f8` | 页面背景 |
| `--c-card` | `#ffffff` | 卡片/面板背景 |
| `--c-text` | `#1e293b` | 正文 |
| `--c-text-muted` | `#64748b` | 辅助文字 |
| `--c-border` | `#e2e8f0` | 边框/分割线 |
| `--c-hover` | `#f8fafc` | 行/卡片悬停 |

## 字体

- 字体栈：`-apple-system, "Segoe UI", "Microsoft YaHei", system-ui, sans-serif`
- 等宽：`"JetBrains Mono", "Cascadia Code", Consolas, monospace`
- 字号：12 / 13 / 14 / 15 / 18 / 22 / 26 px

## 间距

4px 网格：4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48

## 圆角

- 小：`6px`（按钮、输入框）
- 中：`10px`（卡片）
- 大：`12px`（弹窗）

## 阴影

- 卡片：`0 1px 3px rgba(0,0,0,.08)`
- 弹窗：`0 20px 60px rgba(0,0,0,.2)`
- 悬停：`0 4px 12px rgba(0,0,0,.1)`

## 动效

| Token | Value | 用途 |
|-------|-------|------|
| `--dur-fast` | `150ms` | hover/active |
| `--dur-normal` | `250ms` | 切换/出现 |
| `--dur-slow` | `400ms` | 入场动画 |
| `--ease-out` | `cubic-bezier(0.16, 1, 0.3, 1)` | 弹出 |
| `--ease-in-out` | `cubic-bezier(0.4, 0, 0.2, 1)` | 标准过渡 |

## 骨架屏

灰色脉冲动画：`@keyframes shimmer { 0% { background-position: -200% 0 } 100% { background-position: 200% 0 } }`