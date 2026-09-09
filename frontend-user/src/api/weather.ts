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
