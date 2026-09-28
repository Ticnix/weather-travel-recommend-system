/**
 * 行程分享工具（Day 57 + 58）。
 *
 * **为什么海报用 canvas 纯排版而不用 AI 出图**：AI 生图按张计费（工作日志第十二节
 * 已移除），而且行程/时间/地点是"印章式精确印刷"的内容——纯排版反而更准，
 * 生成模型会把数字和汉字画错。零 API 成本，断网也能生成。
 *
 * **分享为什么区分桌面/手机**：桌面 Chrome 的 `navigator.share` 虽然存在，
 * 但 Windows 没有注册"图片文件"的分享目标时，弹出的系统面板是空的
 * （实测显示"我们无法为你显示所有共享方法"）。所以桌面一律走**预览弹窗 + 下载**，
 * 只有触屏设备（pointer: coarse）才走系统分享面板。
 */

import type { ItineraryItem } from '../api/itinerary'

/** 分享计数存这里：只是想知道"有没有人在用"，不值得进后端 */
const SHARE_COUNT_KEY = 'wt_share_count'

export function trackShare(): void {
  try {
    const n = Number(localStorage.getItem(SHARE_COUNT_KEY) ?? '0')
    localStorage.setItem(SHARE_COUNT_KEY, String(n + 1))
  } catch {
    /* 隐私模式下 localStorage 不可用：计数失败不影响分享本身 */
  }
}

/* ------------------------------------------------------------------ */
/* 文本截断：按**像素宽度**省略（Day 57 要求），不能按字符数——
   中英文宽度差一倍，按字符截断要么溢出要么浪费空间 */
/* ------------------------------------------------------------------ */

function fitText(ctx: CanvasRenderingContext2D, text: string, maxWidth: number): string {
  if (ctx.measureText(text).width <= maxWidth) return text
  let t = text
  while (t.length > 1 && ctx.measureText(`${t}…`).width > maxWidth) {
    t = t.slice(0, -1)
  }
  return `${t}…`
}

function weekdayLabel(date: string): string {
  const d = new Date(`${date}T00:00:00`)
  if (Number.isNaN(d.getTime())) return ''
  return '周' + '日一二三四五六'[d.getDay()]
}

/* ------------------------------------------------------------------ */
/* 海报绘制                                                            */
/* ------------------------------------------------------------------ */

const W = 720
const PAD = 48

/**
 * 绘制行程海报。返回 canvas，由调用方决定导出（下载 / 分享）。
 *
 * 占位规则（Day 57 检查项）：没开始时间显示「全天」，
 * 没地点不画地点行——**绝不出现 "undefined" 或空白行**。
 */
export function buildPoster(items: ItineraryItem[]): HTMLCanvasElement {
  const days = groupByDate(items)
  const scale = Math.min(window.devicePixelRatio || 1, 2) // 移动端 2x，桌面不浪费
  // 高度按内容算：标题区 150 + 每天组头 56 + 每条 64，保底 900
  const contentH = 150 + days.reduce((h, d) => h + 56 + d.items.length * 64 + 14, 0) + 90
  const H = Math.max(contentH, 900)

  const canvas = document.createElement('canvas')
  canvas.width = W * scale
  canvas.height = H * scale
  const ctx = canvas.getContext('2d')
  if (!ctx) return canvas
  ctx.scale(scale, scale)

  // 背景：浅色渐变（海报是要分享出去的，白底最不挑场景）
  const bg = ctx.createLinearGradient(0, 0, 0, H)
  bg.addColorStop(0, '#f4f7fb')
  bg.addColorStop(1, '#e8eef6')
  ctx.fillStyle = bg
  ctx.fillRect(0, 0, W, H)

  // 标题
  ctx.fillStyle = '#243b55'
  ctx.font = '700 44px system-ui, "PingFang SC", "Microsoft YaHei", sans-serif'
  ctx.fillText('我的行程', PAD, 88)
  ctx.font = '400 22px system-ui, "PingFang SC", "Microsoft YaHei", sans-serif'
  ctx.fillStyle = '#8a97a8'
  const span =
    days.length > 1 ? `${days[0].date} ~ ${days[days.length - 1].date}` : (days[0]?.date ?? '')
  ctx.fillText(span ? `${span} · 共 ${items.length} 段` : `共 ${items.length} 段`, PAD, 122)

  let y = 190
  for (const day of days) {
    // 日期组头
    ctx.fillStyle = '#243b55'
    ctx.font = '600 26px system-ui, "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.fillText(`${day.date.slice(5).replace('-', '/')} ${weekdayLabel(day.date)}`, PAD, y)
    y += 40

    for (const it of day.items) {
      ctx.font = '400 24px system-ui, "PingFang SC", "Microsoft YaHei", sans-serif'
      ctx.fillStyle = '#5b6b7d'
      const time = it.start_time ? it.start_time : '全天'
      ctx.fillText(time, PAD, y)

      // 主标题：长文本按像素截断（Day 57 检查项：长地点名不溢出）
      ctx.fillStyle = '#2c3e50'
      ctx.font = '600 24px system-ui, "PingFang SC", "Microsoft YaHei", sans-serif'
      const titleX = PAD + 84
      const locX = W - PAD
      const titleMax = (it.location ? locX - 200 : locX) - titleX
      ctx.fillText(fitText(ctx, it.title, titleMax), titleX, y)

      // 地点右对齐
      if (it.location) {
        ctx.font = '400 20px system-ui, "PingFang SC", "Microsoft YaHei", sans-serif'
        ctx.fillStyle = '#8a97a8'
        const loc = fitText(ctx, it.location, 180)
        ctx.fillText(loc, locX - ctx.measureText(loc).width, y)
      }
      y += 40

      if (it.activity) {
        ctx.font = '400 20px system-ui, "PingFang SC", "Microsoft YaHei", sans-serif'
        ctx.fillStyle = '#8a97a8'
        ctx.fillText(fitText(ctx, it.activity, W - PAD * 2 - 84), PAD + 84, y)
        y += 24
      }
      y += 24 // 条间距
    }
    y += 14 // 组间距
  }

  // 底部品牌落款
  ctx.fillStyle = '#8a97a8'
  ctx.font = '400 18px system-ui, "PingFang SC", "Microsoft YaHei", sans-serif'
  ctx.fillText('由广州天气旅行助手生成', PAD, H - 40)

  return canvas
}

/** 按日期分组（保持后端返回顺序：已按日期与开始时间排序） */
function groupByDate(items: ItineraryItem[]): { date: string; items: ItineraryItem[] }[] {
  const map = new Map<string, ItineraryItem[]>()
  for (const it of items) {
    const list = map.get(it.date) ?? []
    list.push(it)
    map.set(it.date, list)
  }
  return [...map.entries()].map(([date, list]) => ({ date, items: list }))
}

/* ------------------------------------------------------------------ */
/* 分享（Day 58）                                                      */
/* ------------------------------------------------------------------ */

/** 复制用的纯文本文案，也是 Web Share 的 text 兜底 */
export function itineraryText(items: ItineraryItem[]): string {
  return groupByDate(items)
    .map((day) =>
      [
        `${day.date.slice(5).replace('-', '/')} ${weekdayLabel(day.date)}`,
        ...day.items.map(
          (it) => `  ${it.start_time ?? '全天'} ${it.title}${it.location ? ` · ${it.location}` : ''}`,
        ),
      ].join('\n'),
    )
    .join('\n')
}

export type ShareOutcome = 'shared' | 'cancelled'

/**
 * 是否具备原生分享：**触屏设备** + Web Share 支持文件。
 * 桌面 Chrome 的 navigator.share 也存在，但没有文件分享目标时面板是空的
 * （实测截图），所以必须用 pointer: coarse 判定，而不是只看 API 存在。
 */
export function canNativeShare(): boolean {
  return (
    typeof navigator !== 'undefined' &&
    typeof navigator.share === 'function' &&
    window.matchMedia?.('(pointer: coarse)').matches === true
  )
}

/** 生成海报 dataURL：预览 <img> 与下载共用一份 */
export function posterDataUrl(items: ItineraryItem[]): string {
  if (items.length === 0) throw new Error('当前筛选下没有行程，先加一条或换个范围')
  return buildPoster(items).toDataURL('image/png')
}

/** 下载海报 PNG */
export function downloadPoster(dataUrl: string): void {
  const a = document.createElement('a')
  a.href = dataUrl
  a.download = '我的行程.png'
  a.click()
}

/**
 * 原生分享海报（**仅 canNativeShare() 为 true 时调用**）。
 * 用户取消（AbortError）不算失败，静默返回；其它失败引导用下载。
 */
export async function sharePoster(items: ItineraryItem[]): Promise<ShareOutcome> {
  const dataUrl = posterDataUrl(items)
  const blob = await (await fetch(dataUrl)).blob()
  const file = new File([blob], '我的行程.png', { type: 'image/png' })
  const nav = navigator as Navigator & { canShare?: (data: ShareData) => boolean }
  if (!nav.share || !nav.canShare?.({ files: [file] })) {
    throw new Error('当前设备不支持系统分享，请用「下载图片」')
  }
  trackShare()
  try {
    await nav.share({ files: [file], title: '我的行程', text: itineraryText(items) })
    return 'shared'
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') return 'cancelled'
    throw new Error('分享面板唤起失败，请改用「下载图片」')
  }
}

/** 一键复制文案；剪贴板 API 不可用（http 环境 / 老浏览器）时退回 execCommand */
export async function copyItineraryText(items: ItineraryItem[]): Promise<void> {
  const text = itineraryText(items)
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }
  const ta = document.createElement('textarea')
  ta.value = text
  ta.style.position = 'fixed'
  ta.style.opacity = '0'
  document.body.appendChild(ta)
  ta.select()
  try {
    if (!document.execCommand('copy')) throw new Error('复制失败')
  } finally {
    document.body.removeChild(ta)
  }
}
