import http from './http'

// 候选地点（来自高德输入提示，含精确坐标）
export interface PlaceItem {
  name: string
  district?: string
  address?: string
  lng: number
  lat: number
}

interface PlaceListData {
  items: PlaceItem[]
  total: number
}

// 说明：axios 拦截器已在运行时把统一响应体解包成 data，
// 但类型层面仍是 AxiosResponse，这里用断言对齐（与项目其他 api 模块一致）
export async function suggestPlaces(keyword: string, city?: string): Promise<PlaceItem[]> {
  const res = (await http.get('/places/suggest', {
    params: { keyword, city: city ?? undefined },
  })) as unknown as PlaceListData
  return res?.items ?? []
}

// 常用地点（内置广州地标，零依赖兜底）
export async function listLandmarks(): Promise<PlaceItem[]> {
  const res = (await http.get('/places/landmarks')) as unknown as PlaceListData
  return res?.items ?? []
}
