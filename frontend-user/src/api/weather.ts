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
  temp_max: number | null
  temp_min: number | null
  weather_desc: string | null
  weather_code: string | null
  precipitation: number | null
}

// 获取最新实测天气
export async function getCurrentWeather(location = 'gz'): Promise<CurrentWeather | null> {
  return http.get('/weather/current', { params: { location } })
}

// 获取 7 天预报
export async function getForecast(location = 'gz'): Promise<{ items: ForecastDay[]; total: number }> {
  return http.get('/weather/forecast', { params: { location } })
}
