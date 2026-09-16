import { useCallback, useEffect, useState } from 'react'
import { Button, Col, Empty, Row, Skeleton, Space, Tag, Typography } from 'antd'
import {
  CalendarOutlined,
  ClockCircleOutlined,
  CommentOutlined,
  CompassOutlined,
  EnvironmentOutlined,
  MessageOutlined,
  RightOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import WeatherHero from '../components/WeatherHero'
import ForecastList from '../components/ForecastList'
import { getDashboard, type HomeDashboard } from '../api/home'
import { isLoggedIn } from '../api/auth'

const { Paragraph, Text } = Typography

// 提醒级别 → 点缀色
const LEVEL_COLOR: Record<string, string> = {
  info: '#3b5b8c',
  warning: '#d99a4e',
  danger: '#d9543f',
}

// 快捷功能入口（保持跳转，用于做详细操作）
const QUICK_ACTIONS = [
  { key: 'chat', icon: <MessageOutlined />, title: 'AI 智能问答', desc: '天气 / 穿搭 / 出行一站式咨询', color: '#3b5b8c' },
  { key: 'outfit', icon: <ThunderboltOutlined />, title: '穿搭推荐', desc: '按天气场景推荐穿搭', color: '#d9543f' },
  { key: 'travel', icon: <CompassOutlined />, title: '出行规划', desc: '多维度评分推荐最优路线', color: '#5a7d5a' },
  { key: 'itinerary', icon: <CalendarOutlined />, title: '行程管理', desc: '行程安排与笔记编辑', color: '#d99a4e' },
  { key: 'feedback', icon: <CommentOutlined />, title: '意见反馈', desc: '问题反馈与建议提交', color: '#e3a7ad' },
]

export default function Home() {
  const navigate = useNavigate()
  const [dash, setDash] = useState<HomeDashboard | null>(null)
  const [loading, setLoading] = useState(true)
  const loggedIn = isLoggedIn()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setDash(await getDashboard())
    } catch {
      setDash(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const tips = dash?.tips ?? []
  const outfit = dash?.outfit ?? null
  const upcoming = dash?.itinerary?.upcoming ?? []
  const indices = dash?.indices ?? []
  // 默认只展示最相关的 4 个指数，避免 16 项铺满首页
  const [showAllIndices, setShowAllIndices] = useState(false)

  return (
    <Space direction="vertical" size={20} style={{ width: '100%' }}>
      {/* 天气主卡片 */}
      <WeatherHero />

      {/* ===== 今日提醒（结合天气自动生成，无需跳转） ===== */}
      <div className="jp-card" style={{ padding: 20 }}>
        <div style={{ marginBottom: 12 }}>
          <span className="jp-serif" style={{ fontSize: 16, fontWeight: 600, color: 'var(--jp-ink)' }}>
            <ThunderboltOutlined style={{ color: 'var(--jp-amber)' }} /> 今日提醒
          </span>
        </div>
        {loading ? (
          <Skeleton active paragraph={{ rows: 2 }} />
        ) : tips.length === 0 ? (
          <Text style={{ color: 'var(--jp-ink-2)', fontSize: 13 }}>暂无特别提醒</Text>
        ) : (
          <Space direction="vertical" size={10} style={{ width: '100%' }}>
            {tips.map((t, i) => (
              <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                <span style={{ fontSize: 20, lineHeight: 1.2 }}>{t.icon}</span>
                <div>
                  <Text style={{ fontWeight: 600, color: LEVEL_COLOR[t.level] ?? 'var(--jp-ink)' }}>
                    {t.title}
                  </Text>
                  <div style={{ color: 'var(--jp-ink-2)', fontSize: 13, marginTop: 2 }}>{t.text}</div>
                </div>
              </div>
            ))}
          </Space>
        )}
      </div>

      {/* ===== 今日穿搭建议（直接展示，不用跳转） ===== */}
      <div className="jp-card" style={{ padding: 20 }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 12,
          }}
        >
          <span className="jp-serif" style={{ fontSize: 16, fontWeight: 600, color: 'var(--jp-ink)' }}>
            👔 今日穿搭
          </span>
          <Button type="link" size="small" onClick={() => navigate('/recommend?tab=outfit')}>
            更多搭配 <RightOutlined />
          </Button>
        </div>
        {loading ? (
          <Skeleton active paragraph={{ rows: 2 }} />
        ) : outfit ? (
          <>
            <Paragraph style={{ margin: 0, color: 'var(--jp-ink)', lineHeight: 1.9, fontSize: 14 }}>
              {outfit.suggestion}
            </Paragraph>
            {outfit.rules?.length ? (
              <Space wrap size={[6, 6]} style={{ marginTop: 10 }}>
                {outfit.rules.map((r, i) => (
                  <Tag key={i} style={{ whiteSpace: 'normal', padding: '4px 8px', fontSize: 12 }}>
                    {r.split('：')[0]}
                  </Tag>
                ))}
              </Space>
            ) : null}
          </>
        ) : (
          <Text style={{ color: 'var(--jp-ink-2)', fontSize: 13 }}>暂无穿搭建议</Text>
        )}
      </div>

      {/* ===== 生活指数（后端已按体质偏好与近期行程排序） ===== */}
      {indices.length > 0 ? (
        <div className="jp-card" style={{ padding: 20 }}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: 12,
            }}
          >
            <span
              className="jp-serif"
              style={{ fontSize: 16, fontWeight: 600, color: 'var(--jp-ink)' }}
            >
              🌿 生活指数
            </span>
            <Button type="link" size="small" onClick={() => setShowAllIndices((v) => !v)}>
              {showAllIndices ? '收起' : `全部 ${indices.length} 项`} <RightOutlined />
            </Button>
          </div>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
              gap: 12,
            }}
          >
            {(showAllIndices ? indices : indices.slice(0, 4)).map((item) => (
              <div
                key={item.type_code}
                style={{
                  background: '#faf7f2',
                  border: '1px solid #f0e9df',
                  borderRadius: 10,
                  padding: '12px 14px',
                }}
              >
                <div style={{ fontSize: 12, color: 'var(--jp-ink-3)' }}>{item.name}</div>
                <div
                  className="jp-serif"
                  style={{
                    fontSize: 18,
                    fontWeight: 600,
                    color: 'var(--jp-ink)',
                    margin: '2px 0 6px',
                  }}
                >
                  {item.category}
                </div>
                <div
                  style={{
                    fontSize: 12,
                    color: 'var(--jp-ink-2)',
                    lineHeight: 1.6,
                    display: '-webkit-box',
                    WebkitLineClamp: showAllIndices ? 6 : 3,
                    WebkitBoxOrient: 'vertical',
                    overflow: 'hidden',
                  }}
                >
                  {item.text}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {/* ===== 近期行程（含逐条天气提醒） ===== */}
      <div className="jp-card" style={{ padding: 20 }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 12,
          }}
        >
          <span className="jp-serif" style={{ fontSize: 16, fontWeight: 600, color: 'var(--jp-ink)' }}>
            <CalendarOutlined /> 近期行程
          </span>
          <Button type="link" size="small" onClick={() => navigate('/itinerary')}>
            全部行程 <RightOutlined />
          </Button>
        </div>

        {loading ? (
          <Skeleton active paragraph={{ rows: 2 }} />
        ) : !loggedIn ? (
          <div style={{ textAlign: 'center', padding: '16px 0' }}>
            <Text style={{ color: 'var(--jp-ink-2)', fontSize: 13 }}>
              登录后可查看行程安排与天气提醒
            </Text>
            <div style={{ marginTop: 10 }}>
              <Button size="small" type="primary" onClick={() => navigate('/login', { state: { from: '/' } })}>
                去登录
              </Button>
            </div>
          </div>
        ) : upcoming.length === 0 ? (
          <Empty description="未来 7 天还没有安排" style={{ padding: 12 }}>
            <Button size="small" type="primary" onClick={() => navigate('/itinerary')}>
              去添加行程
            </Button>
          </Empty>
        ) : (
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            {upcoming.map((it) => (
              <div
                key={it.id}
                style={{
                  paddingLeft: 12,
                  borderLeft: '3px solid var(--jp-indigo)',
                }}
              >
                <Space size={8} wrap>
                  <Tag color="blue" icon={<CalendarOutlined />} style={{ margin: 0 }}>
                    {it.date}
                  </Tag>
                  {it.start_time && (
                    <Tag icon={<ClockCircleOutlined />} style={{ margin: 0 }}>
                      {it.start_time}
                    </Tag>
                  )}
                  <Text style={{ fontWeight: 600, color: 'var(--jp-ink)' }}>{it.title}</Text>
                  {it.location && (
                    <Text style={{ color: 'var(--jp-ink-3)', fontSize: 12 }}>
                      <EnvironmentOutlined /> {it.location}
                    </Text>
                  )}
                </Space>
                <div style={{ marginTop: 4, fontSize: 12.5, color: 'var(--jp-ink-2)' }}>
                  🌦️ {it.weather_hint}
                  {it.city && it.city !== dash?.city ? `（${it.city}）` : ''}
                </div>
              </div>
            ))}
          </Space>
        )}
      </div>

      {/* 7 天预报 */}
      <ForecastList />

      {/* 快捷功能入口 */}
      <Row gutter={[16, 16]}>
        {QUICK_ACTIONS.map((action) => (
          <Col key={action.key} xs={12} md={8} lg={4}>
            <div
              className="jp-card"
              onClick={() => {
                const routeMap: Record<string, string> = {
                  chat: '/chat',
                  feedback: '/feedback',
                  itinerary: '/itinerary',
                  outfit: '/recommend?tab=outfit',
                  travel: '/recommend?tab=travel',
                }
                navigate(routeMap[action.key] ?? `/chat?topic=${action.key}`)
              }}
              style={{ padding: 20, cursor: 'pointer', height: '100%' }}
            >
              <Space direction="vertical" size={12}>
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: 44,
                    height: 44,
                    borderRadius: 12,
                    fontSize: 22,
                    color: action.color,
                    background: `${action.color}14`,
                  }}
                >
                  {action.icon}
                </span>
                <div>
                  <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--jp-ink)' }}>
                    {action.title}
                  </div>
                  <Paragraph style={{ margin: '4px 0 0', fontSize: 12.5, color: 'var(--jp-ink-2)' }}>
                    {action.desc}
                  </Paragraph>
                </div>
              </Space>
            </div>
          </Col>
        ))}
      </Row>
    </Space>
  )
}
