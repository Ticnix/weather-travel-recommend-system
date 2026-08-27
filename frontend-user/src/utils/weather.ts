// 天气状态 → 展示信息（emoji + 中文标签 + 主题色）
// 供首页天气卡片、对话页等复用
export interface WeatherVisual {
  icon: string
  label: string
  color: string
}

const WEATHER_MAP: Record<string, WeatherVisual> = {
  晴: { icon: '☀️', label: '晴', color: '#faad14' },
  多云: { icon: '⛅', label: '多云', color: '#91caff' },
  阴: { icon: '☁️', label: '阴', color: '#8c8c8c' },
  小雨: { icon: '🌦️', label: '小雨', color: '#69b1ff' },
  中雨: { icon: '🌧️', label: '中雨', color: '#1677ff' },
  大雨: { icon: '🌧️', label: '大雨', color: '#0958d9' },
  雷阵雨: { icon: '⛈️', label: '雷阵雨', color: '#722ed1' },
  '雷阵雨伴冰雹': { icon: '⛈️', label: '雷阵雨伴冰雹', color: '#722ed1' },
  雪: { icon: '❄️', label: '雪', color: '#c5e0f7' },
  雾: { icon: '🌫️', label: '雾', color: '#bfbfbf' },
  霾: { icon: '🌫️', label: '霾', color: '#8c8c8c' },
}

// 根据 weather_desc（如"小雨"）或 weather_code 匹配视觉信息
export function getWeatherVisual(desc?: string | null): WeatherVisual {
  if (!desc) return { icon: '🌤️', label: '未知', color: '#8c8c8c' }
  // 尝试精确匹配
  for (const key of Object.keys(WEATHER_MAP)) {
    if (desc.includes(key)) return WEATHER_MAP[key]
  }
  return { icon: '🌤️', label: desc, color: '#8c8c8c' }
}

// 星期格式化
export function formatWeekday(dateStr?: string | null): string {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  const days = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
  return days[d.getDay()]
}
