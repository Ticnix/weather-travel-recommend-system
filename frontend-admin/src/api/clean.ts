import http from './http'

export interface CleanTaskItem {
  task_id: string
  filename: string
  status: 'pending' | 'running' | 'success' | 'failed'
  total_rows: number | null
  cleaned_rows: number | null
  duplicated_removed: number | null
  filled_missing: number | null
  filtered_outliers: number | null
  unit_standardized: number | null
  error: string | null
  triggered_by: string | null
  created_at: string
  updated_at: string
}

export interface CleanTaskDetail extends CleanTaskItem {
  log: string | null
}

export function listCleanTasks(limit = 20): Promise<{ items: CleanTaskItem[]; total: number }> {
  return http.get('/clean', { params: { limit } })
}

export function getCleanTask(taskId: string): Promise<CleanTaskDetail> {
  return http.get(`/clean/${taskId}`)
}

// 上传 CSV 触发清洗（FormData）
export function uploadCsv(file: File): Promise<{ task_id: string; filename: string; status: string }> {
  const fd = new FormData()
  fd.append('file', file)
  return http.post('/clean/upload', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

// 下载清洗后 CSV（用带鉴权 header 的 axios blob）
export async function downloadClean(taskId: string, filename: string): Promise<void> {
  const resp = await http.get(`/clean/${taskId}/download`, { responseType: 'blob' })
  const blob = resp as unknown as Blob
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename || `cleaned_${taskId}.csv`
  a.click()
  URL.revokeObjectURL(url)
}
