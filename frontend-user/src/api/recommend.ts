import http from './http'

// ===== 出行规划推荐 =====
export interface TravelRoute {
  mode: string // 驾车 / 地铁/公交 / 骑行 / 步行
  duration_min: number
  distance_km: number
  cost: number
  detail: string
  time_score?: number
  cost_score?: number
  weather_score?: number
  total_score?: number
}

export interface TravelWeather {
  desc: string
  temp_min: number | null
  temp_max: number | null
  precip: number | null
}

export interface TravelResult {
  origin: string
  destination: string
  weather: TravelWeather
  routes: TravelRoute[]
  error?: string
  hint?: string
}

export async function recommendTravel(
  origin: string,
  destination: string,
  city?: string,
): Promise<TravelResult> {
  return http.get('/recommend/travel', {
    params: { origin, destination, city: city ?? undefined },
  })
}

// ===== 穿搭推荐 =====
export interface OutfitResult {
  city: string
  weather: { desc: string; temp: number; precip: number }
  scene: string | null
  preference: string | null
  temp_rule: string | null
  rules: string[]
  preference_rule: string | null
  knowledge: string
  suggestion: string
}

export async function recommendOutfit(
  city?: string,
  scene?: string,
  preference?: string,
): Promise<OutfitResult> {
  return http.get('/recommend/outfit', {
    params: {
      city: city ?? undefined,
      scene: scene ?? undefined,
      preference: preference ?? undefined,
    },
  })
}

// ===== 今日天气概要（推荐页标题用） =====
export interface WeatherHead {
  temperature: number | null
  desc: string | null
  feels_like: number | null
  humidity: number | null
  temp_min: number | null
  temp_max: number | null
}

export async function getWeatherHead(city?: string): Promise<WeatherHead> {
  return http.get('/recommend/weather-head', {
    params: { city: city ?? undefined },
  })
}
