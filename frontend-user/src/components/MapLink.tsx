import type { ReactNode } from 'react'
import { EnvironmentOutlined } from '@ant-design/icons'

/** 高德 URI API 要求带一个来源标识（便于官方统计，也避免被判成未知来源） */
const SRC = 'weather-travel-assistant'

interface Props {
  /** 地点名：既作为地图搜索关键词，也是默认显示文案 */
  name: string
  /** 城市：只有地名、没有坐标时用来限定搜索范围（不然"北京路"可能搜到别的城市） */
  city?: string | null
  /** 坐标（来自后端候选 POI） */
  lng?: number | null
  lat?: number | null
  children?: ReactNode
  showIcon?: boolean
}

/**
 * 拼地图链接。
 *
 * 两档策略，优先级从准到糙：
 * 1. 有坐标 → `uri.amap.com/marker`，直接钉在点上（排程结果里的地点大多有坐标）
 * 2. 没坐标 → `uri.amap.com/search`，按地名（可带城市）搜索
 *    （「我的行程」里的数据是用户自己录入的，库里没存坐标，只能走这档）
 *
 * 显式导出是为了能单测：链接拼错了用户点开就是空地图，而这在页面上看不出来。
 */
export function mapUrl(
  name: string,
  opts: { city?: string | null; lng?: number | null; lat?: number | null } = {},
): string {
  const { city, lng, lat } = opts
  if (typeof lng === 'number' && typeof lat === 'number') {
    const params = new URLSearchParams({
      position: `${lng},${lat}`,
      name,
      src: SRC,
      // 明确告诉高德坐标是 GCJ-02（高德自己的坐标系），否则定位会偏
      coordinate: 'gaode',
    })
    return `https://uri.amap.com/marker?${params.toString()}`
  }

  const params = new URLSearchParams({ keyword: name, src: SRC })
  if (city) params.set('city', city)
  return `https://uri.amap.com/search?${params.toString()}`
}

/**
 * 可点击的地点名：点开在高德地图里看位置。
 *
 * 为什么值得做：行程里最常被追问的就是"这地方在哪、离下个点远不远"，
 * 让他自己复制地名再去地图 App 里搜，是典型的把成本丢给用户。
 *
 * 说明：链接会尝试拉起高德 App（未安装则打开网页版）。
 */
export default function MapLink({
  name,
  city,
  lng,
  lat,
  children,
  showIcon = true,
}: Props) {
  return (
    <a
      href={mapUrl(name, { city, lng, lat })}
      target="_blank"
      rel="noreferrer"
      className="jp-map-link"
      data-testid="map-link"
      title={`在高德地图中查看「${name}」`}
      // 卡片本体可能有自己的点击行为（跳详情等），别被这次点击连带触发
      onClick={(event) => event.stopPropagation()}
    >
      {showIcon && <EnvironmentOutlined style={{ fontSize: '0.85em', opacity: 0.7 }} />}
      <span>{children ?? name}</span>
    </a>
  )
}
