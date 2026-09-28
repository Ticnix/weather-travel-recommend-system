import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import MapLink, { mapUrl } from './MapLink'

/**
 * 这里只测一件事：**链接拼得对不对**。
 * 拼错了用户点开是空地图，而页面上完全看不出来，所以必须锁死。
 */
describe('mapUrl', () => {
  it('有坐标时钉到具体位置', () => {
    const url = mapUrl('白云山', { lng: 113.2987, lat: 23.186 })

    expect(url).toContain('uri.amap.com/marker')
    expect(url).toContain('position=113.2987%2C23.186')
    // 必须声明坐标系：不声明会按 WGS-84 解释，定位会偏几百米
    expect(url).toContain('coordinate=gaode')
  })

  it('没有坐标时按地名搜索，并带上城市限定范围', () => {
    const url = mapUrl('北京路', { city: '广州' })

    expect(url).toContain('uri.amap.com/search')
    expect(url).toContain('keyword=%E5%8C%97%E4%BA%AC%E8%B7%AF')
    expect(url).toContain('city=%E5%B9%BF%E5%B7%9E')
  })

  it('只有一半坐标时退回搜索，不硬拼一个错位置', () => {
    expect(mapUrl('广州塔', { lng: 113.32, lat: null })).toContain('uri.amap.com/search')
  })
})

describe('MapLink', () => {
  it('渲染成新窗口打开的地图链接', () => {
    render(<MapLink name="广州塔" city="广州" />)

    const link = screen.getByTestId('map-link')
    expect(link).toHaveAttribute('href', expect.stringContaining('uri.amap.com'))
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noreferrer')
    expect(link).toHaveTextContent('广州塔')
  })

  it('可以自定义显示文案（地点名仍用于搜索）', () => {
    render(
      <MapLink name="广州塔" lng={113.3245} lat={23.1065}>
        小蛮腰
      </MapLink>,
    )

    const link = screen.getByTestId('map-link')
    expect(link).toHaveTextContent('小蛮腰')
    expect(link).toHaveAttribute('href', expect.stringContaining('113.3245'))
  })
})
