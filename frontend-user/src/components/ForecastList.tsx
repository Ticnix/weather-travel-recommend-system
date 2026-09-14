import { Button, Segmented, Skeleton, Space, Typography } from 'antd'
import { useEffect, useMemo, useRef, useState } from 'react'
import { getForecast, getHistory, type ForecastDay } from '../api/weather'
import { getWeatherVisual, formatWeekday } from '../utils/weather'

const { Text } = Typography

// 时间轴窗口：以「今天」为基准向前/向后取多少天
type RangeKey = 'future' | 'recent' | 'past'
const RANGE_CONFIG: Record<RangeKey, { back: number; forward: number }> = {
  // 默认：今天 + 未来一周（用户最关心「明天要不要带伞」）
  future: { back: 0, forward: 6 },
  // 近期：过去 7 天 + 今天 + 未来 6 天
  recent: { back: 7, forward: 6 },
  // 长期：过去 23 天 + 今天 + 未来 6 天（共 30 天）
  past: { back: 23, forward: 6 },
}

// 取日期字符串（YYYY-MM-DD），兼容 time / date 字段
function getDateStr(day: ForecastDay): string {
  const raw = (day.time ?? day.date ?? '') as string
  if (!raw) return ''
  return raw.slice(0, 10)
}

// 今天（本地）的日期串
function todayStr(): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

// 天气预报横向卡片（日式简洁 + 左右滑动）
// 默认展示「今天 + 未来一周」；切换到含历史区间时自动定位到「今天」
export default function ForecastList() {
  const [range, setRange] = useState<RangeKey>('future')
  const [history, setHistory] = useState<ForecastDay[]>([])
  const [forecast, setForecast] = useState<ForecastDay[]>([])
  const [loading, setLoading] = useState(true)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      // 取足够多的历史（最多 31 天）供前端按窗口截取
      getHistory(31).then((r) => setHistory(r.items ?? [])),
      getForecast().then((r) => setForecast(r.items ?? [])),
    ])
      .catch(() => {
        setHistory([])
        setForecast([])
      })
      .finally(() => setLoading(false))
  }, [])

  // 合并：生成连续日期轴（过去 → 今天 → 未来），用历史实测 + 未来预报填充
  const merged = useMemo(() => {
    const t = todayStr()
    const { back, forward } = RANGE_CONFIG[range]
    const total = back + 1 + forward
    const start = new Date(t)
    start.setDate(start.getDate() - back)

    const days: ForecastDay[] = []
    for (let k = 0; k < total; k++) {
      const d = new Date(start)
      d.setDate(start.getDate() + k)
      const p = (n: number) => String(n).padStart(2, '0')
      const ds = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
      const isFuture = ds > t
      const match = [...history, ...forecast].find((x) => getDateStr(x) === ds)
      if (match) {
        days.push({ ...match, is_forecast: isFuture })
      } else {
        days.push({
          date: ds,
          temp_max: null,
          temp_min: null,
          weather_desc: null,
          weather_code: null,
          precipitation: null,
          is_forecast: isFuture,
        })
      }
    }
    return days
  }, [history, forecast, range])

  // 自动把「今天」滚到可见位置：
  // - future 模式下今天本来就在最左，不用动
  // - 含历史区间时左侧会有一堆过去日期，需要主动定位
  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const todayCard = el.querySelector<HTMLElement>('[data-today="true"]')
    if (!todayCard) return
    el.scrollTo({ left: Math.max(0, todayCard.offsetLeft - 8), behavior: 'smooth' })
  }, [merged])

  if (loading) {
    return (
      <div className="jp-card" style={{ padding: 24 }}>
        <div className="jp-serif" style={{ fontSize: 16, fontWeight: 600, marginBottom: 16, color: 'var(--jp-ink)' }}>
          天气时间轴
        </div>
        <Skeleton active />
      </div>
    )
  }

  return (
    <div className="jp-card" style={{ padding: '20px 16px' }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 14,
          paddingLeft: 8,
        }}
      >
        <div className="jp-serif" style={{ fontSize: 16, fontWeight: 600, color: 'var(--jp-ink)' }}>
          天气时间轴
        </div>
        <Space size={4}>
          {/* 长区间滑动后快速定位回「今天」 */}
          <Button
            size="small"
            type="text"
            onClick={() => {
              const el = scrollRef.current
              const card = el?.querySelector<HTMLElement>('[data-today="true"]')
              if (el && card) {
                el.scrollTo({ left: Math.max(0, card.offsetLeft - 8), behavior: 'smooth' })
              }
            }}
          >
            回到今天
          </Button>
          <Segmented
            size="small"
            value={range}
            onChange={(v) => setRange(v as RangeKey)}
            options={[
              { label: '未来 7 天', value: 'future' },
              { label: '近 14 天', value: 'recent' },
              { label: '近 30 天', value: 'past' },
            ]}
          />
        </Space>
      </div>

      {/* 横向滑动容器（显示滚动条） */}
      <div
        ref={scrollRef}
        style={{
          display: 'flex',
          gap: 10,
          overflowX: 'auto',
          overflowY: 'hidden',
          paddingBottom: 10,
          scrollSnapType: 'x proximity',
          WebkitOverflowScrolling: 'touch',
          // 可见细滚动条
          scrollbarWidth: 'thin',
          scrollbarColor: 'var(--jp-border-strong) transparent',
        }}
      >
        {merged.length === 0 && (
          <Text style={{ color: 'var(--jp-ink-3)', padding: '20px 8px' }}>
            暂无天气数据
          </Text>
        )}
        {merged.map((day, i) => {
          const hasData = day.weather_desc != null
          const visual = getWeatherVisual(day.weather_desc)
          const dateStr = getDateStr(day)
          const isToday = dateStr === todayStr()
          // 区间底色：过去=暖灰微底 / 今天=靛蓝高亮 / 未来=天蓝微底
          const bg = isToday
            ? 'var(--jp-bg-2)'
            : day.is_forecast
              ? 'rgba(122,166,194,0.08)'
              : 'rgba(90,125,90,0.06)'
          const tag = isToday ? '今天' : day.is_forecast ? '预报' : '实况'
          const tagColor = isToday
            ? 'var(--jp-indigo)'
            : day.is_forecast
              ? 'var(--jp-sky)'
              : 'var(--jp-moss)'
          return (
            <div
              key={dateStr + (day.is_forecast ? '-f' : '-p') + i}
              data-today={isToday ? 'true' : undefined}
              style={{
                flex: '0 0 auto',
                width: 92,
                scrollSnapAlign: 'start',
                textAlign: 'center',
                padding: '14px 6px',
                borderRadius: 12,
                background: bg,
                border: isToday
                  ? '1px solid var(--jp-indigo)'
                  : '1px solid var(--jp-border)',
                opacity: hasData ? 1 : 0.5,
              }}
            >
              <Text
                style={{
                  color: isToday ? 'var(--jp-indigo)' : 'var(--jp-ink-3)',
                  fontSize: 12,
                  fontWeight: isToday ? 600 : 400,
                }}
              >
                {isToday ? '今天' : formatWeekday(dateStr)}
              </Text>
              <div style={{ fontSize: 11, color: 'var(--jp-ink-3)', margin: '2px 0' }}>
                {dateStr.slice(5)}
              </div>
              <div style={{ fontSize: 30, margin: '6px 0' }}>
                {hasData ? visual.icon : '—'}
              </div>
              <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--jp-ink)' }}>
                {day.temp_max ?? '--'}°
                <Text style={{ color: 'var(--jp-ink-3)', fontSize: 12 }}>
                  {' '}
                  / {day.temp_min ?? '--'}°
                </Text>
              </div>
              <div style={{ fontSize: 12, color: 'var(--jp-ink-2)' }}>
                {hasData ? visual.label : '暂无'}
              </div>
              <div
                style={{
                  fontSize: 10,
                  marginTop: 4,
                  color: tagColor,
                  fontWeight: 500,
                }}
              >
                {hasData ? tag : '—'}
              </div>
            </div>
          )
        })}
      </div>

      {/* 区间图例 */}
      <div
        style={{
          display: 'flex',
          gap: 16,
          marginTop: 10,
          paddingLeft: 8,
          fontSize: 12,
          color: 'var(--jp-ink-2)',
        }}
      >
        <span>
          <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 3, background: 'rgba(90,125,90,0.5)', marginRight: 6 }} />
          过去 · 实况
        </span>
        <span>
          <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 3, background: 'var(--jp-indigo)', marginRight: 6 }} />
          今天
        </span>
        <span>
          <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 3, background: 'rgba(122,166,194,0.6)', marginRight: 6 }} />
          未来 · 预报
        </span>
      </div>
    </div>
  )
}
