/**
 * 从 axios 错误里取出「能直接给用户看」的原因。
 *
 * 后端所有面向用户的失败都放在 `detail` 里（配额用完、图片过大、出图 Key 被拒…），
 * 只有把它取出来展示，"失败"才对用户有信息量；否则一律显示"网络异常"，
 * 用户只能反复重试同一个必然失败的操作。
 */
export function apiErrorText(err: unknown, fallback = '网络异常'): string {
  const e = err as {
    response?: { data?: { detail?: unknown; message?: unknown } }
    message?: string
  }
  const detail = e?.response?.data?.detail ?? e?.response?.data?.message
  if (typeof detail === 'string' && detail.trim()) return detail
  return e?.message || fallback
}
