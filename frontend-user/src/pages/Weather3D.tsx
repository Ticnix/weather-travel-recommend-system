import { Card, Radio, Space, Tag, Typography, Spin, Empty } from 'antd'
import { useEffect, useState } from 'react'
import WeatherScene from '../components/three/WeatherScene'
import type { WeatherType } from '../components/three/effects/weatherParticles'
import { getCurrentWeather, type CurrentWeather } from '../api/weather'
import { mapWeatherType, WEATHER_TYPE_LABEL } from '../utils/weatherType'

const { Title, Text } = Typography

// 3D 天气可视化页面：展示实时天气驱动的 3D 场景 + 可手动切换天气特效
export default function Weather3D() {
  const [weather, setWeather] = useState<CurrentWeather | null>(null)
  const [loading, setLoading] = useState(true)
  // 当前生效的天气类型（默认跟随实时天气，可手动覆盖）
  const [weatherType, setWeatherType] = useState<WeatherType>('sunny')
  const [autoFollow, setAutoFollow] = useState(true)

  useEffect(() => {
    getCurrentWeather()
      .then((w) => {
        setWeather(w)
        if (w) setWeatherType(mapWeatherType(w.weather_desc))
      })
      .catch(() => setWeather(null))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <Card style={{ height: 600, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Spin tip="正在加载 3D 场景..." />
      </Card>
    )
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card style={{ borderRadius: 16 }}>
        <Space size={16} wrap>
          <Title level={4} style={{ margin: 0 }}>
            广州 3D 天气可视化
          </Title>
          <Tag color="blue">{WEATHER_TYPE_LABEL[weatherType]}</Tag>
          {weather && (
            <Text type="secondary">
              实时天气：{weather.weather_desc} {weather.temperature}°C
            </Text>
          )}
          <Radio.Group
            value={autoFollow ? 'auto' : 'manual'}
            onChange={(e) => setAutoFollow(e.target.value === 'auto')}
            size="small"
          >
            <Radio.Button value="auto">跟随实时天气</Radio.Button>
            <Radio.Button value="manual">手动切换</Radio.Button>
          </Radio.Group>
        </Space>

        {/* 手动切换天气特效 */}
        {!autoFollow && (
          <Space wrap style={{ marginTop: 12 }}>
            {(Object.keys(WEATHER_TYPE_LABEL) as WeatherType[]).map((t) => (
              <Tag.CheckableTag
                key={t}
                checked={weatherType === t}
                onChange={() => setWeatherType(t)}
              >
                {WEATHER_TYPE_LABEL[t]}
              </Tag.CheckableTag>
            ))}
          </Space>
        )}
      </Card>

      {/* 3D 场景 */}
      <Card
        style={{ borderRadius: 16 }}
        styles={{ body: { padding: 0, height: 520, overflow: 'hidden' } }}
      >
        {weather ? (
          <WeatherScene weatherType={weatherType} />
        ) : (
          <Empty style={{ marginTop: 200 }} description="暂无天气数据" />
        )}
      </Card>

      <Text type="secondary" style={{ fontSize: 12 }}>
        提示：鼠标拖拽旋转视角，滚轮缩放，右键平移。
      </Text>
    </Space>
  )
}
