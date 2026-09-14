import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Button,
  DatePicker,
  Empty,
  Form,
  Input,
  Modal,
  Popconfirm,
  Segmented,
  Skeleton,
  Space,
  Tag,
  Typography,
  message,
} from 'antd'
import {
  CalendarOutlined,
  CommentOutlined,
  DeleteOutlined,
  EditOutlined,
  EnvironmentOutlined,
  PlusOutlined,
} from '@ant-design/icons'
import dayjs, { type Dayjs } from 'dayjs'
import { isLoggedIn } from '../api/auth'
import {
  createItinerary,
  deleteItinerary,
  listItinerary,
  updateItinerary,
  type ItineraryItem,
} from '../api/itinerary'
import NotePanel from '../components/NotePanel'

const { Paragraph, Text } = Typography

export default function Itinerary() {
  const navigate = useNavigate()
  const [items, setItems] = useState<ItineraryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [open, setOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm()
  // 视图切换：结构化行程（用于天气提醒）/ 自由笔记（攻略、清单）
  const [view, setView] = useState<'plan' | 'note'>('plan')
  // 正在编辑的行程 id；null 表示新增
  const [editingId, setEditingId] = useState<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await listItinerary()
      setItems(res.items)
    } catch {
      // 失败提示已由 http 拦截器统一处理
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (isLoggedIn()) {
      load()
    } else {
      setLoading(false)
    }
  }, [load])

  // 新增 / 编辑共用：editingId 有值即为编辑
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      setSubmitting(true)
      const payload = {
        title: values.title,
        date: (values.date as Dayjs).format('YYYY-MM-DD'),
        start_time: values.start_time || undefined,
        location: values.location || undefined,
        activity: values.activity || undefined,
        note: values.note || undefined,
      }
      if (editingId !== null) {
        await updateItinerary(editingId, payload)
        message.success('行程已更新')
      } else {
        await createItinerary(payload)
        message.success('行程已添加')
      }
      setOpen(false)
      form.resetFields()
      setEditingId(null)
      await load()
    } catch (e) {
      // validateFields 失败时会抛校验错误对象，只提示业务异常
      if (e instanceof Error) message.error(e.message)
    } finally {
      setSubmitting(false)
    }
  }

  // 打开编辑：把该条行程回填到表单
  const openEdit = (it: ItineraryItem) => {
    setEditingId(it.id)
    form.setFieldsValue({
      title: it.title,
      date: dayjs(it.date),
      start_time: it.start_time ?? '',
      location: it.location ?? '',
      activity: it.activity ?? '',
      note: it.note ?? '',
    })
    setOpen(true)
  }

  const handleDelete = async (id: number) => {
    try {
      await deleteItinerary(id)
      message.success('已删除')
      await load()
    } catch {
      /* 拦截器已提示 */
    }
  }

  // 未登录引导
  if (!isLoggedIn()) {
    return (
      <div className="jp-card" style={{ padding: '60px 20px', textAlign: 'center' }}>
        <div style={{ fontSize: 52 }}>🗓️</div>
        <div
          className="jp-serif"
          style={{ fontSize: 20, fontWeight: 600, marginTop: 16, color: 'var(--jp-ink)' }}
        >
          我的行程
        </div>
        <Paragraph style={{ color: 'var(--jp-ink-2)', marginTop: 8 }}>
          登录后即可添加行程，并获得结合天气的出行提醒。
        </Paragraph>
        <Button type="primary" onClick={() => navigate('/login', { state: { from: '/itinerary' } })}>
          去登录
        </Button>
      </div>
    )
  }

  return (
    <Space direction="vertical" size={20} style={{ width: '100%', maxWidth: 860, margin: '0 auto' }}>
      <div className="jp-card" style={{ padding: '20px 24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
          <div>
            <div className="jp-serif" style={{ fontSize: 22, fontWeight: 700, color: 'var(--jp-ink)' }}>
              我的行程
            </div>
            <Text style={{ color: 'var(--jp-ink-2)', fontSize: 13 }}>
              添加行程后，可直接问 AI「明天有什么安排」，会自动结合当地天气给出提醒。
            </Text>
          </div>
          <Space>
            <Button icon={<CommentOutlined />} onClick={() => navigate('/chat')}>
              问 AI
            </Button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => {
                setEditingId(null)
                form.resetFields()
                setOpen(true)
              }}
            >
              添加行程
            </Button>
          </Space>
        </div>

        {/* 视图切换：结构化行程（用于天气提醒）/ 自由笔记（攻略、清单） */}
        <Segmented
          value={view}
          onChange={(v) => setView(v as 'plan' | 'note')}
          style={{ marginTop: 14 }}
          options={[
            { label: '🗓️ 行程安排', value: 'plan' },
            { label: '📝 行程笔记', value: 'note' },
          ]}
        />
      </div>

      {view === 'note' ? (
        <NotePanel />
      ) : loading ? (
        <div className="jp-card" style={{ padding: 24 }}>
          <Skeleton active paragraph={{ rows: 4 }} />
        </div>
      ) : items.length === 0 ? (
        <div className="jp-card" style={{ padding: '40px 20px' }}>
          <Empty description="还没有行程，点击右上角「添加行程」开始安排吧" />
        </div>
      ) : (
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          {items.map((it) => (
            <div key={it.id} className="jp-card" style={{ padding: 18 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                  <Space size={8} align="center" wrap>
                    <Tag color="blue" icon={<CalendarOutlined />}>
                      {it.date}
                    </Tag>
                    {it.start_time && <Tag>{it.start_time}</Tag>}
                    <span className="jp-serif" style={{ fontSize: 16, fontWeight: 600, color: 'var(--jp-ink)' }}>
                      {it.title}
                    </span>
                  </Space>
                  <div style={{ marginTop: 8, color: 'var(--jp-ink-2)', fontSize: 13 }}>
                    {it.location && (
                      <span style={{ marginRight: 16 }}>
                        <EnvironmentOutlined /> {it.location}
                      </span>
                    )}
                    {it.activity && <span>{it.activity}</span>}
                  </div>
                  {it.note && (
                    <Paragraph style={{ marginTop: 6, marginBottom: 0, color: 'var(--jp-ink-3)', fontSize: 12 }}>
                      {it.note}
                    </Paragraph>
                  )}
                </div>
                <Space size={2}>
                  <Button type="text" icon={<EditOutlined />} onClick={() => openEdit(it)} />
                  <Popconfirm title="确定删除这条行程？" onConfirm={() => handleDelete(it.id)}>
                    <Button type="text" danger icon={<DeleteOutlined />} />
                  </Popconfirm>
                </Space>
              </div>
            </div>
          ))}
        </Space>
      )}

      <Modal
        title={editingId !== null ? '编辑行程' : '添加行程'}
        open={open}
        onCancel={() => {
          setOpen(false)
          setEditingId(null)
        }}
        onOk={handleSubmit}
        confirmLoading={submitting}
        okText="保存"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" style={{ marginTop: 12 }}>
          <Form.Item name="title" label="行程标题" rules={[{ required: true, message: '请输入行程标题' }]}>
            <Input placeholder="如：迪士尼一日游" maxLength={64} />
          </Form.Item>
          <Form.Item name="date" label="日期" rules={[{ required: true, message: '请选择日期' }]}>
            <DatePicker style={{ width: '100%' }} placeholder="选择日期" />
          </Form.Item>
          <Form.Item name="start_time" label="开始时间（可选）">
            <Input placeholder="如：09:00" maxLength={8} />
          </Form.Item>
          <Form.Item name="location" label="地点（可选）">
            <Input placeholder="如：上海迪士尼（会据此查询当地天气）" maxLength={128} />
          </Form.Item>
          <Form.Item name="activity" label="活动（可选）">
            <Input placeholder="如：游玩 / 爬山 / 逛街" maxLength={64} />
          </Form.Item>
          <Form.Item name="note" label="备注（可选）">
            <Input.TextArea rows={2} maxLength={255} placeholder="其他需要提醒的信息" />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  )
}
