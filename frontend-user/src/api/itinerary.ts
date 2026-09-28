import http from './http'

export interface ItineraryItem {
  id: number
  title: string
  date: string // YYYY-MM-DD
  start_time: string | null
  location: string | null
  activity: string | null
  note?: string | null
}

export interface ItineraryCreatePayload {
  title: string
  date: string
  start_time?: string
  location?: string
  activity?: string
  note?: string
}

// 查询本人行程（可按日期过滤）
export async function listItinerary(date?: string): Promise<{ items: ItineraryItem[]; total: number }> {
  return http.get('/itinerary', { params: date ? { date } : {} })
}

// 新增行程
export async function createItinerary(payload: ItineraryCreatePayload): Promise<ItineraryItem> {
  return http.post('/itinerary', payload)
}

// 更新行程（只提交需要改的字段）
export async function updateItinerary(
  id: number,
  payload: Partial<ItineraryCreatePayload>,
): Promise<ItineraryItem> {
  return http.put(`/itinerary/${id}`, payload)
}

// 删除行程
export async function deleteItinerary(id: number): Promise<{ deleted: number }> {
  return http.delete(`/itinerary/${id}`)
}

// ===== AI 一键排行程（Day 40）=====

export interface PlanItem {
  time: string
  title: string
  activity: string
  reason: string
  /** 是否因天气被审计步骤调整过（前端要标出来） */
  weather_adjusted: boolean
  /** 坐标（后端从候选 POI 反查得到，非模型生成）；缺省时地图链接退回按地名搜索 */
  lng?: number | null
  lat?: number | null
}

export interface PlanDay {
  date: string
  weather: string
  weather_note: string
  items: PlanItem[]
}

export interface PlanWeather {
  desc?: string
  precip?: number
  temp_max?: number
  temp_min?: number
  needs_indoor?: boolean
}

export interface TripPlanResult {
  request: {
    city: string
    days: number
    preferences: string[]
    city_assumed: boolean
    /** 解析出的出发日期（YYYY-MM-DD）；需求里没写日期时为 null（即从今天起算） */
    start_date: string | null
    /** 命中的日期原词（如「国庆」），用于向用户说明排程依据 */
    date_hint: string | null
    /** 需求里写的市辖区（如「南沙区」）；没写区域时为 null */
    area: string | null
    /** 命中的区域原词（如「南沙」） */
    area_hint: string | null
  }
  dates: string[]
  weather: Record<string, PlanWeather>
  /** 日期超出预报范围时的说明；预报齐全时为 null */
  weather_hint: string | null
  /** 区域没检索到候选地点（已回落全城）时的说明；正常命中时为 null */
  area_note: string | null
  plan: { city: string; days: number; summary: string; plan: PlanDay[] }
  /** 因天气做过的调整说明——必须展示给用户，静默改内容更让人困惑 */
  adjustments: string[]
}

/** 生成行程草案（只生成、不落库） */
export async function generateTripPlan(query: string): Promise<TripPlanResult> {
  // 单独放宽超时：这里要等大模型把整份行程写完，
  // 长假（国庆 7 天 / 春节 8 天）的输出量远超默认 30s 能覆盖的范围
  return http.post('/recommend/plan', { query }, { timeout: 120000 })
}

/** 批量保存行程（AI 排行程的一键保存） */
export async function saveItineraryBatch(
  items: ItineraryCreatePayload[],
): Promise<{ created: number; failed: string[] }> {
  return http.post('/itinerary/batch', { items })
}

// ===== 行程天气风险（Day 52）=====

/** 一条"行程 × 预报"冲突。与定时预警**同一套规则**（后端 itinerary_risk），
 *  所以页面上标出来的和推送里说的必然一致。 */
export interface ItineraryRisk {
  itinerary_id: number
  date: string
  kind: 'rain' | 'wind' | 'heat' | 'drop'
  level: 'warn' | 'danger'
  reason: string
  /** 可直接展示的标题与正文（含改期建议） */
  title: string
  body: string
}

export interface ItineraryRisks {
  items: ItineraryRisk[]
  /** 以行程 id 为键，前端每条直接查表；JSON 的键是字符串 */
  by_itinerary: Record<string, ItineraryRisk>
  total: number
}

export async function listItineraryRisks(): Promise<ItineraryRisks> {
  const res = (await http.get('/itinerary/risks')) as unknown as ItineraryRisks
  return res ?? { items: [], by_itinerary: {}, total: 0 }
}

/**
 * 导出 .ics 到系统日历（Day 53）。
 *
 * 用 fetch 而不是 axios 实例：全局响应拦截器按「code/message/data」解包，
 * 日历文件是**纯文本**，走它会当成非法响应。token 从 localStorage 取（与 auth.ts 一致）。
 */
export async function downloadItineraryIcs(): Promise<void> {
  const token = localStorage.getItem('wt_token')
  const res = await fetch('/api/v1/itinerary/export.ics', {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  })
  if (!res.ok) throw new Error('导出失败，请稍后重试')
  const text = await res.text()
  const blob = new Blob([text], { type: 'text/calendar;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = '我的行程.ics'
  a.click()
  URL.revokeObjectURL(url)
}
