import { Col, Row, Space, Typography } from 'antd'
import {
  MessageOutlined,
  ThunderboltOutlined,
  CalendarOutlined,
  CompassOutlined,
  CommentOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import WeatherHero from '../components/WeatherHero'
import ForecastList from '../components/ForecastList'

const { Paragraph } = Typography

// 快捷功能入口（日式点缀色：小面积克制使用）
const QUICK_ACTIONS = [
  {
    key: 'chat',
    icon: <MessageOutlined />,
    title: 'AI 智能问答',
    desc: '天气 / 穿搭 / 出行一站式咨询',
    color: '#3b5b8c',
  },
  {
    key: 'outfit',
    icon: <ThunderboltOutlined />,
    title: '穿搭推荐',
    desc: '根据天气场景推荐今日穿搭',
    color: '#d9543f',
  },
  {
    key: 'travel',
    icon: <CompassOutlined />,
    title: '出行规划',
    desc: '多维度评分推荐最优路线',
    color: '#5a7d5a',
  },
  {
    key: 'itinerary',
    icon: <CalendarOutlined />,
    title: '行程提醒',
    desc: '结合天气的出行提醒',
    color: '#d99a4e',
  },
  {
    key: 'feedback',
    icon: <CommentOutlined />,
    title: '意见反馈',
    desc: '问题反馈与建议提交',
    color: '#e3a7ad',
  },
]

export default function Home() {
  const navigate = useNavigate()

  return (
    <Space direction="vertical" size={20} style={{ width: '100%' }}>
      {/* 天气主卡片 */}
      <WeatherHero />

      {/* 7 天预报 */}
      <ForecastList />

      {/* 快捷功能入口 */}
      <Row gutter={[16, 16]}>
        {QUICK_ACTIONS.map((action) => (
          <Col key={action.key} xs={12} md={8} lg={24 / 5 > 4 ? 4 : 4}>
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
              style={{
                padding: 20,
                cursor: 'pointer',
                height: '100%',
              }}
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

      {/* 智能推荐引导 */}
      <div
        className="jp-card"
        style={{ padding: 24, cursor: 'pointer' }}
        onClick={() => navigate('/recommend')}
      >
        <div className="jp-serif" style={{ fontSize: 16, fontWeight: 600, marginBottom: 8, color: 'var(--jp-ink)' }}>
          智能出行 · 穿搭助手
        </div>
        <Row gutter={[16, 8]}>
          <Col xs={24} md={12}>
            <Paragraph style={{ margin: 0, color: 'var(--jp-ink-2)' }}>
              🚇 输入出发地和目的地，获取多套带天气评分的最优出行方案
            </Paragraph>
          </Col>
          <Col xs={24} md={12}>
            <Paragraph style={{ margin: 0, color: 'var(--jp-ink-2)' }}>
              👔 按今日气象 + 出行场景，推荐最合适的穿搭
            </Paragraph>
          </Col>
        </Row>
      </div>
    </Space>
  )
}
