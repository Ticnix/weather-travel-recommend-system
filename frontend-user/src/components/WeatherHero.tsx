import { Button, Col, Row, Space, Tag, Typography } from 'antd'
import { EnvironmentOutlined } from '@ant-design/icons'
import { useCallback, useEffect, useState } from 'react'
import {
  getCurrentWeather,
  getLocalWeather,
  type CurrentWeather,
  type LocalLocationInfo,
} from '../api/weather'
import { getWeatherVisual } from '../utils/weather'
import { useLocalLocation } from '../utils/localLocation'
import LocationPicker from './LocationPicker'
import LoadingState from './LoadingState'
import EmptyState from './EmptyState'
import { useIsMobile } from '../utils/useIsMobile'

const { Text } = Typography

// 首页顶部天气主卡片（日式简洁）：温润大数字 + 柔和指标
export default function WeatherHero() {
  const isMobile = useIsMobile()
  const local = useLocalLocation()
  const [weather, setWeather] = useState<CurrentWeather | null>(null)
  // 这次数据是"按哪个区"取的；null = 还没选过区域，按城市中心
  const [basis, setBasis] = useState<LocalLocationInfo | null>(null)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  // 区级取数失败、已退回城市数据：必须让用户知道现在看的是城市而非本区
  const [districtFailed, setDistrictFailed] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    setDistrictFailed(false)
    // 选了区就按区取（更准），没选就沿用城市实测。
    // 注意刷新页面时用**区名**而不是坐标：同一结果能命中后端缓存，也不必重复定位
    const useLocal = Boolean(local?.district) || Boolean(local?.lat && local?.lon)
    const request = useLocal
      ? getLocalWeather(
          local?.district
            ? { district: local.district }
            : { lat: local?.lat, lon: local?.lon },
        )
          .then((res) => {
            setBasis(res.location)
            return res.current
          })
          .catch(() =>
            // 区级上游偶发连不上时，不要甩给用户一张错误卡：
            // 退回城市实测并标明"这是城市数据"，至少还有天气可看
            getCurrentWeather().then((current) => {
              setBasis(null)
              setDistrictFailed(true)
              return current
            }),
          )
      : getCurrentWeather().then((current) => {
          setBasis(null)
          return current
        })

    request
      .then(setWeather)
      .catch(() => setWeather(null))
      .finally(() => setLoading(false))
  }, [local])

  useEffect(() => {
    load()
  }, [load])

  // 选择器挂在每个分支里：错误态时用户也需要能改区域（可能只是这个区取不到）
  const picker = <LocationPicker open={pickerOpen} onClose={() => setPickerOpen(false)} />

  if (loading) {
    return (
      <>
        <div className="jp-card" style={{ padding: 24 }}>
          <LoadingState
            text="正在获取实时天气…"
            hint="正在向气象服务拉取当前观测数据，通常 1~2 秒"
          />
        </div>
        {picker}
      </>
    )
  }

  if (!weather) {
    return (
      <>
        <div className="jp-card" style={{ padding: 24 }}>
          {/* 取不到和"本来就没数据"不是一回事：给原因 + 重试入口 */}
          <EmptyState
            type="error"
            text="天气数据没能取到"
            hint="气象服务可能暂时不可用，稍后重试即可"
            onRetry={load}
            retryText="重新获取"
          />
        </div>
        {picker}
      </>
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
    <>
    <div className="jp-card" style={{ padding: isMobile ? 14 : '28px 32px' }}>
      {/* 先说明"这是哪里的天气"：广州南北差好几度，
          不写依据的话，用户不知道看到的是自己区还是市中心的数字 */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          flexWrap: 'wrap',
          marginBottom: isMobile ? 10 : 16,
        }}
      >
        <span style={{ fontSize: isMobile ? 13 : 14, color: 'var(--jp-ink-2)' }}>
          <EnvironmentOutlined /> {basis ? basis.label : '广州市中心'}
        </span>
        {basis?.source === 'geo' && <Tag color="cyan">已定位</Tag>}
        {basis?.precision === 'city' && (
          <Tag style={{ color: 'var(--jp-ink-3)' }}>市中心精度</Tag>
        )}
        <Button
          type="link"
          size="small"
          style={{ padding: 0 }}
          onClick={() => setPickerOpen(true)}
        >
          {basis ? '切换区域' : '按我的区域看'}
        </Button>
        {districtFailed && (
          <Text style={{ fontSize: 12, color: 'var(--jp-vermilion)' }}>
            区级天气这次没取到，先显示城市数据
            <Button type="link" size="small" style={{ padding: '0 0 0 4px' }} onClick={load}>
              重试
            </Button>
          </Text>
        )}
      </div>

      <Row align="middle" gutter={[isMobile ? 12 : 32, isMobile ? 10 : 24]}>
        <Col flex="auto">
          <Space size={isMobile ? 12 : 24} align="center">
            {/* 手机上把大数字收小：桌面 84/60px 在 390px 宽里会把整行撑爆 */}
            <span style={{ fontSize: isMobile ? 44 : 84, lineHeight: 1 }}>{visual.icon}</span>
            <div>
              <div
                className="jp-serif"
                style={{
                  fontSize: isMobile ? 38 : 60,
                  fontWeight: 600,
                  lineHeight: 1,
                  color: 'var(--jp-ink)',
                }}
              >
                {weather.temperature ?? '--'}
                <span style={{ fontSize: isMobile ? 18 : 26, color: 'var(--jp-ink-2)' }}>°C</span>
              </div>
              <Space size={8} style={{ marginTop: isMobile ? 4 : 10 }} wrap>
                <span className="jp-chip" style={{ color: visual.color, borderColor: `${visual.color}55`, background: `${visual.color}12` }}>
                  {visual.label}
                </span>
                <Text style={{ color: 'var(--jp-ink-2)', fontSize: isMobile ? 12 : undefined }}>
                  体感 {weather.feels_like ?? '--'}°C
                </Text>
              </Space>
            </div>
          </Space>
        </Col>

        <Col style={{ width: isMobile ? '100%' : undefined }}>
          {isMobile ? (
            /* 手机：四项指标排成一行四格（等宽），比桌面那种大间距横排省一半高度 */
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(4, 1fr)',
                gap: 6,
                width: '100%',
              }}
            >
              {metrics.map((m) => (
                <div key={m.label} style={{ textAlign: 'center' }}>
                  <div className="jp-serif" style={{ fontSize: 15, fontWeight: 600, color: 'var(--jp-ink)' }}>
                    {m.value ?? '--'}
                    <span style={{ fontSize: 10, marginLeft: 1, color: 'var(--jp-ink-2)' }}>{m.unit}</span>
                  </div>
                  <div style={{ color: 'var(--jp-ink-3)', fontSize: 11, marginTop: 2 }}>{m.label}</div>
                </div>
              ))}
            </div>
          ) : (
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
          )}
        </Col>
      </Row>
    </div>
    {picker}
    </>
  )
}
