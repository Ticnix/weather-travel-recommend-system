import http from './http'

// 行程笔记（自由格式的 Markdown 文档：攻略 / 清单 / 备忘）
export interface NoteItem {
  id: number
  title: string
  content: string // Markdown 正文
  note_date: string | null
  location: string | null
  created_at: string
  updated_at: string
}

export interface NotePayload {
  title: string
  content: string
  note_date?: string | null
  location?: string | null
}

interface NoteListData {
  items: NoteItem[]
  total: number
}

// 列表（keyword 同时匹配标题与正文）
export async function listNotes(keyword?: string): Promise<NoteListData> {
  const res = (await http.get('/notes', {
    params: keyword ? { keyword } : {},
  })) as unknown as NoteListData
  return res ?? { items: [], total: 0 }
}

export async function getNote(id: number): Promise<NoteItem> {
  return http.get(`/notes/${id}`)
}

export async function createNote(payload: NotePayload): Promise<NoteItem> {
  return http.post('/notes', payload)
}

export async function updateNote(id: number, payload: Partial<NotePayload>): Promise<NoteItem> {
  return http.put(`/notes/${id}`, payload)
}

export async function deleteNote(id: number): Promise<{ deleted: number }> {
  return http.delete(`/notes/${id}`)
}

// 上传文件导入（.md / .txt 单篇；.json 支持批量）
export async function importNoteFile(file: File): Promise<{ created: number; titles: string[] }> {
  const form = new FormData()
  form.append('file', file)
  return http.post('/notes/import', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

// 粘贴文本导入（标题可空，后端自动推断）
export async function importNoteText(payload: {
  title?: string
  content: string
  note_date?: string | null
  location?: string | null
}): Promise<NoteItem> {
  return http.post('/notes/import-text', payload)
}

// 导出单篇为 .md（浏览器下载）
export async function exportNoteMd(id: number): Promise<Blob> {
  return (await http.get(`/notes/${id}/export`, {
    responseType: 'blob',
  })) as unknown as Blob
}

// 导出全部为 JSON（可再次导入）
export async function exportAllNotes(): Promise<unknown[]> {
  return (await http.get('/notes/export/all')) as unknown as unknown[]
}
