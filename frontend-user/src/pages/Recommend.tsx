import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  AutoComplete,
  Button,
  Dropdown,
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
  getOutfitPosts,
  getWeatherHead,
  recommendOutfit,
  recommendTravel,
  type OutfitIdeas,
  type OutfitResult,
  type TravelResult,
  type WeatherHead,
} from '../api/recommend'
import { listLandmarks, suggestPlaces, type PlaceItem } from '../api/places'
import { getWeatherVisual } from '../utils/weather'

const { Text, Paragraph } = Typography

type Tab = 'travel' | 'outfit'

// 联想下拉项：除展示用 label 外，额外携带完整地点信息（含坐标）
type PlaceOption = { value: string; label: React.ReactNode; place: PlaceItem }

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

  // 已选中的地点（含坐标）：从联想下拉或常用地点选择后写入，
  // 提交规划时把坐标一并传给后端，跳过地名解析，避免「认不出地名」而失败
  const [originPoint, setOriginPoint] = useState<PlaceItem | null>(null)
  const [destinationPoint, setDestinationPoint] = useState<PlaceItem | null>(null)
  const [originOptions, setOriginOptions] = useState<PlaceOption[]>([])
  const [destOptions, setDestOptions] = useState<PlaceOption[]>([])
  const [landmarks, setLandmarks] = useState<PlaceItem[]>([])
  const originTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const destTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // 穿搭表单
  const [scene, setScene] = useState<string | null>(null)
  const [pref, setPref] = useState<string | null>(null)
  const [outfitLoading, setOutfitLoading] = useState(false)
  const [outfit, setOutfit] = useState<OutfitResult | null>(null)
  // 穿搭灵感（社交平台内容）：独立加载，避免联网搜索拖慢规则建议
  const [ideas, setIdeas] = useState<OutfitIdeas | null>(null)
  const [ideasLoading, setIdeasLoading] = useState(false)

  useEffect(() => {
    getWeatherHead().then(setHead).catch(() => {})
    // 常用地点：兜底入口，一个字不打也能一键选点
    listLandmarks().then(setLandmarks).catch(() => {})
  }, [])

  // 输入联想：300ms 防抖，避免每敲一个字都打接口
  const searchPlaces = useCallback(
    (
      keyword: string,
      timer: { current: ReturnType<typeof setTimeout> | null },
      setOptions: (v: PlaceOption[]) => void,
    ) => {
      if (timer.current) clearTimeout(timer.current)
      const kw = keyword.trim()
      if (!kw) {
        setOptions([])
        return
      }
      timer.current = setTimeout(async () => {
        const items = await suggestPlaces(kw).catch(() => [] as PlaceItem[])
        setOptions(
          items.map((it) => ({
            value: it.name,
            label: (
              <span>
                {it.name}
                {it.district ? (
                  <Text style={{ color: 'var(--jp-ink-3)', fontSize: 12, marginLeft: 8 }}>
                    {it.district.replace(/^广东省/, '')}
                  </Text>
                ) : null}
              </span>
            ),
            place: it,
          })),
        )
      }, 300)
    },
    [],
  )

  const loadTravel = async () => {
    if (!origin.trim() || !destination.trim()) {
      setTravelError('请填写出发地和目的地')
      return
    }
    setTravelLoading(true)
    setTravelError(null)
    try {
      const res = await recommendTravel(origin.trim(), destination.trim(), undefined, {
        origin_lng: originPoint?.lng,
        origin_lat: originPoint?.lat,
        destination_lng: destinationPoint?.lng,
        destination_lat: destinationPoint?.lat,
      })
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
    setIdeas(null)
    setIdeasLoading(true)
    try {
      const res = await recommendOutfit('广州', scene ?? undefined, pref ?? undefined)
      setOutfit(res)
    } finally {
      setOutfitLoading(false)
    }
    // 灵感放在建议渲染之后单独拉取：它要联网搜索，耗时数秒
    try {
      setIdeas(await getOutfitPosts('广州', scene ?? undefined, pref ?? undefined))
    } catch {
      setIdeas(null)
    } finally {
      setIdeasLoading(false)
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
              <AutoComplete
                value={origin}
                options={originOptions}
                onSearch={(v) => searchPlaces(v, originTimer, setOriginOptions)}
                onSelect={(_v, option) =>
                  setOriginPoint((option as unknown as PlaceOption).place)
                }
                onChange={(v) => {
                  setOrigin(v)
                  setOriginPoint(null) // 手改文字后坐标失效，避免与实际文字不符
                }}
                style={{ width: '100%' }}
              >
                <Input
                  prefix={<LeftOutlined style={{ color: 'var(--jp-ink-3)' }} />}
                  placeholder="出发地：输入后从下拉选择"
                />
              </AutoComplete>
              <AutoComplete
                value={destination}
                options={destOptions}
                onSearch={(v) => searchPlaces(v, destTimer, setDestOptions)}
                onSelect={(_v, option) =>
                  setDestinationPoint((option as unknown as PlaceOption).place)
                }
                onChange={(v) => {
                  setDestination(v)
                  setDestinationPoint(null)
                }}
                style={{ width: '100%' }}
              >
                <Input
                  prefix={<RightOutlined style={{ color: 'var(--jp-ink-3)' }} />}
                  placeholder="目的地：输入后从下拉选择"
                />
              </AutoComplete>
              <Button
                type="primary"
                icon={<ThunderboltOutlined />}
                loading={travelLoading}
                onClick={loadTravel}
              >
                智能规划
              </Button>
            </div>

            {/* 常用地点：一键填入（点击标签选「设为出发地 / 目的地」） */}
            {landmarks.length > 0 && (
              <div style={{ marginTop: 12 }}>
                <Text style={{ color: 'var(--jp-ink-3)', fontSize: 12, marginRight: 8 }}>
                  常用地点
                </Text>
                <Space wrap size={[6, 6]}>
                  {landmarks.map((p) => (
                    <Dropdown
                      key={p.name}
                      trigger={['click']}
                      menu={{
                        items: [
                          { key: 'origin', label: '设为出发地' },
                          { key: 'dest', label: '设为目的地' },
                        ],
                        onClick: ({ key }) => {
                          if (key === 'origin') {
                            setOrigin(p.name)
                            setOriginPoint(p)
                          } else {
                            setDestination(p.name)
                            setDestinationPoint(p)
                          }
                        },
                      }}
                    >
                      <Tag style={{ cursor: 'pointer', margin: 0 }}>{p.name}</Tag>
                    </Dropdown>
                  ))}
                </Space>
              </div>
            )}

            {/* 选点状态：明确告知当前按「坐标」还是「地名」规划 */}
            <div style={{ marginTop: 10, fontSize: 12, color: 'var(--jp-ink-3)' }}>
              {originPoint
                ? `出发地已锁定坐标（${originPoint.lng.toFixed(4)}, ${originPoint.lat.toFixed(4)}）`
                : '出发地未选点，将按地名解析'}
              {' · '}
              {destinationPoint
                ? `目的地已锁定坐标（${destinationPoint.lng.toFixed(4)}, ${destinationPoint.lat.toFixed(4)}）`
                : '目的地未选点，将按地名解析'}
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

              {/* 穿搭灵感：社交平台真实搭配参考 */}
              <div className="jp-card" style={{ padding: 20 }}>
                <div style={{ marginBottom: 12 }}>
                  <span className="jp-serif" style={{ fontSize: 15, fontWeight: 700, color: 'var(--jp-indigo)' }}>
                    ✨ 穿搭灵感
                  </span>
                  {ideas?.keyword ? (
                    <Text
                      style={{ fontSize: 12, color: 'var(--jp-ink-3)', marginLeft: 8 }}
                    >
                      为你搜「{ideas.keyword}」
                    </Text>
                  ) : null}
                </div>

                {ideasLoading ? (
                  <Skeleton active paragraph={{ rows: 3 }} />
                ) : (
                  <>
                    {ideas?.posts?.length ? (
                      <div
                        style={{
                          display: 'grid',
                          gridTemplateColumns: 'repeat(auto-fill,minmax(280px,1fr))',
                          gap: 12,
                        }}
                      >
                        {ideas.posts.map((p) => (
                          <a
                            key={p.url}
                            href={p.url}
                            target="_blank"
                            rel="noreferrer"
                            className="jp-card"
                            style={{ padding: 14, display: 'block', textDecoration: 'none' }}
                          >
                            <Tag
                              color={p.platform === '抖音' ? 'magenta' : 'blue'}
                              style={{ margin: '0 0 6px' }}
                            >
                              {p.platform}
                            </Tag>
                            <div
                              style={{
                                color: 'var(--jp-ink)',
                                fontSize: 13.5,
                                fontWeight: 600,
                                lineHeight: 1.5,
                              }}
                            >
                              {p.title}
                            </div>
                            {p.snippet ? (
                              <Paragraph
                                style={{ margin: '6px 0 0', color: 'var(--jp-ink-2)', fontSize: 12 }}
                                ellipsis={{ rows: 2 }}
                              >
                                {p.snippet}
                              </Paragraph>
                            ) : null}
                          </a>
                        ))}
                      </div>
                    ) : (
                      <Text style={{ color: 'var(--jp-ink-2)', fontSize: 13 }}>
                        暂时没搜到合适的搭配内容，可以从下方平台入口直接浏览。
                      </Text>
                    )}

                    {/* 平台搜索直达：小红书站内笔记搜不到，但搜索页可直接打开 */}
                    {ideas?.portals?.length ? (
                      <div style={{ marginTop: 14 }}>
                        <Text style={{ color: 'var(--jp-ink-3)', fontSize: 12, marginRight: 8 }}>
                          去平台看更多
                        </Text>
                        <Space wrap size={[8, 8]}>
                          {ideas.portals.map((pt) => (
                            <Button
                              key={pt.platform}
                              size="small"
                              href={pt.url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              {pt.platform}
                            </Button>
                          ))}
                        </Space>
                      </div>
                    ) : null}
                  </>
                )}
              </div>
            </>
          ) : null}
        </Space>
      )}
    </Space>
  )
}
