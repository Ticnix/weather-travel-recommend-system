import { Col, Row, Space, Spin, Typography } from 'antd'
import { useEffect, useState } from 'react'
import { getCurrentWeather, type CurrentWeather } from '../api/weather'
import { getWeatherVisual } from '../utils/weather'

const { Text } = Typography

// 首页顶部天气主卡片（日式简洁）：温润大数字 + 柔和指标
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
      <div className="jp-card" style={{ padding: 40, textAlign: 'center' }}>
        <Spin tip="正在获取实时天气..." />
      </div>
    )
  }

  if (!weather) {
    return (
      <div className="jp-card" style={{ padding: 40, textAlign: 'center' }}>
        <Text style={{ color: 'var(--jp-ink-2)' }}>暂无天气数据，请稍后刷新</Text>
      </div>
    )
  }

  const visual = getWeatherVisual(weather.weather_desc)

  const metrics = [
    { label: '湿度', value: weather.humidity, unit: '%' },
    { label: '风速', value: weather.wind_speed, unit: 'km/h' },
    { label: '降水', value: weather.precipitation, unit: 'mm' },
    { label: '能见度', value: weather.visibility, unit: 'km' },
  ]

  return (
    <div className="jp-card" style={{ padding: '28px 32px' }}>
      <Row align="middle" gutter={[32, 24]}>
        <Col flex="auto">
          <Space size={24} align="center">
            <span style={{ fontSize: 84, lineHeight: 1 }}>{visual.icon}</span>
            <div>
              <div
                className="jp-serif"
                style={{ fontSize: 60, fontWeight: 600, lineHeight: 1, color: 'var(--jp-ink)' }}
              >
                {weather.temperature ?? '--'}
                <span style={{ fontSize: 26, color: 'var(--jp-ink-2)' }}>°C</span>
              </div>
              <Space size={8} style={{ marginTop: 10 }}>
                <span className="jp-chip" style={{ color: visual.color, borderColor: `${visual.color}55`, background: `${visual.color}12` }}>
                  {visual.label}
                </span>
                <Text style={{ color: 'var(--jp-ink-2)' }}>体感 {weather.feels_like ?? '--'}°C</Text>
              </Space>
            </div>
          </Space>
        </Col>

        <Col>
          <Space size={32} wrap>
            {metrics.map((m) => (
              <div key={m.label} style={{ textAlign: 'center' }}>
                <div
                  className="jp-serif"
                  style={{ fontSize: 24, fontWeight: 600, color: 'var(--jp-ink)' }}
                >
                  {m.value ?? '--'}
                  <span style={{ fontSize: 12, marginLeft: 2, color: 'var(--jp-ink-2)' }}>{m.unit}</span>
                </div>
                <div style={{ color: 'var(--jp-ink-3)', fontSize: 12, marginTop: 4 }}>{m.label}</div>
              </div>
            ))}
          </Space>
        </Col>
      </Row>
    </div>
  )
}
