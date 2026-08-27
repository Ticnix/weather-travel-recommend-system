import { Card, Col, Row, Skeleton, Typography } from 'antd'
import { useEffect, useState } from 'react'
import { getForecast, type ForecastDay } from '../api/weather'
import { getWeatherVisual, formatWeekday } from '../utils/weather'

const { Text } = Typography

// 7 天预报横向卡片列表
export default function ForecastList() {
  const [days, setDays] = useState<ForecastDay[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getForecast()
      .then((data) => setDays(data.items ?? []))
      .catch(() => setDays([]))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <Card title="7 天预报">
        <Skeleton active />
      </Card>
    )
  }

  return (
    <Card title="7 天预报" style={{ borderRadius: 16 }}>
      <Row gutter={[12, 12]}>
        {days.map((day, i) => {
          const visual = getWeatherVisual(day.weather_desc)
          return (
            <Col key={day.date ?? i} xs={12} sm={8} md={Math.floor(24 / Math.max(days.length, 1))} flex="1">
              <div
                style={{
                  textAlign: 'center',
                  padding: '12px 8px',
                  borderRadius: 12,
                  background: i === 0 ? '#f0f7ff' : 'transparent',
                  border: i === 0 ? '1px solid #91caff' : '1px solid transparent',
                }}
              >
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {i === 0 ? '今天' : formatWeekday(day.date)}
                </Text>
                <div style={{ fontSize: 28, margin: '8px 0' }}>{visual.icon}</div>
                <div style={{ fontWeight: 600 }}>
                  {day.temp_max ?? '--'}°{' '}
                  <Text type="secondary">/ {day.temp_min ?? '--'}°</Text>
                </div>
                <div style={{ fontSize: 12, color: '#666' }}>{visual.label}</div>
              </div>
            </Col>
          )
        })}
      </Row>
    </Card>
  )
}
