/**
 * 天气趋势分析页（Day 59）。
 *
 * 数据全部来自 TimescaleDB 连续聚合（`/weather/analysis/daily`）——
 * 这页的价值是让用户看见"系统在持续积累数据"，也是面试可深挖的一页。
 * 手写 SVG（与 HourlyChart 同一思路）：不引图表库，90 天数据也能流畅渲染。
 */

import { useEffect, useMemo, useState } from 'react'
import { Segmented, Space, Typography } from 'antd'
import { getStoredUser, isLoggedIn } from '../api/auth'
import http from '../api/http'
import EmptyState from '../components/EmptyState'

const { Paragraph, Text, Title } = Typography

interface DayRow {
  date: string
  temp_avg: number | null
  temp_max: number | null
  temp_min: number | null
  precip_sum: number | null
  humidity_avg: number | null
  samples: number
}

const RANGES = [
  { label: '30 天', value: 30 },
  { label: '90 天', value: 90 },
  { label: '180 天', value: 180 },
]

const W = 720
const H = 240
const PAD_X = 30
const PAD_T = 26
const BAR_BASE = 186
const LABEL_Y = 210

export default function Analysis() {
  const [days, setDays] = useState(90)
  const [rows, setRows] = useState<DayRow[] | null>(null)
  const [failed, setFailed] = useState(false)
  const loggedIn = isLoggedIn()

  useEffect(() => {
    if (!loggedIn) return
    let alive = true
    setRows(null)
    setFailed(false)
    http
      .get('/weather/analysis/daily', { params: { location: 'gz', days } })
      .then((res) => {
        // 拦截器已解包：res 就是 {items, total, ...} 本体
        if (alive) setRows((res as unknown as { items: DayRow[] })?.items ?? [])
      })
      .catch(() => {
        if (alive) setFailed(true)
      })
    return () => {
      alive = false
    }
  }, [days, loggedIn])

  const stats = useMemo(() => {
    const valid = (rows ?? []).filter((r) => r.temp_max != null)
    if (valid.length === 0) return null
    const rains = valid.filter((r) => (r.precip_sum ?? 0) > 1)
    const hottest = valid.reduce((a, b) => ((b.temp_max ?? 0) > (a.temp_max ?? 0) ? b : a))
    return {
      avgMax: valid.reduce((s, r) => s + (r.temp_max ?? 0), 0) / valid.length,
      rainDays: rains.length,
      hottest: hottest as DayRow,
    }
  }, [rows])

  const x = (i: number) => PAD_X + (i * (W - PAD_X * 2)) / Math.max((rows?.length ?? 1) - 1, 1)
  const allTemps = (rows ?? []).flatMap((r) => [r.temp_max, r.temp_min].filter((t): t is number => t != null))
  const tLo = allTemps.length ? Math.min(...allTemps) : 0
  const tHi = allTemps.length ? Math.max(...allTemps) : 1
  const span = Math.max(tHi - tLo, 1)
  const y = (t: number) => PAD_T + (1 - (t - tLo) / span) * (BAR_BASE - PAD_T - 30)
  const yBar = (p: number) => Math.min((p / Math.max(...(rows ?? []).map((r) => r.precip_sum ?? 0), 1)) * 40, 40)

  if (!loggedIn) {
    return (
      <div className="jp-card" style={{ padding: 24 }}>
        <Title level={4} className="jp-serif" style={{ margin: 0 }}>
          天气趋势
        </Title>
        <Paragraph style={{ margin: '8px 0 16px', color: 'var(--jp-ink-2)' }}>
          登录后可查看基于历史观测的趋势分析。
        </Paragraph>
      </div>
    )
  }

  const user = getStoredUser()

  return (
    <Space direction="vertical" size={20} style={{ width: '100%' }}>
      <div className="jp-card" style={{ padding: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10, flexWrap: 'wrap', gap: 8 }}>
          <span className="jp-serif" style={{ fontSize: 16, fontWeight: 600, color: 'var(--jp-ink)' }}>
            广州 · 历史趋势
          </span>
          <Segmented size="small" value={days} onChange={(v) => setDays(v as number)} options={RANGES} />
        </div>
        <Paragraph style={{ marginTop: 0, marginBottom: 10, fontSize: 12, color: 'var(--jp-ink-3)' }}>
          {user ? `${user.username}，` : ''}数据来自系统持续同步的观测记录（TimescaleDB 连续聚合），每次打开都是最新聚合。
        </Paragraph>

        {failed ? (
          <EmptyState type="error" text="趋势数据加载失败" hint="网络恢复后重试即可" onRetry={() => setDays(days)} />
        ) : !rows ? (
          <Text style={{ fontSize: 13, color: 'var(--jp-ink-3)' }}>正在聚合 {days} 天的观测数据…</Text>
        ) : rows.length < 2 ? (
          <Text style={{ fontSize: 13, color: 'var(--jp-ink-3)' }}>
            数据还在积累中（当前 {rows.length} 天），过几天再来看会更明显。
          </Text>
        ) : (
          <>
            {stats && (
              <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap', marginBottom: 8, fontSize: 12.5, color: 'var(--jp-ink-2)' }}>
                <span>平均最高 <b>{stats.avgMax.toFixed(1)}℃</b></span>
                <span>降水日 <b>{stats.rainDays}</b> 天</span>
                <span>
                  最热 <b>{stats.hottest.date}</b>（{stats.hottest.temp_max}℃）
                </span>
              </div>
            )}
            <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 'auto', display: 'block' }}>
              {/* 降水柱（画在底层，不抢温度曲线的主视觉） */}
              {rows.map((r, i) =>
                (r.precip_sum ?? 0) > 0.5 ? (
                  <rect
                    key={`b${i}`}
                    x={x(i) - 2}
                    y={BAR_BASE - yBar(r.precip_sum ?? 0)}
                    width={4}
                    height={yBar(r.precip_sum ?? 0)}
                    fill="#4a90d9"
                    opacity="0.3"
                  />
                ) : null,
              )}
              {/* 最高/最低温双曲线 */}
              {(['temp_max', 'temp_min'] as const).map((key, idx) => (
                <polyline
                  key={key}
                  points={rows
                    .map((r, i) => (r[key] == null ? null : `${x(i)},${y(r[key] as number)}`))
                    .filter(Boolean)
                    .join(' ')}
                  fill="none"
                  stroke={idx === 0 ? '#d46b6b' : '#4a7fc9'}
                  strokeWidth="2"
                  strokeLinejoin="round"
                />
              ))}
              {/* 月份刻度：每月 1 号标一次 */}
              {rows.map((r, i) =>
                r.date.endsWith('-01') ? (
                  <text key={`m${i}`} x={x(i)} y={LABEL_Y} textAnchor="middle" fontSize="10" fill="#8a97a8">
                    {r.date.slice(0, 7)}
                  </text>
                ) : null,
              )}
            </svg>
            <div style={{ fontSize: 12, color: 'var(--jp-ink-3)', marginTop: 4 }}>
              <span style={{ color: '#d46b6b' }}>━</span> 最高温　
              <span style={{ color: '#4a7fc9' }}>━</span> 最低温　
              <span style={{ color: '#4a90d9' }}>▎</span> 降水量（mm）
            </div>
          </>
        )}
      </div>
    </Space>
  )
}
