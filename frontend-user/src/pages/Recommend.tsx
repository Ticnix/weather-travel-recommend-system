import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Button,
  Input,
  Progress,
  Segmented,
  Skeleton,
  Space,
  Tag,
  Typography,
} from 'antd'
import {
  EnvironmentOutlined,
  ThunderboltOutlined,
  ClockCircleOutlined,
  CarOutlined,
  RiseOutlined,
  SafetyOutlined,
  LeftOutlined,
  RightOutlined,
} from '@ant-design/icons'
import {
  getWeatherHead,
  recommendOutfit,
  recommendTravel,
  type OutfitResult,
  type TravelResult,
  type WeatherHead,
} from '../api/recommend'
import { getWeatherVisual } from '../utils/weather'

const { Text, Paragraph } = Typography

type Tab = 'travel' | 'outfit'

// 交通方式 → 图标/点缀色
const MODE_META: Record<string, { color: string; icon: React.ReactNode }> = {
  驾车: { color: '#3b5b8c', icon: <CarOutlined /> },
  '地铁/公交': { color: '#5a7d5a', icon: <EnvironmentOutlined /> },
  骑行: { color: '#d99a4e', icon: <RiseOutlined /> },
  步行: { color: '#e3a7ad', icon: <RiseOutlined /> },
}

const OUTFIT_SCENES = ['爬山', '逛街', '夜游', '商务', '通勤', '露营', '骑行', '亲子']
const OUTFIT_PREFS = ['怕冷', '怕热', '正式', '运动', '休闲', '简约', '时尚']

function fmtTime(min: number): string {
  if (min < 60) return `${min} 分钟`
  const h = Math.floor(min / 60)
  const m = min % 60
  return m ? `${h} 小时 ${m} 分` : `${h} 小时`
}

export default function Recommend() {
  const [searchParams] = useSearchParams()
  const [tab, setTab] = useState<Tab>(
    (searchParams.get('tab') as Tab) === 'outfit' ? 'outfit' : 'travel',
  )
  const [head, setHead] = useState<WeatherHead | null>(null)

  // 出行表单
  const [origin, setOrigin] = useState('广州南站')
  const [destination, setDestination] = useState('广州塔')
  const [travelLoading, setTravelLoading] = useState(false)
  const [travel, setTravel] = useState<TravelResult | null>(null)
  const [travelError, setTravelError] = useState<string | null>(null)

  // 穿搭表单
  const [scene, setScene] = useState<string | null>(null)
  const [pref, setPref] = useState<string | null>(null)
  const [outfitLoading, setOutfitLoading] = useState(false)
  const [outfit, setOutfit] = useState<OutfitResult | null>(null)

  useEffect(() => {
    getWeatherHead().then(setHead).catch(() => {})
  }, [])

  const loadTravel = async () => {
    if (!origin.trim() || !destination.trim()) {
      setTravelError('请填写出发地和目的地')
      return
    }
    setTravelLoading(true)
    setTravelError(null)
    try {
      const res = await recommendTravel(origin.trim(), destination.trim())
      if (res.error) {
        setTravel(null)
        setTravelError(res.error)
      } else {
        setTravel(res)
      }
    } catch {
      setTravel(null)
      setTravelError('推荐服务暂时不可用，请稍后重试')
    } finally {
      setTravelLoading(false)
    }
  }

  const loadOutfit = async () => {
    setOutfitLoading(true)
    try {
      const res = await recommendOutfit('广州', scene ?? undefined, pref ?? undefined)
      setOutfit(res)
    } finally {
      setOutfitLoading(false)
    }
  }

  useEffect(() => {
    if (tab === 'travel') {
      loadTravel()
    } else {
      loadOutfit()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab])

  const visual = head ? getWeatherVisual(head.desc) : getWeatherVisual(null)

  return (
    <Space direction="vertical" size={20} style={{ width: '100%' }}>
      {/* 今日天气概要头 */}
      <div className="jp-card" style={{ padding: '20px 24px' }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 12,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <span style={{ fontSize: 44 }}>{head ? visual.icon : '🌤️'}</span>
            <div>
              <div className="jp-serif" style={{ fontSize: 18, fontWeight: 600, color: 'var(--jp-ink)' }}>
                广州 · {head?.desc ?? '…'}
              </div>
              <Text style={{ color: 'var(--jp-ink-2)', fontSize: 13 }}>
                {head ? `${head.temp_min ?? '--'}~${head.temp_max ?? '--'}°C` : ''}
                {head?.feels_like != null ? ` · 体感 ${head.feels_like}°C` : ''}
                {head?.humidity != null ? ` · 湿度 ${head.humidity}%` : ''}
              </Text>
            </div>
          </div>
          <Segmented
            value={tab}
            onChange={(v) => setTab(v as Tab)}
            options={[
              { label: '🚇 出行方案', value: 'travel' },
              { label: '👔 穿搭建议', value: 'outfit' },
            ]}
          />
        </div>
      </div>

      {/* ========== 出行规划 ========== */}
      {tab === 'travel' && (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          {/* 输入区 */}
          <div className="jp-card" style={{ padding: 20 }}>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr auto',
                gap: 12,
                alignItems: 'center',
              }}
            >
              <Input
                value={origin}
                onChange={(e) => setOrigin(e.target.value)}
                prefix={<LeftOutlined style={{ color: 'var(--jp-ink-3)' }} />}
                placeholder="出发地，如 广州南站"
              />
              <Input
                value={destination}
                onChange={(e) => setDestination(e.target.value)}
                prefix={<RightOutlined style={{ color: 'var(--jp-ink-3)' }} />}
                placeholder="目的地，如 广州塔"
              />
              <Button
                type="primary"
                icon={<ThunderboltOutlined />}
                loading={travelLoading}
                onClick={loadTravel}
              >
                智能规划
              </Button>
            </div>
          </div>

          {travelError && (
            <div className="jp-card" style={{ padding: 24, textAlign: 'center' }}>
              <Text style={{ color: 'var(--jp-vermilion)' }}>{travelError}</Text>
            </div>
          )}

          {travelLoading ? (
            <div className="jp-card" style={{ padding: 24 }}>
              <Skeleton active paragraph={{ rows: 6 }} />
            </div>
          ) : travel ? (
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '0 4px' }}>
                <span className="jp-chip" style={{ fontWeight: 600 }}>
                  <EnvironmentOutlined /> {travel.origin}
                </span>
                <span style={{ color: 'var(--jp-ink-3)' }}>→</span>
                <span className="jp-chip" style={{ fontWeight: 600 }}>
                  {travel.destination}
                </span>
                <Text style={{ color: 'var(--jp-ink-3)', fontSize: 12, marginLeft: 'auto' }}>
                  {travel.routes.length} 套方案 · 按综合评分排序
                </Text>
              </div>

              {/* 天气提示 */}
              {travel.weather.desc && (
                <div className="jp-card" style={{ padding: '12px 20px', background: 'rgba(217,84,63,0.05)' }}>
                  <Text style={{ color: 'var(--jp-vermilion)' }}>
                    <SafetyOutlined /> 今日 {travel.weather.desc}
                    {travel.weather.temp_min != null
                      ? `，${travel.weather.temp_min}~${travel.weather.temp_max}°C`
                      : ''}
                    {travel.weather.precip ? `，降水 ${travel.weather.precip}mm` : ''}
                  </Text>
                </div>
              )}

              {/* 方案卡片 */}
              {travel.routes.map((r, i) => {
                const meta = MODE_META[r.mode] ?? { color: '#3b5b8c', icon: <CarOutlined /> }
                const best = i === 0
                const score = Math.round((r.total_score ?? 0.5) * 100)
                return (
                  <div
                    key={i}
                    className="jp-card"
                    style={{
                      padding: '18px 20px',
                      borderLeft: `4px solid ${meta.color}`,
                      background: best ? 'rgba(90,125,90,0.05)' : undefined,
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'flex-start',
                        flexWrap: 'wrap',
                        gap: 10,
                      }}
                    >
                      <Space size={10} align="center">
                        <span
                          style={{
                            fontSize: 20,
                            color: meta.color,
                            width: 36,
                            height: 36,
                            display: 'inline-flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            borderRadius: 10,
                            background: `${meta.color}14`,
                          }}
                        >
                          {meta.icon}
                        </span>
                        <div>
                          <Space size={8}>
                            <Text style={{ fontWeight: 700, fontSize: 16, color: 'var(--jp-ink)' }}>
                              {r.mode}
                            </Text>
                            {best && <Tag color="green" style={{ margin: 0 }}>推荐</Tag>}
                          </Space>
                          <div style={{ color: 'var(--jp-ink-2)', fontSize: 13, marginTop: 2 }}>
                            <ClockCircleOutlined /> {fmtTime(r.duration_min)} · {r.distance_km} km · 约 {r.cost} 元
                          </div>
                        </div>
                      </Space>
                      <div style={{ width: 150 }}>
                        <div
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            fontSize: 12,
                            color: 'var(--jp-ink-2)',
                            marginBottom: 2,
                          }}
                        >
                          <span>综合评分</span>
                          <Text style={{ color: 'var(--jp-ink)', fontWeight: 700 }}>
                            {r.total_score?.toFixed(2)}
                          </Text>
                        </div>
                        <Progress
                          percent={score}
                          showInfo={false}
                          size="small"
                          strokeColor={meta.color}
                        />
                      </div>
                    </div>
                    {r.detail && (
                      <Paragraph
                        style={{ margin: '10px 0 0', color: 'var(--jp-ink-2)', fontSize: 12.5 }}
                        ellipsis={{ rows: 2, expandable: true, symbol: '展开路线' }}
                      >
                        {r.detail}
                      </Paragraph>
                    )}
                  </div>
                )
              })}
            </>
          ) : null}
        </Space>
      )}

      {/* ========== 穿搭建议 ========== */}
      {tab === 'outfit' && (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <div className="jp-card" style={{ padding: 20 }}>
            <Space direction="vertical" size={14} style={{ width: '100%' }}>
              <div>
                <Text style={{ fontWeight: 600, color: 'var(--jp-ink)', display: 'block', marginBottom: 8 }}>
                  出行场景
                </Text>
                <Space wrap>
                  {OUTFIT_SCENES.map((s) => (
                    <Button
                      key={s}
                      size="small"
                      type={scene === s ? 'primary' : 'default'}
                      onClick={() => setScene(scene === s ? null : s)}
                    >
                      {s}
                    </Button>
                  ))}
                </Space>
              </div>
              <div>
                <Text style={{ fontWeight: 600, color: 'var(--jp-ink)', display: 'block', marginBottom: 8 }}>
                  个人偏好
                </Text>
                <Space wrap>
                  {OUTFIT_PREFS.map((p) => (
                    <Button
                      key={p}
                      size="small"
                      type={pref === p ? 'primary' : 'default'}
                      onClick={() => setPref(pref === p ? null : p)}
                    >
                      {p}
                    </Button>
                  ))}
                </Space>
              </div>
              <Button
                type="primary"
                icon={<ThunderboltOutlined />}
                loading={outfitLoading}
                onClick={loadOutfit}
              >
                获取穿搭建议
              </Button>
            </Space>
          </div>

          {outfitLoading ? (
            <div className="jp-card" style={{ padding: 24 }}>
              <Skeleton active paragraph={{ rows: 6 }} />
            </div>
          ) : outfit ? (
            <>
              {/* 气象摘要 */}
              <div className="jp-card" style={{ padding: 20 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 34 }}>{getWeatherVisual(outfit.weather.desc).icon}</span>
                  <div>
                    <Text style={{ fontWeight: 700, fontSize: 16, color: 'var(--jp-ink)' }}>
                      {outfit.weather.desc} · {outfit.weather.temp}°C
                      {outfit.weather.precip ? ` · 降水 ${outfit.weather.precip}mm` : ''}
                    </Text>
                    <div style={{ color: 'var(--jp-ink-2)', fontSize: 13 }}>
                      广州市 · {outfit.scene ? `场景：${outfit.scene}` : '通用'}
                      {outfit.preference ? ` · 偏好：${outfit.preference}` : ''}
                    </div>
                  </div>
                </div>
              </div>

              {/* 推荐结论 */}
              <div className="jp-card" style={{ padding: 24, background: 'rgba(59,91,140,0.04)' }}>
                <div className="jp-serif" style={{ fontSize: 15, fontWeight: 700, marginBottom: 10, color: 'var(--jp-indigo)' }}>
                  👔 穿搭建议
                </div>
                <Paragraph
                  style={{ fontSize: 15, lineHeight: 1.9, margin: 0, color: 'var(--jp-ink)', whiteSpace: 'pre-wrap' }}
                >
                  {outfit.suggestion}
                </Paragraph>
              </div>

              {/* 分项规则 */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(260px,1fr))', gap: 12 }}>
                {outfit.rules.map((rule, i) => {
                  const parts = rule.split('：')
                  const label = parts[0]
                  const body = parts.slice(1).join('：')
                  const cat =
                    outfit.temp_rule === rule
                      ? '温度'
                      : /爬山|逛街|夜游|商务|通勤|露营|骑行|亲子|摄影/.test(rule)
                        ? '场景'
                        : /雨|雪|雷|风|雾|霾/.test(rule)
                          ? '天气'
                          : '提示'
                  return (
                    <div key={i} className="jp-card" style={{ padding: 16 }}>
                      <Tag color="blue" style={{ marginBottom: 6 }}>{cat}</Tag>
                      <Text style={{ fontWeight: 700, color: 'var(--jp-ink)' }}>{label}</Text>
                      <Paragraph style={{ margin: '4px 0 0', color: 'var(--jp-ink-2)', fontSize: 13 }}>{body}</Paragraph>
                    </div>
                  )
                })}
              </div>
            </>
          ) : null}
        </Space>
      )}
    </Space>
  )
}
