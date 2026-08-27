import type { WeatherType } from '../components/three/effects/weatherParticles'

// 天气描述 → 3D 场景天气类型
export function mapWeatherType(desc?: string | null): WeatherType {
  if (!desc) return 'unknown'
  if (desc.includes('雨') || desc.includes('雷')) return 'rain'
  if (desc.includes('雾') || desc.includes('霾')) return 'fog'
  if (desc.includes('多云') || desc.includes('阴')) return 'cloudy'
  if (desc.includes('晴')) return 'sunny'
  // 温度高温判断在页面层处理，这里返回 sunny 兜底
  return 'sunny'
}

// 天气类型中文标签
export const WEATHER_TYPE_LABEL: Record<WeatherType, string> = {
  sunny: '晴天',
  rain: '雨天',
  cloudy: '多云',
  fog: '雾天',
  hot: '高温',
  unknown: '未知',
}
