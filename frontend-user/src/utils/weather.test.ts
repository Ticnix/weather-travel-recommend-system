import { describe, expect, it } from 'vitest'
import { formatWeekday, getWeatherVisual } from './weather'

describe('getWeatherVisual', () => {
  it('常见天气能精确匹配', () => {
    expect(getWeatherVisual('晴').label).toBe('晴')
    expect(getWeatherVisual('多云').icon).toBe('⛅')
    expect(getWeatherVisual('中雨').label).toBe('中雨')
    expect(getWeatherVisual('雪').icon).toBe('❄️')
  })

  it('空值统一返回「未知」而不是抛错', () => {
    expect(getWeatherVisual(null).label).toBe('未知')
    expect(getWeatherVisual(undefined).label).toBe('未知')
    expect(getWeatherVisual('').label).toBe('未知')
  })

  it('复合描述能被基础天气命中', () => {
    expect(getWeatherVisual('晴间多云').label).toBe('晴')
    expect(getWeatherVisual('中雨转小雨').label).toBe('中雨')
  })

  it('更具体的描述不会被宽泛描述抢走', () => {
    // 「雷阵雨伴冰雹」既包含「雷阵雨」，也是它自己。
    // 若按字典声明顺序匹配，「雷阵雨」会先命中，label 就退化成了「雷阵雨」。
    expect(getWeatherVisual('雷阵雨伴冰雹').label).toBe('雷阵雨伴冰雹')
  })

  it('未收录的天气原样返回描述并使用兜底图标', () => {
    const visual = getWeatherVisual('沙尘暴')
    expect(visual.label).toBe('沙尘暴')
    expect(visual.icon).toBe('🌤️')
  })

  it('每种天气都配了图标与颜色', () => {
    const descs = ['晴', '多云', '阴', '小雨', '中雨', '大雨', '雷阵雨', '雪', '雾', '霾']
    for (const desc of descs) {
      const visual = getWeatherVisual(desc)
      expect(visual.icon, `${desc} 缺少图标`).toBeTruthy()
      expect(visual.color, `${desc} 缺少颜色`).toMatch(/^#/)
    }
  })
})

describe('formatWeekday', () => {
  // 注意：断言依赖运行环境时区为东八区（本地开发与 CI 均为 UTC+8）
  it('把日期转成中文星期', () => {
    expect(formatWeekday('2026-09-14')).toBe('周一')
    expect(formatWeekday('2026-09-19')).toBe('周六')
    expect(formatWeekday('2026-09-20')).toBe('周日')
  })

  it('空值返回空字符串', () => {
    expect(formatWeekday(null)).toBe('')
    expect(formatWeekday(undefined)).toBe('')
    expect(formatWeekday('')).toBe('')
  })

  it('返回值只会是七个星期之一', () => {
    const week = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
    expect(week).toContain(formatWeekday('2026-09-14'))
  })
})
