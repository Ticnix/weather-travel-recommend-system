/**
 * 用户偏好 API（Day 55 后端 + Day 56 前端）。
 *
 * **PUT 是整体替换**（后端 schema 的既定语义）：前端每次提交完整表单，
 * 「一键清空」就是把默认值整体 PUT 回去——不需要额外的 DELETE 接口。
 */

import http from './http'

export interface UserPreferenceData {
  sun_sensitive: boolean
  cold_sensitive: boolean
  with_elderly: boolean
  with_children: boolean
  with_pet: boolean
  prefer_outdoor: boolean
  prefer_indoor: boolean
  prefer_photo: boolean
  prefer_food: boolean
  budget_low: boolean
  /** 主要通勤方式（地铁/自驾/步行…）；空串 = 未设置 */
  commute: string
  /** 忌口 / 饮食注意；空串 = 未设置 */
  diet: string
}

/** 全默认值：首次打开表单、以及「一键清空」都用它 */
export const PREFERENCE_DEFAULTS: UserPreferenceData = {
  sun_sensitive: false,
  cold_sensitive: false,
  with_elderly: false,
  with_children: false,
  with_pet: false,
  prefer_outdoor: false,
  prefer_indoor: false,
  prefer_photo: false,
  prefer_food: false,
  budget_low: false,
  commute: '',
  diet: '',
}

/** 读取偏好；后端对未设置过的用户返回全默认，这里再兜一层底。
 *
 * ⚠️ 响应拦截器（api/http.ts）已经解包过 `{code, message, data}`，
 * `res` **就是偏好本体**——再取 `res.data` 永远是 undefined，
 * 表现成"保存成功、一刷新就回到默认"（实测踩过：保存其实进了库，
 * 是前端读回来时被默认值覆盖）。
 */
export async function getMyPreferences(): Promise<UserPreferenceData> {
  const res = (await http.get('/users/me/preferences')) as UserPreferenceData | null
  return { ...PREFERENCE_DEFAULTS, ...(res ?? {}) }
}

/** 保存偏好（整体替换）。返回保存后的完整数据，便于服务端裁剪后回显 */
export async function updateMyPreferences(
  data: UserPreferenceData,
): Promise<UserPreferenceData> {
  const res = (await http.put('/users/me/preferences', data)) as UserPreferenceData | null
  return { ...PREFERENCE_DEFAULTS, ...(res ?? data) }
}
