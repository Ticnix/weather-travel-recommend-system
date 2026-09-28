/**
 * 48 小时天气曲线 v2（可拖动 + 悬浮详情卡）。
 *
 * **为什么 48 小时 + 拖动**：24 点挤在一屏里，曲线的起伏基本看不见；
 * 拉长到 48 点后信息密度才对，代价是超出一屏——用横向拖动解决，
 * 桌面按住拖、手机直接滑（原生滚动）。
 *
 * **为什么悬浮卡而不是常驻表格**：48 行数据铺出来等于没有重点；
 * 悬浮/点按某小时才出详情（温度/降水概率/降雨量/风速/天气），
 * 移开即收起，手机上点按同样触发。
 *
 * AQI 徽标来自 `/weather/aqi`（失败不影响曲线）。
 */

import { useEffect, useRef, useState } from 'react'
import { Typography } from 'antd'
import http from '../api/http'

const { Text } = Typography

interface HourItem {
  date: string
  time: string
  temperature: number | null
  precip_prob: number | null
  precip: number | null
  weather_desc: string | null
  wind_speed: number | null
}

interface AqiData {
  pm25: number | null
  us_aqi: number | null
  level: string
  color: string
}

const AQL_COLOR: Record<string, string> = {
  green: '#52c41a',
  blue: '#1677ff',
  orange: '#fa8c16',
  volcano: '#fa541c',
  red: '#f5222d',
  magenta: '#eb2f96',
  default: '#8a97a8',
}

const STEP = 30 // 每小时占的横向像素
const W = 60 + 48 * STEP // 画布总宽（48 点 + 两侧留白）
const H = 210
const PAD_L = 40
const PAD_T = 44
const BAR_TOP = 160 // 降水柱基线
const LABEL_Y = 184

export default function HourlyChart({ city }: { city?: string }) {
  const [items, setItems] = useState<HourItem[] | null>(null)
  const [aqi, setAqi] = useState<AqiData | null>(null)
  const [failed, setFailed] = useState(false)
  const [hover, setHover] = useState<number | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const drag = useRef<{ x: number; left: number } | null>(null)

  useEffect(() => {
    let alive = true
    http
      .get('/weather/hourly', { params: { city: city || '广州', hours: 48 } })
      // 拦截器已解包：res 就是 {city, items} 本体
      .then((res) => {
        if (alive) setItems((res as unknown as { items: HourItem[] })?.items ?? [])
      })
      .catch(() => {
        if (alive) setFailed(true)
      })
    // AQI 失败不影响曲线：徽标位不显示即可
    http
      .get('/weather/aqi', { params: { city: city || '广州' } })
      .then((res) => {
        if (alive) setAqi((res as unknown as AqiData) ?? null)
      })
      .catch(() => {
        if (alive) setAqi(null)
      })
    return () => {
      alive = false
    }
  }, [city])

  const temps = (items ?? []).map((it) => it.temperature).filter((t): t is number => t != null)
  const tMin = Math.min(...temps)
  const tMax = Math.max(...temps)
  const span = Math.max(tMax - tMin, 1)
  const x = (i: number) => PAD_L + i * STEP
  const y = (t: number) => PAD_T + (1 - (t - tMin) / span) * (BAR_TOP - PAD_T - 16)

  /** 鼠标/触摸移动时定位到最近的小时（拖动中不触发，避免跟着手抖） */
  const locate = (clientX: number) => {
    const el = scrollRef.current
    if (!el || !items?.length) return
    const rect = el.getBoundingClientRect()
    const px = clientX - rect.left + el.scrollLeft
    const i = Math.round((px - PAD_L) / STEP)
    setHover(Math.max(0, Math.min(items.length - 1, i)))
  }

  const onPointerDown = (e: React.PointerEvent) => {
    if (e.pointerType !== 'mouse') return // 触屏走原生滚动，别抢事件
    drag.current = { x: e.clientX, left: scrollRef.current?.scrollLeft ?? 0 }
    ;(e.target as Element).setPointerCapture?.(e.pointerId)
  }
  const onPointerMove = (e: React.PointerEvent | React.MouseEvent) => {
    if (drag.current && scrollRef.current) {
      scrollRef.current.scrollLeft = drag.current.left - (e.clientX - drag.current.x)
    } else {
      locate(e.clientX)
    }
  }
  const endDrag = () => {
    drag.current = null
  }

  if (failed) {
    return (
      <div className="jp-card" style={{ padding: 20 }}>
        <Text style={{ fontSize: 13, color: 'var(--jp-ink-3)' }}>
          逐小时预报暂时取不到，稍后重试即可；不影响其它功能。
        </Text>
      </div>
    )
  }

  const hoverItem = hover != null ? items?.[hover] : undefined

  return (
    <div className="jp-card" style={{ padding: 20 }}>
      <div style={{ marginBottom: 6, display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 6 }}>
        <span className="jp-serif" style={{ fontSize: 16, fontWeight: 600, color: 'var(--jp-ink)' }}>
          48 小时天气
        </span>
        <span style={{ fontSize: 12, color: 'var(--jp-ink-3)', display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          {aqi && aqi.pm25 != null ? (
            <span
              style={{
                padding: '2px 8px',
                borderRadius: 10,
                fontSize: 11,
                color: '#fff',
                background: AQL_COLOR[aqi.color] ?? '#8a97a8',
              }}
            >
              AQI {aqi.us_aqi ?? '—'} · {aqi.level}（PM2.5 {Math.round(aqi.pm25)}）
            </span>
          ) : null}
          {city || '广州'} · 按住可左右拖动
        </span>
      </div>

      {!items ? (
        <Text style={{ fontSize: 13, color: 'var(--jp-ink-3)' }}>正在加载逐小时预报…</Text>
      ) : items.length < 2 ? (
        <Text style={{ fontSize: 13, color: 'var(--jp-ink-3)' }}>
          逐小时数据暂缺（数据源未返回），不影响当日天气与行程提醒。
        </Text>
      ) : (
        <div
          ref={scrollRef}
          style={{
            overflowX: 'auto',
            cursor: 'grab',
            touchAction: 'pan-x',
            // 拖动时的"抓取中"光标
            userSelect: 'none',
          }}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerLeave={() => {
            endDrag()
            setHover(null)
          }}
        >
          <div style={{ position: 'relative', width: W }}>
            <svg
              viewBox={`0 0 ${W} ${H}`}
              width={W}
              height={H}
              style={{ display: 'block' }}
              onMouseMove={onPointerMove}
              onClick={() => {/* 触屏点按由 onMouseMove 覆盖，这里无需处理 */}}
            >
              <defs>
                <linearGradient id="hourly-fill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#5b8dd6" stopOpacity="0.25" />
                  <stop offset="100%" stopColor="#5b8dd6" stopOpacity="0.02" />
                </linearGradient>
              </defs>

              {/* 降水概率柱：>=10% 才画 */}
              {items.map((it, i) =>
                (it.precip_prob ?? 0) >= 10 ? (
                  <rect
                    key={`p${i}`}
                    x={x(i) - 8}
                    y={BAR_TOP - ((it.precip_prob ?? 0) / 100) * 30}
                    width={16}
                    height={((it.precip_prob ?? 0) / 100) * 30}
                    fill="#4a90d9"
                    opacity="0.35"
                    rx="2"
                  />
                ) : null,
              )}

              {/* 温度曲线 + 渐变面积 */}
              <polygon
                points={
                  items
                    .map((it, i) => (it.temperature == null ? null : `${x(i)},${y(it.temperature)}`))
                    .filter(Boolean)
                    .join(' ') + ` ${x(items.length - 1)},${BAR_TOP} ${x(0)},${BAR_TOP}`
                }
                fill="url(#hourly-fill)"
              />
              <polyline
                points={items
                  .map((it, i) => (it.temperature == null ? null : `${x(i)},${y(it.temperature)}`))
                  .filter(Boolean)
                  .join(' ')}
                fill="none"
                stroke="#3b5b8c"
                strokeWidth="2.5"
                strokeLinejoin="round"
              />

              {/* 当前悬停点：高亮竖线 + 圆点 */}
              {hover != null && items[hover]?.temperature != null && (
                <g>
                  <line x1={x(hover)} y1={PAD_T - 6} x2={x(hover)} y2={BAR_TOP} stroke="#3b5b8c" strokeWidth="1" strokeDasharray="3 3" opacity="0.5" />
                  <circle cx={x(hover)} cy={y(items[hover].temperature as number)} r="4.5" fill="#3b5b8c" stroke="#fff" strokeWidth="1.5" />
                </g>
              )}

              {/* 温度数字 + 日期/时间：每 3 小时标一次 */}
              {items.map((it, i) =>
                it.temperature == null || i % 3 !== 0 ? null : (
                  <g key={`t${i}`}>
                    <text x={x(i)} y={y(it.temperature) - 10} textAnchor="middle" fontSize="11" fill="#2c3e50">
                      {Math.round(it.temperature)}°
                    </text>
                    <text x={x(i)} y={LABEL_Y} textAnchor="middle" fontSize="10" fill="#8a97a8">
                      {i === 0 || it.time === '00:00' ? it.date.slice(3) : it.time}
                    </text>
                  </g>
                ),
              )}
            </svg>

            {/* 悬浮详情小卡片：跟随时段点定位，超出右边界则往左翻 */}
            {hoverItem && (
              <div
                style={{
                  position: 'absolute',
                  top: 2,
                  left: Math.min(Math.max(x(hover!) - 70, 4), W - 150),
                  width: 146,
                  padding: '8px 10px',
                  borderRadius: 8,
                  background: 'rgba(255,255,255,0.96)',
                  boxShadow: '0 4px 14px rgba(36,59,85,0.18)',
                  border: '1px solid #e5eaf2',
                  pointerEvents: 'none',
                  zIndex: 2,
                }}
              >
                <div style={{ fontSize: 12, fontWeight: 700, color: '#2c3e50' }}>
                  {hoverItem.date.slice(3)} {hoverItem.time}
                </div>
                <div style={{ fontSize: 11.5, color: '#5b6b7d', marginTop: 2 }}>
                  {hoverItem.weather_desc ?? '—'}
                </div>
                <div style={{ fontSize: 12, color: '#2c3e50', marginTop: 4, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2px 6px' }}>
                  <span>🌡️ {hoverItem.temperature != null ? `${Math.round(hoverItem.temperature)}℃` : '—'}</span>
                  <span>☔ {hoverItem.precip_prob ?? 0}%</span>
                  <span>🌧️ {hoverItem.precip != null ? `${hoverItem.precip.toFixed(1)}mm` : '0mm'}</span>
                  <span>💨 {hoverItem.wind_speed != null ? `${Math.round(hoverItem.wind_speed)}km/h` : '—'}</span>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
      <div style={{ fontSize: 11.5, color: 'var(--jp-ink-3)', marginTop: 4 }}>
        悬停或点按某小时查看详情（温度 / 降水概率 / 降雨量 / 风速）
      </div>
    </div>
  )
}
