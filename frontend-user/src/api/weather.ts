import http from './http'

export interface CurrentWeather {
  location_code: string
  temperature: number | null
  feels_like: number | null
  humidity: number | null
  wind_speed: number | null
  wind_direction: string | null
  weather_code: string | null
  weather_desc: string | null
  precipitation: number | null
  visibility: number | null
  time?: string
}

export interface ForecastDay {
  date: string
  time?: string
  temp_max: number | null
  temp_min: number | null
  weather_desc: string | null
  weather_code: string | null
  precipitation: number | null
  is_forecast?: boolean
}

// ===== 区级天气（按用户所在区显示）=====

/** 后端解析出的位置依据：既用于取数，也用于向用户说明"这是哪里的天气" */
export interface LocalLocationInfo {
  city: string
  district: string | null
  lat: number
  lon: number
  source: 'geo' | 'manual' | 'city'
  /** district=区级精度 / city=只能到市中心 */
  precision: 'district' | 'city'
  label: string
  location_code: string
}

export interface LocalWeather {
  location: LocalLocationInfo
  current: CurrentWeather
  forecast: ForecastDay[]
}

/**
 * 取「用户所在区」的天气。
 *
 * 两种入参任选：坐标（浏览器定位，最准）或区名（手动选，也用于刷新时复现）。
 * 返回里的 `location.precision` 必须展示给用户——退到市中心时要说明，
 * 否则用户会以为这就是他家门口的温度。
 */
export async function getLocalWeather(params: {
  district?: string | null
  lat?: number
  lon?: number
}): Promise<LocalWeather> {
  return http.get('/weather/local', { params })
}

export interface DistrictOption {
  name: string
  /** 是否收录了区中心坐标：false 的区只能按市中心取数，选项上要标出来 */
  has_coords: boolean
}

/** 某城市可选的市辖区列表（供区域选择器使用） */
export async function listDistricts(city = '广州'): Promise<DistrictOption[]> {
  const res = (await http.get('/weather/districts', { params: { city } })) as unknown as {
    items: DistrictOption[]
  }
  return res?.items ?? []
}

// 获取最新实测天气
export async function getCurrentWeather(location = 'gz'): Promise<CurrentWeather | null> {
  return http.get('/weather/current', { params: { location } })
}

// 获取 7 天预报
export async function getForecast(location = 'gz'): Promise<{ items: ForecastDay[]; total: number }> {
  return http.get('/weather/forecast', { params: { location } })
}

// 获取最近 N 条实测记录（过去的天气）
export async function getHistory(
  limit = 30,
  location = 'gz',
): Promise<{ items: ForecastDay[]; total: number }> {
  return http.get('/weather/history', { params: { location, limit } })
}
