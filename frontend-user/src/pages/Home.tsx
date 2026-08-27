import { Card, Col, Row, Space, Typography } from 'antd'
import {
  MessageOutlined,
  ThunderboltOutlined,
  CalendarOutlined,
  CompassOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import WeatherHero from '../components/WeatherHero'
import ForecastList from '../components/ForecastList'

const { Title, Paragraph } = Typography

// 快捷功能入口（预留：穿搭/出行推荐 Day 18 接入具体页面）
const QUICK_ACTIONS = [
  {
    key: 'chat',
    icon: <MessageOutlined style={{ fontSize: 28 }} />,
    title: 'AI 智能问答',
    desc: '天气 / 穿搭 / 出行一站式咨询',
    color: '#1677ff',
  },
  {
    key: 'outfit',
    icon: <ThunderboltOutlined style={{ fontSize: 28 }} />,
    title: '穿搭推荐',
    desc: '根据天气场景推荐今日穿搭',
    color: '#722ed1',
  },
  {
    key: 'travel',
    icon: <CompassOutlined style={{ fontSize: 28 }} />,
    title: '出行规划',
    desc: '多维度评分推荐最优路线',
    color: '#13c2c2',
  },
  {
    key: 'itinerary',
    icon: <CalendarOutlined style={{ fontSize: 28 }} />,
    title: '行程提醒',
    desc: '结合天气的出行提醒',
    color: '#fa8c16',
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
          <Col key={action.key} xs={12} md={6}>
            <Card
              hoverable
              onClick={() =>
                action.key === 'chat' ? navigate('/chat') : navigate(`/chat?topic=${action.key}`)
              }
              style={{ borderRadius: 16, height: '100%' }}
              styles={{ body: { padding: 20 } }}
            >
              <Space direction="vertical" size={8}>
                <span style={{ color: action.color }}>{action.icon}</span>
                <Title level={5} style={{ margin: 0 }}>
                  {action.title}
                </Title>
                <Paragraph type="secondary" style={{ margin: 0, fontSize: 12 }}>
                  {action.desc}
                </Paragraph>
              </Space>
            </Card>
          </Col>
        ))}
      </Row>

      {/* 预留：出行/穿搭推荐结果展示区（Day 18 接入） */}
      <Card title="为你推荐" style={{ borderRadius: 16 }}>
        <Paragraph type="secondary" style={{ margin: 0 }}>
          出行推荐、穿搭建议、行程提醒等内容将在这里展示（开发中）。
        </Paragraph>
      </Card>
    </Space>
  )
}
