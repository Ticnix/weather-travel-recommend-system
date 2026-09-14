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
//
// 复合描述（「中雨转小雨」「晴间多云」「雷阵雨伴冰雹」）会同时包含多个关键词，
// 因此不能简单地"谁先声明用谁"，规则是：
//   1. **出现位置最靠前**的优先（复合天气以先出现的为主）
//   2. 位置相同时，**更长的关键词**优先（更具体的描述不该被宽泛描述抢走）
// 例：
//   「中雨转小雨」  → 中雨(位置0) vs 小雨(位置3)  → 中雨
//   「雷阵雨伴冰雹」→ 雷阵雨(位置0) vs 雷阵雨伴冰雹(位置0) → 取更长的「雷阵雨伴冰雹」
export function getWeatherVisual(desc?: string | null): WeatherVisual {
  if (!desc) return { icon: '🌤️', label: '未知', color: '#8c8c8c' }

  let bestKey: string | null = null
  let bestIndex = Number.POSITIVE_INFINITY
  for (const key of Object.keys(WEATHER_MAP)) {
    const idx = desc.indexOf(key)
    if (idx === -1) continue
    const longer = key.length > (bestKey?.length ?? 0)
    if (idx < bestIndex || (idx === bestIndex && longer)) {
      bestKey = key
      bestIndex = idx
    }
  }
  return bestKey ? WEATHER_MAP[bestKey] : { icon: '🌤️', label: desc, color: '#8c8c8c' }
}

// 星期格式化
export function formatWeekday(dateStr?: string | null): string {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  const days = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
  return days[d.getDay()]
}
