import http from './http'

export interface HistoryRecord {
  time: string
  location_code: string
  temperature: number | null
  feels_like: number | null
  humidity: number | null
  pressure: number | null
  wind_speed: number | null
  wind_direction: string | null
  weather_code: string | null
  weather_desc: string | null
  precipitation: number | null
  visibility: number | null
  is_forecast: boolean
  temp_max?: number | null
  temp_min?: number | null
}

export interface PageResult<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface AdminListQuery {
  page?: number
  page_size?: number
  date_from?: string
  date_to?: string
  keyword?: string
  weather?: string
  forecast?: '' | 'true' | 'false'
}

// 管理端气象时序分页查询
export function adminList(params: AdminListQuery = {}): Promise<PageResult<HistoryRecord>> {
  return http.get('/weather/admin-list', { params: { page: 1, page_size: 20, ...params } })
}

// 手动同步
export function syncNow(): Promise<unknown> {
  return http.post('/weather/sync')
}

// 历史回补（同步过去 N 天）
export function syncHistory(days = 30): Promise<unknown> {
  return http.post(`/weather/sync-history?days=${days}`)
}

// 当前最新实测
export function currentWeather(): Promise<HistoryRecord | null> {
  return http.get('/weather/current')
}

// 7 天预报
export function forecast(): Promise<{ items: HistoryRecord[]; total: number }> {
  return http.get('/weather/forecast')
}

// 最近实测（history）
export function historyList(limit = 30): Promise<{ items: HistoryRecord[]; total: number }> {
  return http.get('/weather/history', { params: { limit } })
}

// 时序统计（按天聚合）
export interface DailyAgg {
  date: string
  temperature_avg: number | null
  humidity_avg: number | null
  precipitation_avg: number | null
}

export function weatherStats(days = 30): Promise<{ items: DailyAgg[]; total: number }> {
  return http.get('/weather/stats', { params: { days } })
}

// ---------------------------------------------------------------------------
// 时序分析（Day 42，读连续聚合 weather_daily）
// ---------------------------------------------------------------------------

/** 连续聚合产出的日行（比 DailyAgg 多了极值与累计降水） */
export interface DailyPoint {
  date: string
  temp_avg: number | null
  temp_max: number | null
  temp_min: number | null
  precip_sum: number | null
  humidity_avg: number | null
  /** 当日样本数：只有 1 个样本时，极值的代表性要打折 */
  samples: number
}

/** 同比 / 环比的区间汇总 */
export interface PeriodSummary {
  days: number
  samples: number
  temp_avg: number | null
  temp_max: number | null
  temp_min: number | null
  precip_total: number | null
  humidity_avg: number | null
}

export interface CompareResult {
  kind: 'yoy' | 'mom'
  kind_label: string
  location_code: string
  current_period: string
  previous_period: string
  current: PeriodSummary
  previous: PeriodSummary
  diff: {
    temp_avg: number | null
    temp_max: number | null
    precip_total: number | null
    humidity_avg: number | null
  }
  /** 本期进行中时已按相同天数对齐同期（口径可比） */
  aligned: boolean
  aligned_days: number | null
  available: boolean
  /** 任一侧无数据时的原因说明——绝不拿 0 充数 */
  reason: string
  verdict?: string
  sample_note?: string
}

/** 日粒度趋势序列（趋势图数据源） */
export function analysisDaily(days = 90, location = 'gz'): Promise<{ items: DailyPoint[]; total: number }> {
  return http.get('/weather/analysis/daily', { params: { days, location } })
}

/** 月度同比 / 环比 */
export function analysisCompare(
  kind: 'yoy' | 'mom',
  year?: number,
  month?: number,
  location = 'gz',
): Promise<CompareResult> {
  const params: Record<string, unknown> = { kind, location }
  if (year) params.year = year
  if (month) params.month = month
  return http.get('/weather/analysis/compare', { params })
}

/** 手动刷新连续聚合（回补历史后立即生效用） */
export function refreshAggregate(since?: string): Promise<{ refreshed: boolean }> {
  return http.post('/weather/analysis/refresh', { params: since ? { since } : {} })
}

/** 回补历史日统计（Open-Meteo 归档），同比需要去年同期数据 */
export function syncArchive(start: string, end: string, location = 'gz'): Promise<unknown> {
  return http.post('/weather/sync-archive', { params: { start, end, location } })
}
