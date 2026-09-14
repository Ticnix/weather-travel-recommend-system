import { useCallback, useEffect, useState } from 'react'
import {
  Button,
  DatePicker,
  Empty,
  Input,
  Modal,
  Popconfirm,
  Skeleton,
  Space,
  Tabs,
  Tag,
  Typography,
  Upload,
  message,
} from 'antd'
import {
  CalendarOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  EnvironmentOutlined,
  ExportOutlined,
  PlusOutlined,
  SearchOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import MDEditor from '@uiw/react-md-editor'
import '@uiw/react-md-editor/markdown-editor.css'
import '@uiw/react-markdown-preview/markdown.css'
import dayjs, { type Dayjs } from 'dayjs'
import {
  createNote,
  deleteNote,
  exportAllNotes,
  exportNoteMd,
  importNoteFile,
  importNoteText,
  listNotes,
  updateNote,
  type NoteItem,
} from '../api/notes'

const { Text, Paragraph } = Typography

// 正文预览：去掉 Markdown 标记，取前 N 字
function preview(content: string, len = 140): string {
  const plain = (content || '')
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/[#>*`\-|]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  return plain.length > len ? `${plain.slice(0, len)}…` : plain
}

// 触发浏览器下载
function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export default function NotePanel() {
  const [items, setItems] = useState<NoteItem[]>([])
  const [loading, setLoading] = useState(true)
  const [keyword, setKeyword] = useState('')

  // 编辑器状态
  const [editorOpen, setEditorOpen] = useState(false)
  const [editing, setEditing] = useState<NoteItem | null>(null)
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [noteDate, setNoteDate] = useState<Dayjs | null>(null)
  const [location, setLocation] = useState('')
  const [saving, setSaving] = useState(false)

  // 导入弹窗
  const [importOpen, setImportOpen] = useState(false)
  const [pasteTitle, setPasteTitle] = useState('')
  const [pasteContent, setPasteContent] = useState('')
  const [importing, setImporting] = useState(false)

  const load = useCallback(async (kw?: string) => {
    setLoading(true)
    try {
      const res = await listNotes(kw)
      setItems(res.items)
    } catch {
      /* 失败提示已由 http 拦截器统一处理 */
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const openCreate = () => {
    setEditing(null)
    setTitle('')
    setContent('')
    setNoteDate(null)
    setLocation('')
    setEditorOpen(true)
  }

  const openEdit = (n: NoteItem) => {
    setEditing(n)
    setTitle(n.title)
    setContent(n.content || '')
    setNoteDate(n.note_date ? dayjs(n.note_date) : null)
    setLocation(n.location ?? '')
    setEditorOpen(true)
  }

  const handleSave = async () => {
    if (!title.trim()) {
      message.warning('请填写笔记标题')
      return
    }
    setSaving(true)
    try {
      const payload = {
        title: title.trim(),
        content,
        note_date: noteDate ? noteDate.format('YYYY-MM-DD') : null,
        location: location.trim() || null,
      }
      if (editing) {
        await updateNote(editing.id, payload)
        message.success('已保存')
      } else {
        await createNote(payload)
        message.success('笔记已创建')
      }
      setEditorOpen(false)
      await load(keyword)
    } catch {
      /* 拦截器已提示 */
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await deleteNote(id)
      message.success('已删除')
      await load(keyword)
    } catch {
      /* 拦截器已提示 */
    }
  }

  const handleExportMd = async (n: NoteItem) => {
    try {
      const blob = await exportNoteMd(n.id)
      downloadBlob(new Blob([blob], { type: 'text/markdown;charset=utf-8' }), `${n.title}.md`)
    } catch {
      message.error('导出失败')
    }
  }

  const handleExportAll = async () => {
    try {
      const data = await exportAllNotes()
      downloadBlob(
        new Blob([JSON.stringify(data, null, 2)], { type: 'application/json;charset=utf-8' }),
        `行程笔记备份-${dayjs().format('YYYYMMDD')}.json`,
      )
    } catch {
      message.error('导出失败')
    }
  }

  const handleImportFile = async (file: File) => {
    setImporting(true)
    try {
      const res = await importNoteFile(file)
      message.success(`导入成功，新增 ${res?.created ?? 0} 篇笔记`)
      setImportOpen(false)
      await load(keyword)
    } catch {
      /* 拦截器已提示 */
    } finally {
      setImporting(false)
    }
  }

  const handlePasteImport = async () => {
    if (!pasteContent.trim()) {
      message.warning('请粘贴笔记内容')
      return
    }
    setImporting(true)
    try {
      await importNoteText({ title: pasteTitle.trim() || undefined, content: pasteContent })
      message.success('已导入 1 篇笔记')
      setPasteTitle('')
      setPasteContent('')
      setImportOpen(false)
      await load(keyword)
    } catch {
      /* 拦截器已提示 */
    } finally {
      setImporting(false)
    }
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      {/* 工具条 */}
      <div className="jp-card" style={{ padding: '14px 18px' }}>
        <div
          style={{
            display: 'flex',
            gap: 10,
            alignItems: 'center',
            flexWrap: 'wrap',
            justifyContent: 'space-between',
          }}
        >
          <Input
            allowClear
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onPressEnter={() => load(keyword)}
            prefix={<SearchOutlined style={{ color: 'var(--jp-ink-3)' }} />}
            placeholder="搜索标题或正文"
            style={{ maxWidth: 280 }}
          />
          <Space wrap>
            <Button icon={<ExportOutlined />} onClick={handleExportAll} disabled={!items.length}>
              导出全部
            </Button>
            <Button icon={<UploadOutlined />} onClick={() => setImportOpen(true)}>
              导入笔记
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              新建笔记
            </Button>
          </Space>
        </div>
      </div>

      {/* 列表 */}
      {loading ? (
        <div className="jp-card" style={{ padding: 24 }}>
          <Skeleton active paragraph={{ rows: 4 }} />
        </div>
      ) : items.length === 0 ? (
        <div className="jp-card" style={{ padding: '40px 20px' }}>
          <Empty description="还没有笔记，点「新建笔记」写一篇攻略，或从文件导入" />
        </div>
      ) : (
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          {items.map((n) => (
            <div key={n.id} className="jp-card" style={{ padding: 18 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <Space size={8} wrap>
                    <span
                      className="jp-serif"
                      style={{ fontSize: 16, fontWeight: 600, color: 'var(--jp-ink)' }}
                    >
                      {n.title}
                    </span>
                    {n.note_date && (
                      <Tag color="blue" icon={<CalendarOutlined />}>
                        {n.note_date}
                      </Tag>
                    )}
                    {n.location && (
                      <Tag icon={<EnvironmentOutlined />}>{n.location}</Tag>
                    )}
                  </Space>
                  <Paragraph
                    style={{ margin: '8px 0 0', color: 'var(--jp-ink-2)', fontSize: 13 }}
                    ellipsis={{ rows: 2 }}
                  >
                    {preview(n.content) || '（空笔记）'}
                  </Paragraph>
                  <Text style={{ color: 'var(--jp-ink-3)', fontSize: 12 }}>
                    更新于 {dayjs(n.updated_at).format('YYYY-MM-DD HH:mm')}
                  </Text>
                </div>
                <Space direction="vertical" size={4}>
                  <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(n)}>
                    编辑
                  </Button>
                  <Button
                    size="small"
                    icon={<DownloadOutlined />}
                    onClick={() => handleExportMd(n)}
                  >
                    导出
                  </Button>
                  <Popconfirm title="确定删除这篇笔记？" onConfirm={() => handleDelete(n.id)}>
                    <Button size="small" danger icon={<DeleteOutlined />}>
                      删除
                    </Button>
                  </Popconfirm>
                </Space>
              </div>
            </div>
          ))}
        </Space>
      )}

      {/* 编辑器弹窗 */}
      <Modal
        title={editing ? '编辑笔记' : '新建笔记'}
        open={editorOpen}
        onCancel={() => setEditorOpen(false)}
        onOk={handleSave}
        confirmLoading={saving}
        okText="保存"
        cancelText="取消"
        width={1020}
        style={{ top: 24 }}
        destroyOnHidden
      >
        <Space direction="vertical" size={10} style={{ width: '100%' }}>
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="笔记标题，如：广州三天两夜攻略"
            maxLength={255}
          />
          <Space wrap size={10}>
            <DatePicker
              value={noteDate}
              onChange={(d) => setNoteDate(d)}
              placeholder="关联日期（可选）"
            />
            <Input
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="关联地点（可选），如 广州"
              maxLength={128}
              style={{ width: 240 }}
            />
          </Space>
          {/* Markdown 编辑器：左写右预览，工具栏支持标题/加粗/列表/链接等 */}
          <div data-color-mode="light">
            <MDEditor
              value={content}
              onChange={(v) => setContent(v ?? '')}
              height={430}
              preview="live"
              textareaProps={{ placeholder: '用 Markdown 记录行程…支持 # 标题、- 列表、**加粗**、表格等' }}
            />
          </div>
          <Text style={{ color: 'var(--jp-ink-3)', fontSize: 12 }}>
            提示：Markdown 语法可被 AI 直接理解，之后也可以让 AI 基于这篇笔记帮你排行程。
          </Text>
        </Space>
      </Modal>

      {/* 导入弹窗 */}
      <Modal
        title="导入笔记"
        open={importOpen}
        onCancel={() => setImportOpen(false)}
        footer={null}
        width={720}
      >
        <Tabs
          items={[
            {
              key: 'file',
              label: '上传文件',
              children: (
                <Space direction="vertical" size={12} style={{ width: '100%' }}>
                  <Text style={{ color: 'var(--jp-ink-2)', fontSize: 13 }}>
                    支持 <Text code>.md</Text> / <Text code>.txt</Text>（整篇作为一篇笔记）
                    与 <Text code>.json</Text>（可批量，兼容「导出全部」的格式）。
                  </Text>
                  <Upload
                    accept=".md,.txt,.json"
                    showUploadList={false}
                    beforeUpload={(file) => {
                      handleImportFile(file as unknown as File)
                      return false
                    }}
                  >
                    <Button type="primary" icon={<UploadOutlined />} loading={importing}>
                      选择文件
                    </Button>
                  </Upload>
                </Space>
              ),
            },
            {
              key: 'paste',
              label: '粘贴文本',
              children: (
                <Space direction="vertical" size={10} style={{ width: '100%' }}>
                  <Input
                    value={pasteTitle}
                    onChange={(e) => setPasteTitle(e.target.value)}
                    placeholder="标题（留空则自动从正文首行推断）"
                    maxLength={255}
                  />
                  <Input.TextArea
                    value={pasteContent}
                    onChange={(e) => setPasteContent(e.target.value)}
                    rows={10}
                    placeholder={'把攻略 / 备忘粘贴到这里，支持 Markdown\n\n# 标题\n- 要点一\n- 要点二'}
                  />
                  <Button
                    type="primary"
                    onClick={handlePasteImport}
                    loading={importing}
                    disabled={!pasteContent.trim()}
                  >
                    导入为笔记
                  </Button>
                </Space>
              ),
            },
          ]}
        />
      </Modal>
    </Space>
  )
}
