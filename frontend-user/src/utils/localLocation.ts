import { useEffect, useState } from 'react'

/**
 * 「按哪个区的天气」这份状态：存在哪、怎么通知。
 *
 * 为什么不放 React Context：首页的天气卡（WeatherHero）与天气时间轴（ForecastList）
 * 都要用它，但它们不在同一棵子树里，为一份状态加一层 Provider 会把 App 的组件树改复杂。
 * 用 localStorage + 自定义事件，读写各几行，刷新页面也不丢。
 */
export interface LocalLocation {
  city: string
  /** 区名（如「南沙区」）；只有城市精度时为 null */
  district: string | null
  lat: number
  lon: number
  /** 依据来源：geo=浏览器定位 / manual=手动选 / city=默认城市中心 */
  source: 'geo' | 'manual' | 'city'
  /** district=区级精度 / city=只能到市中心（必须如实告诉用户，别让他以为这是家门口的天气） */
  precision: 'district' | 'city'
  /** 给用户看的一句话依据，如「广州市 · 南沙区」 */
  label: string
}

const STORAGE_KEY = 'wt_location'
const CHANGE_EVENT = 'wt-location-change'

export function getLocalLocation(): LocalLocation | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as LocalLocation) : null
  } catch {
    // 存的是坏 JSON 或隐私模式禁用了 localStorage
    return null
  }
}

export function setLocalLocation(value: LocalLocation | null): void {
  try {
    if (value) localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
    else localStorage.removeItem(STORAGE_KEY)
  } catch {
    /* 写不进去就算了：本次会话内仍能通过事件让组件刷新 */
  }
  window.dispatchEvent(new Event(CHANGE_EVENT))
}

/** 订阅位置变化，返回取消订阅函数 */
export function subscribeLocation(callback: () => void): () => void {
  window.addEventListener(CHANGE_EVENT, callback)
  return () => window.removeEventListener(CHANGE_EVENT, callback)
}

/** 浏览器定位是否可用（需要 HTTPS 或 localhost） */
export function geoAvailable(): boolean {
  return typeof navigator !== 'undefined' && 'geolocation' in navigator
}

/**
 * 取一次当前坐标。
 *
 * 失败/被拒绝/超时都返回 null 而不是抛异常：定位只是**锦上添花**，
 * 拿不到就退到"用户手动选"或"城市中心"，绝不能因此让天气卡变成错误态。
 */
export function requestPosition(timeout = 8000): Promise<{ lat: number; lon: number } | null> {
  return new Promise((resolve) => {
    if (!geoAvailable()) {
      resolve(null)
      return
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
      () => resolve(null),
      {
        enableHighAccuracy: false, // 区级粒度不需要 GPS 级精度，省电、出结果也快
        timeout,
        maximumAge: 10 * 60 * 1000, // 10 分钟内的缓存坐标够用
      },
    )
  })
}

/** 当前生效的位置（null = 还没选过，按默认城市中心展示） */
export function useLocalLocation(): LocalLocation | null {
  const [state, setState] = useState<LocalLocation | null>(() => getLocalLocation())

  useEffect(() => {
    setState(getLocalLocation())
    return subscribeLocation(() => setState(getLocalLocation()))
  }, [])

  return state
}
