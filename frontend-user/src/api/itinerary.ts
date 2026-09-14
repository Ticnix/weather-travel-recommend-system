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
