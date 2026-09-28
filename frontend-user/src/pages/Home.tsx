import { useCallback, useEffect, useState } from 'react'
import { Button, Col, Empty, Row, Space, Tag, Typography, message } from 'antd'
import {
  CalendarOutlined,
  ClockCircleOutlined,
  CommentOutlined,
  CompassOutlined,
  MessageOutlined,
  RightOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import WeatherHero from '../components/WeatherHero'
import ForecastList from '../components/ForecastList'
import LoadingState from '../components/LoadingState'
import EmptyState from '../components/EmptyState'
import HourlyChart from '../components/HourlyChart'
import MapLink from '../components/MapLink'
import { getDashboard, type HomeDashboard } from '../api/home'
import { isLoggedIn } from '../api/auth'
import { useIsMobile } from '../utils/useIsMobile'

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
  // 加载失败必须和"确实没数据"分开：否则用户看到"暂无提醒"会以为一切正常，
  // 而实际上是接口挂了（这正是"功能没反应却不给提示"的典型观感）
  const [failed, setFailed] = useState(false)
  const loggedIn = isLoggedIn()
  const isMobile = useIsMobile()

  const load = useCallback(async () => {
    setLoading(true)
    setFailed(false)
    try {
      setDash(await getDashboard())
    } catch {
      setDash(null)
      setFailed(true)
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
  // 语音播报状态：没有这个反馈，"点了没声音"和"根本没播"用户分不清
  const [speaking, setSpeaking] = useState(false)

  // 三块内容都来自同一个接口，失败时统一给一份带重试的说明，
  // 而不是各自显示"暂无…"——那等于把"接口挂了"说成"你没有数据"
  const failedHint = (
    <EmptyState
      type="error"
      text="数据加载失败"
      hint="今日提醒 / 穿搭 / 近期行程来自同一个接口，这一次没取到"
      onRetry={() => void load()}
    />
  )

  return (
    <Space direction="vertical" size={20} style={{ width: '100%' }}>
      {/* 天气主卡片 */}
      <WeatherHero />

      {/* ===== 今日提醒（结合天气自动生成，无需跳转） ===== */}
      <div className="jp-card" style={{ padding: 20 }}>
        <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span className="jp-serif" style={{ fontSize: 16, fontWeight: 600, color: 'var(--jp-ink)' }}>
            <ThunderboltOutlined style={{ color: 'var(--jp-amber)' }} /> 今日提醒
          </span>
          {/* 语音播报（Day 61）：browser speechSynthesis，零成本零后端；
              出门前的场景是"手上有东西、没空看屏幕" */}
          {!loading && !failed && (
            <Button
              size="small"
              danger={speaking}
              onClick={() => {
                const synth = window.speechSynthesis
                if (!synth) {
                  message.warning('当前浏览器不支持语音播报')
                  return
                }
                // 再点一次 = 停止播报
                if (speaking) {
                  synth.cancel()
                  setSpeaking(false)
                  return
                }
                const parts = [
                  dash?.city ? `${dash.city}今日提醒。` : '今日提醒。',
                  ...tips.slice(0, 5).map((t) => `${t.title}。${t.text}`),
                  outfit?.suggestion ? `穿搭建议：${outfit.suggestion}` : '',
                ].filter(Boolean)
                const text = parts.join(' ')
                if (!text.trim()) {
                  message.info('暂无可播报的内容')
                  return
                }

                const speakOnce = () => {
                  const u = new SpeechSynthesisUtterance(text)
                  u.lang = 'zh-CN'
                  u.rate = 1
                  // 显式挑中文音色：默认音色常是英文引擎，读中文会整段沉默
                  const zh = synth
                    .getVoices()
                    .find((v) => v.lang.replace('_', '-').toLowerCase().startsWith('zh'))
                  if (zh) u.voice = zh
                  u.onstart = () => setSpeaking(true)
                  u.onend = () => setSpeaking(false)
                  u.onerror = (ev) => {
                    setSpeaking(false)
                    // 用户点"停止"触发的中断不是错误
                    if (ev.error !== 'interrupted' && ev.error !== 'canceled') {
                      message.error(`语音播报失败（${ev.error}）。可尝试换 Chrome/Edge 浏览器`)
                    }
                  }
                  synth.speak(u)
                }

                // Chrome 已知坑：cancel() 之后**同步** speak() 会被静默吞掉，
                // 所以先 cancel，立即播一次；400ms 后若确实没在播，再补一次
                synth.cancel()
                speakOnce()
                window.setTimeout(() => {
                  if (!synth.speaking && !synth.pending) speakOnce()
                }, 400)
              }}
            >
              {speaking ? '⏹ 停止' : '🔊 播报'}
            </Button>
          )}
        </div>
        {/* 加载文案刻意避开「今日提醒」这个标题词：e2e 的文本断言是子串匹配，
            文案里再出现一次标题会让断言命中两个元素 */}
        {loading ? (
          <LoadingState
            compact
            text="正在整理今天的注意事项…"
            hint="要结合当天天气与你的行程逐条判断，通常 1~2 秒"
          />
        ) : failed ? (
          failedHint
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

      {/* ===== 24 小时天气曲线（对手产品标配能力，Day 59 补齐） ===== */}
      <HourlyChart city={dash?.city} />

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
          <LoadingState compact text="正在搭配今天的穿着…" hint="按当天温度、降水与风况匹配穿搭规则" />
        ) : failed ? (
          failedHint
        ) : outfit ? (
          <>
            {/* 手机上这条建议常常四五行长：先收成三行，想看全再展开（"文字堆在一起"的主要来源之一） */}
            <Paragraph
              style={{ margin: 0, color: 'var(--jp-ink)', lineHeight: 1.9, fontSize: 14 }}
              ellipsis={isMobile ? { rows: 3, expandable: true, symbol: '展开' } : false}
            >
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
          <LoadingState
            compact
            text="正在加载你的行程…"
            hint="顺带拉取每条行程当天的天气提醒"
          />
        ) : failed ? (
          failedHint
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
                  {/* 地点名可点开地图：出门前最常确认的就是"这地方在哪" */}
                  <Text style={{ fontWeight: 600, color: 'var(--jp-ink)' }}>
                    <MapLink name={it.title} city={it.city} />
                  </Text>
                  {it.location && it.location !== it.title && (
                    <Text style={{ color: 'var(--jp-ink-3)', fontSize: 12 }}>
                      <MapLink name={it.location} city={it.city} />
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
                  {/* 手机上只留图标 + 标题：两列布局里再塞一行说明只会更挤 */}
                  <Paragraph
                    className="jp-hide-mobile"
                    style={{ margin: '4px 0 0', fontSize: 12.5, color: 'var(--jp-ink-2)' }}
                  >
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
