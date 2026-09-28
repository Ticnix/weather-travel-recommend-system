import { useEffect, useState } from 'react'

/** 与 CSS 里的断点保持一致（见 jp-clean.css 的 @media (max-width: 767px)） */
export const MOBILE_QUERY = '(max-width: 767px)'

/**
 * 是否窄屏（手机）。
 *
 * 有些适配必须换结构而不只是改字号——比如三列排成一行、桌面用横向导航手机要换底部导航。
 * 这类只能由 JS 判断；能用 CSS 解决的（留白、字号、隐藏次要文案）就别用它，
 * 否则白白多一次渲染。
 *
 * 初始值直接读 matchMedia（而不是等 effect 测量），避免首屏先按桌面渲染再"跳"成手机布局。
 */
export function useIsMobile(): boolean {
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== 'undefined' && window.matchMedia(MOBILE_QUERY).matches,
  )

  useEffect(() => {
    const mql = window.matchMedia(MOBILE_QUERY)
    const onChange = (event: MediaQueryListEvent) => setIsMobile(event.matches)
    mql.addEventListener('change', onChange)
    setIsMobile(mql.matches)
    return () => mql.removeEventListener('change', onChange)
  }, [])

  return isMobile
}

export default useIsMobile
