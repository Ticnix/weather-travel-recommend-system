import { useState } from 'react'
import { Alert, Button, Input, Skeleton, Space, Tag, Typography, message } from 'antd'
import { SaveOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import {
  generateTripPlan,
  saveItineraryBatch,
  type ItineraryCreatePayload,
  type TripPlanResult,
} from '../api/itinerary'
import { isLoggedIn } from '../api/auth'

const { Text, Paragraph } = Typography

/** 示例需求：降低"不知道该怎么说"的启动成本 */
const EXAMPLES = [
  '周末想去广州玩两天，喜欢美食和拍照',
  '带小孩去深圳玩三天，轻松一点',
  '去北京玩五天，喜欢历史和文化',
]

/**
 * AI 一键排行程（Day 40）。
 *
 * 两个刻意的设计：
 * 1. **只生成、不自动保存**——AI 排出来的是"提案"，直接写进用户的行程表
 *    等于替他做了决定，而改起来比删掉更烦，所以保存必须由用户点一次
 * 2. **因天气做过的调整要显式展示**（调色提示 + 逐条标记）——
 *    静默替换掉用户刚看到的内容，比不调整更让人困惑
 */
export default function TripPlanner() {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [result, setResult] = useState<TripPlanResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loggedIn = isLoggedIn()

  const generate = async () => {
    const text = query.trim()
    if (!text) {
      message.warning('先说说想去哪、玩几天')
      return
    }
    setLoading(true)
    setError(null)
    try {
      setResult(await generateTripPlan(text))
    } catch (e) {
      // 排程要调大模型，超时/限流都可能发生：把原因说清楚，别只显示"失败"
      setError(e instanceof Error ? e.message : '生成失败，请稍后重试')
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  const save = async () => {
    if (!result) return

    const items: ItineraryCreatePayload[] = []
    for (const day of result.plan.plan) {
      for (const entry of day.items) {
        if (!entry.title) continue
        items.push({
          title: entry.title,
          date: day.date,
          start_time: entry.time?.slice(0, 5) || undefined,
          location: entry.title,
          activity: entry.activity || undefined,
          note: entry.reason || undefined,
        })
      }
    }

    if (items.length === 0) {
      message.warning('这份行程还没有可保存的条目')
      return
    }

    setSaving(true)
    try {
      const stat = await saveItineraryBatch(items)
      if (stat.failed?.length) {
        message.warning(`已保存 ${stat.created} 条，${stat.failed.length} 条失败`)
      } else {
        message.success(`已保存 ${stat.created} 条到我的行程`)
      }
    } catch {
      message.error('保存失败，请稍后重试')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div className="jp-card" style={{ padding: 20 }}>
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <div>
            <span
              className="jp-serif"
              style={{ fontSize: 16, fontWeight: 600, color: 'var(--jp-ink)' }}
            >
              <ThunderboltOutlined style={{ color: 'var(--jp-amber)' }} /> AI 一键排行程
            </span>
            <Text style={{ fontSize: 12, color: 'var(--jp-ink-3)', marginLeft: 8 }}>
              说一句需求就行，下雨天会自动避开户外安排
            </Text>
          </div>

          <Input.TextArea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="例如：周末想去广州玩两天，喜欢美食和拍照"
            autoSize={{ minRows: 2, maxRows: 4 }}
            maxLength={200}
            showCount
          />

          <Space wrap size={6}>
            {EXAMPLES.map((example) => (
              <Tag
                key={example}
                data-testid="plan-example"
                style={{ cursor: 'pointer', whiteSpace: 'normal' }}
                onClick={() => setQuery(example)}
              >
                {example}
              </Tag>
            ))}
          </Space>

          <Space wrap>
            <Button
              type="primary"
              loading={loading}
              disabled={!loggedIn}
              onClick={() => void generate()}
            >
              生成行程
            </Button>
            {result && (
              <Button
                icon={<SaveOutlined />}
                loading={saving}
                disabled={!loggedIn}
                onClick={() => void save()}
              >
                一键保存到我的行程
              </Button>
            )}
            {!loggedIn && (
              <Text style={{ fontSize: 12, color: 'var(--jp-ink-3)' }}>
                登录后才能生成与保存
                <Button
                  type="link"
                  size="small"
                  onClick={() => navigate('/login', { state: { from: '/recommend?tab=plan' } })}
                >
                  去登录
                </Button>
              </Text>
            )}
          </Space>
        </Space>
      </div>

      {error && <Alert type="error" showIcon message="生成失败" description={error} />}

      {loading && !result && (
        <div className="jp-card" style={{ padding: 20 }}>
          <Skeleton active paragraph={{ rows: 4 }} />
        </div>
      )}

      {result && (
        <>
          {/* 概要：把"我理解成了什么"先讲清楚，用户才知道要不要重来 */}
          <div className="jp-card" style={{ padding: 20 }}>
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <Space wrap size={6}>
                <Tag color="blue">{result.plan.city}</Tag>
                <Tag>{result.plan.days} 天</Tag>
                {result.request.preferences.map((item) => (
                  <Tag key={item} color="gold">
                    {item}
                  </Tag>
                ))}
              </Space>
              {result.request.city_assumed && (
                <Text style={{ fontSize: 12, color: 'var(--jp-ink-3)' }}>
                  没听出你想去哪个城市，按「{result.plan.city}」规划的——想换城市就在需求里写清楚城市名。
                </Text>
              )}
              {result.plan.summary && (
                <Paragraph style={{ margin: 0, color: 'var(--jp-ink)', fontSize: 14 }}>
                  {result.plan.summary}
                </Paragraph>
              )}
            </Space>
          </div>

          {/* 因天气做的调整：必须显式展示，静默替换比不调整更让人困惑 */}
          {result.adjustments.length > 0 && (
            <Alert
              type="warning"
              showIcon
              message={`已按天气调整 ${result.adjustments.length} 处安排`}
              description={
                <ul style={{ margin: 0, paddingLeft: 18 }}>
                  {result.adjustments.map((item) => (
                    <li key={item}>
                      <Text style={{ fontSize: 12 }}>{item}</Text>
                    </li>
                  ))}
                </ul>
              }
            />
          )}

          {/* 逐日卡片 */}
          {result.plan.plan.map((day) => {
            const weather = result.weather[day.date]
            return (
              <div key={day.date} className="jp-card" style={{ padding: 20 }}>
                <Space style={{ width: '100%', justifyContent: 'space-between' }} wrap>
                  <Space size={8}>
                    <span className="jp-serif" style={{ fontSize: 15, fontWeight: 600 }}>
                      {day.date}
                    </span>
                    {weather?.desc && <Tag>{weather.desc}</Tag>}
                    {weather?.needs_indoor && <Tag color="orange">不适合户外</Tag>}
                  </Space>
                  {weather?.temp_max != null && (
                    <Text style={{ fontSize: 12, color: 'var(--jp-ink-3)' }}>
                      {weather.temp_min}~{weather.temp_max}°C
                      {weather.precip != null ? ` · 降水 ${weather.precip}mm` : ''}
                    </Text>
                  )}
                </Space>

                {day.weather_note && (
                  <Text
                    style={{ fontSize: 12, color: '#8a5a1f', display: 'block', marginTop: 6 }}
                  >
                    ⚠️ {day.weather_note}
                  </Text>
                )}

                <div style={{ marginTop: 10 }}>
                  {day.items.map((entry, index) => (
                    <div
                      key={`${day.date}-${index}`}
                      data-testid="plan-item"
                      style={{
                        display: 'flex',
                        gap: 10,
                        padding: '8px 0',
                        borderTop: index === 0 ? 'none' : '1px dashed var(--jp-border)',
                      }}
                    >
                      <Text
                        style={{ fontSize: 13, color: 'var(--jp-ink-3)', minWidth: 46 }}
                      >
                        {entry.time}
                      </Text>
                      <div style={{ flex: 1 }}>
                        <Space size={6} wrap>
                          <Text style={{ fontWeight: 600, fontSize: 14 }}>{entry.title}</Text>
                          {entry.activity && <Tag color="geekblue">{entry.activity}</Tag>}
                          {entry.weather_adjusted && <Tag color="orange">已因天气调整</Tag>}
                        </Space>
                        {entry.reason && (
                          <Paragraph
                            style={{ margin: '2px 0 0', fontSize: 12, color: 'var(--jp-ink-2)' }}
                          >
                            {entry.reason}
                          </Paragraph>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </>
      )}
    </Space>
  )
}
