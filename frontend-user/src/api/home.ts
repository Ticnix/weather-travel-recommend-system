import http from './http'

// 首页聚合数据：天气 + 今日提醒 + 穿搭建议 + 近期行程（含天气提醒）

export interface HomeTip {
  icon: string
  level: 'info' | 'warning' | 'danger'
  title: string
  text: string
}

export interface HomeWeather {
  city?: string
  desc?: string | null
  temperature?: number | null
  feels_like?: number | null
  humidity?: number | null
  temp_min?: number | null
  temp_max?: number | null
  precip?: number | null
}

export interface HomeOutfit {
  suggestion: string
  rules: string[]
  temp_rule?: string | null
}

export interface HomeItineraryItem {
  id: number
  title: string
  date: string
  start_time: string | null
  location: string | null
  activity: string | null
  city: string
  weather_hint: string
}

export interface HomeDashboard {
  city: string
  date: string
  weather: HomeWeather
  tips: HomeTip[]
  outfit: HomeOutfit | null
  itinerary: { upcoming: HomeItineraryItem[]; total: number }
  logged_in: boolean
}

export async function getDashboard(city?: string): Promise<HomeDashboard> {
  const res = (await http.get('/home/dashboard', {
    params: { city: city ?? undefined },
  })) as unknown as HomeDashboard
  return res
}
