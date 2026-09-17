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
  request: { city: string; days: number; preferences: string[]; city_assumed: boolean }
  dates: string[]
  weather: Record<string, PlanWeather>
  plan: { city: string; days: number; summary: string; plan: PlanDay[] }
  /** 因天气做过的调整说明——必须展示给用户，静默改内容更让人困惑 */
  adjustments: string[]
}

/** 生成行程草案（只生成、不落库） */
export async function generateTripPlan(query: string): Promise<TripPlanResult> {
  return http.post('/recommend/plan', { query })
}

/** 批量保存行程（AI 排行程的一键保存） */
export async function saveItineraryBatch(
  items: ItineraryCreatePayload[],
): Promise<{ created: number; failed: string[] }> {
  return http.post('/itinerary/batch', { items })
}
