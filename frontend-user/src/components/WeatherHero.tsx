import { Card, Col, Row, Space, Statistic, Tag, Typography, Spin, Empty } from 'antd'
import { useEffect, useState } from 'react'
import { getCurrentWeather, type CurrentWeather } from '../api/weather'
import { getWeatherVisual } from '../utils/weather'

const { Title, Text } = Typography

// 首页顶部天气主卡片：大图标 + 温度 + 关键指标
export default function WeatherHero() {
  const [weather, setWeather] = useState<CurrentWeather | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getCurrentWeather()
      .then(setWeather)
      .catch(() => setWeather(null))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <Card style={{ textAlign: 'center', padding: 40 }}>
        <Spin tip="正在获取实时天气..." />
      </Card>
    )
  }

  if (!weather) {
    return (
      <Card>
        <Empty description="暂无天气数据，请稍后刷新" />
      </Card>
    )
  }

  const visual = getWeatherVisual(weather.weather_desc)

  return (
    <Card
      style={{
        background: `linear-gradient(135deg, ${visual.color}22 0%, #ffffff 60%)`,
        borderRadius: 16,
        overflow: 'hidden',
      }}
      styles={{ body: { padding: '32px' } }}
    >
      <Row align="middle" gutter={[32, 24]}>
        <Col flex="auto">
          <Space size={20} align="center">
            <span style={{ fontSize: 88, lineHeight: 1 }}>{visual.icon}</span>
            <div>
              <Title level={1} style={{ margin: 0, fontSize: 56 }}>
                {weather.temperature ?? '--'}
                <span style={{ fontSize: 28 }}>°C</span>
              </Title>
              <Space size={8} style={{ marginTop: 8 }}>
                <Tag color={visual.color}>{visual.label}</Tag>
                <Text type="secondary">体感 {weather.feels_like ?? '--'}°C</Text>
              </Space>
            </div>
          </Space>
        </Col>

        <Col>
          <Space size={32} wrap>
            <Statistic title="湿度" value={weather.humidity ?? '--'} suffix="%" />
            <Statistic title="风速" value={weather.wind_speed ?? '--'} suffix="km/h" />
            <Statistic title="降水量" value={weather.precipitation ?? '--'} suffix="mm" />
            <Statistic title="能见度" value={weather.visibility ?? '--'} suffix="km" />
          </Space>
        </Col>
      </Row>
    </Card>
  )
}
