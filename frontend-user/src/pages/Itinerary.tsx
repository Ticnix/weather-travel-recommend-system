import { useCallback, useEffect, useMemo, useState } from 'react'
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
  Space,
  Tag,
  TimePicker,
  Tooltip,
  Typography,
  message,
} from 'antd'
import {
  CommentOutlined,
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
} from '@ant-design/icons'
import dayjs, { type Dayjs } from 'dayjs'
import { isLoggedIn } from '../api/auth'
import {
  createItinerary,
  deleteItinerary,
  downloadItineraryIcs,
  listItinerary,
  listItineraryRisks,
  updateItinerary,
  type ItineraryItem,
  type ItineraryRisk,
} from '../api/itinerary'
import {
  canNativeShare,
  copyItineraryText,
  downloadPoster,
  posterDataUrl,
  sharePoster,
  trackShare,
} from '../utils/itineraryShare'
import NotePanel from '../components/NotePanel'
import LoadingState from '../components/LoadingState'
import EmptyState from '../components/EmptyState'
import MapLink from '../components/MapLink'

const { Paragraph, Text } = Typography

/** 出发提醒的提前量，与后端 reminder_tasks.REMIND_LEAD_MINUTES 保持一致 */
const REMIND_LEAD_MINUTES = 30

/**
 * 保存行程后是否该提醒用户「这条不会发出发提醒」。
 *
 * 提醒是出发前 30 分钟发的，所以「刚建一条 1 分钟后出发的行程」注定收不到——
 * 但用户只会认为"功能坏了"。这里在保存那一刻就把原因说清楚。
 */
function reminderHint(date: string, startTime?: string): string | null {
  if (!startTime) {
    return '这条行程没填开始时间，不会发送出发提醒'
  }
  const start = dayjs(`${date} ${startTime}`)
  if (!start.isValid()) {
    return `开始时间「${startTime}」不是 HH:MM 格式，出发提醒不会发送`
  }
  const minutes = start.diff(dayjs(), 'minute')
  if (minutes < 0) {
    return `开始时间「${startTime}」已经过去了，不会再发出发提醒`
  }
  if (minutes < REMIND_LEAD_MINUTES) {
    return `距出发只剩 ${minutes} 分钟，已错过「出发前 ${REMIND_LEAD_MINUTES} 分钟」的提醒窗口；想收到提醒，把开始时间改到 ${REMIND_LEAD_MINUTES} 分钟以后`
  }
  return null
}

/**
 * 列表上「这条到底会不会提醒」的标记。
 *
 * 保存时那个提示一闪就没了，用户回到页面看不到任何状态，
 * 于是"提醒功能不存在"就成了最自然的结论（实测反馈就是这句）。
 * 所以把规则摊在每条行程上：会提醒 / 没填时间 / 已过窗口。
 */
interface ReminderState {
  label: string
  color?: string
  tip: string
}

function reminderStateOf(item: ItineraryItem, now: Dayjs = dayjs()): ReminderState | null {
  if (!item.start_time) {
    return {
      label: '无出发提醒',
      tip: `这条没填「开始时间」，不会发送出发提醒。填上时间后，会在出发前 ${REMIND_LEAD_MINUTES} 分钟推送一次。`,
    }
  }
  const start = dayjs(`${item.date} ${item.start_time}`)
  if (!start.isValid()) {
    return {
      label: '时间格式不对',
      color: 'orange',
      tip: '开始时间不是 HH:MM，出发提醒不会发送；编辑这条行程重新选一次时间即可。',
    }
  }
  const minutes = start.diff(now, 'minute')
  // 已经出发的行程不再标注（列表里已有「已过去」标签，再加一个只会更乱）
  if (minutes < 0) return null
  if (minutes < REMIND_LEAD_MINUTES) {
    return {
      label: '已过提醒窗口',
      color: 'orange',
      tip: `距出发只剩 ${minutes} 分钟，已错过「出发前 ${REMIND_LEAD_MINUTES} 分钟」的提醒窗口。把开始时间调到 ${REMIND_LEAD_MINUTES} 分钟以后就能收到。`,
    }
  }
  const when = dayjs(item.date).isSame(now, 'day') ? '今天' : dateLabel(item.date)
  return {
    label: '⏰ 会提醒',
    color: 'green',
    tip: `${when} ${item.start_time} 出发，将在出发前 ${REMIND_LEAD_MINUTES} 分钟提醒你（需在「我的 → 通知设置」开启「行程提醒」并允许浏览器通知，否则会被拦下）。`,
  }
}

/** 时间范围筛选：默认只看"还没发生的"，否则行程一多，往下翻一屏都是过去的事 */
type RangeKey = 'upcoming' | 'today' | 'week' | 'all'

const RANGE_OPTIONS: Array<{ label: string; value: RangeKey }> = [
  { label: '即将开始', value: 'upcoming' },
  { label: '今天', value: 'today' },
  { label: '本周', value: 'week' },
  { label: '全部', value: 'all' },
]

const WEEK_LABEL = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

/** 日期分组标题：近几天用"今天/明天"说话，比"2026-09-20"好认得多 */
function dateLabel(date: string): string {
  const diff = dayjs(date).startOf('day').diff(dayjs().startOf('day'), 'day')
  if (diff === 0) return '今天'
  if (diff === 1) return '明天'
  if (diff === 2) return '后天'
  if (diff === -1) return '昨天'
  return dayjs(date).format('M月D日')
}

/** 排序键：没填时间的当成"当天最后"（多半是"全天"这类安排） */
function timeKey(item: ItineraryItem): string {
  return item.start_time ?? '99:99'
}

function inRange(item: ItineraryItem, range: RangeKey): boolean {
  const today = dayjs().startOf('day')
  const day = dayjs(item.date).startOf('day')
  if (range === 'today') return day.isSame(today, 'day')
  if (range === 'week') {
    const diff = day.diff(today, 'day')
    return diff >= 0 && diff < 7
  }
  if (range === 'upcoming') return !day.isBefore(today, 'day')
  return true
}

/** 这条行程是否已经开始（用「日期 + 开始时间」判断；没填时间就按当天结束算） */
function isPast(item: ItineraryItem): boolean {
  const start = item.start_time
    ? dayjs(`${item.date} ${item.start_time}`)
    : dayjs(item.date).endOf('day')
  return start.isBefore(dayjs())
}

export default function Itinerary() {
  const navigate = useNavigate()
  const [items, setItems] = useState<ItineraryItem[]>([])
  const [loading, setLoading] = useState(true)
  // 取数失败不能和"还没有行程"混为一谈：后者是用户自己没加，
  // 前者是没取到——显示成同一句话会让用户以为自己删光了
  const [failed, setFailed] = useState(false)
  const [open, setOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm()
  // 视图切换：结构化行程（用于天气提醒）/ 自由笔记（攻略、清单）
  const [view, setView] = useState<'plan' | 'note'>('plan')
  // 正在编辑的行程 id；null 表示新增
  const [editingId, setEditingId] = useState<number | null>(null)
  // 时间范围筛选（默认"即将开始"）
  const [range, setRange] = useState<RangeKey>('upcoming')
  // 刚保存的那条：高亮一下再滚动过去，否则用户翻半天找不到自己刚写的
  const [justSaved, setJustSaved] = useState<number | null>(null)
  // 行程天气风险（Day 52）：按行程 id 索引，渲染时直接查
  const [risks, setRisks] = useState<Record<string, ItineraryRisk>>({})

  const load = useCallback(async () => {
    setLoading(true)
    setFailed(false)
    try {
      const res = await listItinerary()
      setItems(res.items)
    } catch {
      // 全局拦截器只在右上角闪一条 toast，用户回头看列表仍是空的，
      // 所以页面内也要留下可重试的失败说明
      setItems([])
      setFailed(true)
    } finally {
      setLoading(false)
    }
    // 风险单独取：它失败**不该**让整页变成"加载失败"（列表其实已经拿到了），
    // 少一层提示而已，行程本身还能正常看
    try {
      const res = await listItineraryRisks()
      setRisks(res.by_itinerary ?? {})
    } catch {
      setRisks({})
    }
  }, [])

  useEffect(() => {
    if (isLoggedIn()) {
      load()
    } else {
      setLoading(false)
    }
  }, [load])

  // 海报预览（分享弹窗）：桌面端不走系统分享（面板是空的），先看图再下载
  const [posterUrl, setPosterUrl] = useState<string | null>(null)

  // 筛选 + 按日期分组：一次算好，渲染时不再反复判断
  const shown = useMemo(() => items.filter((it) => inRange(it, range)), [items, range])

  const groups = useMemo(() => {
    const byDate = new Map<string, ItineraryItem[]>()
    for (const it of shown) {
      const list = byDate.get(it.date)
      if (list) list.push(it)
      else byDate.set(it.date, [it])
    }
    return [...byDate.entries()]
      .map(([date, list]) => ({
        date,
        items: [...list].sort((a, b) => timeKey(a).localeCompare(timeKey(b))),
      }))
      .sort((a, b) => a.date.localeCompare(b.date))
  }, [shown])

  // 每个筛选下的条数直接写在选项上：用户不必来回切着数
  const counts = useMemo(() => {
    const result: Record<string, number> = {}
    for (const option of RANGE_OPTIONS) {
      result[option.value] = items.filter((it) => inRange(it, option.value)).length
    }
    return result
  }, [items])

  // "下一段"：第一个还没开始的行程——用户最关心的就是这一条
  const nextId = useMemo(() => {
    const upcoming = shown
      .filter((it) => !isPast(it))
      .sort((a, b) => `${a.date} ${timeKey(a)}`.localeCompare(`${b.date} ${timeKey(b)}`))
    return upcoming[0]?.id ?? null
  }, [shown])

  // 刚保存的那条：高亮 3 秒后取消
  useEffect(() => {
    if (justSaved === null) return
    const timer = setTimeout(() => setJustSaved(null), 3000)
    return () => clearTimeout(timer)
  }, [justSaved])

  // 滚动过去。依赖里带 items：保存后列表是重新拉的，
  // 只靠 justSaved 变化会在"新条目还没进 DOM"时白跑一次
  useEffect(() => {
    if (justSaved === null) return
    document
      .querySelector('[data-just-saved]')
      ?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [justSaved, items])

  // 新增 / 编辑共用：editingId 有值即为编辑
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      setSubmitting(true)
      const payload = {
        title: values.title,
        date: (values.date as Dayjs).format('YYYY-MM-DD'),
        // TimePicker 给的是 Dayjs，后端要的仍是 "HH:MM" 字符串
        start_time: values.start_time
          ? (values.start_time as Dayjs).format('HH:mm')
          : undefined,
        location: values.location || undefined,
        activity: values.activity || undefined,
        note: values.note || undefined,
      }
      if (editingId !== null) {
        await updateItinerary(editingId, payload)
        message.success('行程已更新')
        setJustSaved(editingId)
      } else {
        const created = await createItinerary(payload)
        message.success('行程已添加')
        setJustSaved(created?.id ?? null)
        // 新行程落在当前筛选之外（比如补了一条上个月的）就自动切"全部"：
        // 保存成功却看不见，用户只会以为没存上
        if (!inRange({ date: payload.date } as ItineraryItem, range)) setRange('all')
      }
      // 保存成功不代表能收到提醒：时间太近/已过/格式不对时当场说明，
      // 而不是让用户等一条永远不会来的通知。
      // "没填时间"只是轻提示——不少人本来就是按天安排的，不必报警
      const hint = reminderHint(payload.date, payload.start_time)
      if (hint) {
        if (payload.start_time) message.warning(hint, 6)
        else message.info(hint, 5)
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
      // TimePicker 的值必须是 Dayjs；库里存的是 "HH:MM"，借一个固定日期拼出来最省事
      start_time: it.start_time ? dayjs(`2000-01-01 ${it.start_time}`) : null,
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

        {/* 时间范围筛选：默认只看"还没发生的"。
            行程攒多了以后，不加筛选就得一路往下翻过去的事，最新的安排反而看不见 */}
        {view === 'plan' && (
          <div
            style={{
              marginTop: 12,
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              flexWrap: 'wrap',
            }}
          >
            <Segmented
              size="small"
              value={range}
              onChange={(v) => setRange(v as RangeKey)}
              options={RANGE_OPTIONS.map((o) => ({
                label: `${o.label} ${counts[o.value]}`,
                value: o.value,
              }))}
            />
            <Text style={{ fontSize: 12, color: 'var(--jp-ink-3)' }}>
              共 {items.length} 段行程
            </Text>
            <Text style={{ fontSize: 12, color: 'var(--jp-ink-3)' }}>
              ⏰ 出发前 {REMIND_LEAD_MINUTES} 分钟推送提醒
            </Text>
            {/* 导出到日历：系统日历的提醒不依赖打开本应用（App 被杀也有系统提醒兜底） */}
            <Button
              type="link"
              size="small"
              style={{ padding: 0 }}
              onClick={() => {
                downloadItineraryIcs()
                  .then(() => message.success('已导出 .ics，在系统日历中导入即可到点提醒'))
                  .catch(() => message.error('导出失败，请稍后重试'))
              }}
            >
              导出到日历
            </Button>
            {/* 分享海报：先弹**预览**再决定分享/下载——桌面系统分享面板是空的
                （Windows 没注册文件分享目标），直接调 navigator.share 只会白屏 */}
            <Button
              type="link"
              size="small"
              style={{ padding: 0 }}
              onClick={() => {
                try {
                  setPosterUrl(posterDataUrl(shown))
                } catch (err) {
                  message.error((err as Error).message)
                }
              }}
            >
              分享海报
            </Button>
            {/* 复制文案跟随当前 Tab（shown），而不是全量行程——
                用户筛了「今天」却复制出一个月的行程，等于复制了个寂寞 */}
            <Button
              type="link"
              size="small"
              style={{ padding: 0 }}
              onClick={() => {
                copyItineraryText(shown)
                  .then(() => message.success(`已复制 ${shown.length} 段行程，可直接粘贴给朋友`))
                  .catch(() => message.error('复制失败，请手动选择文字复制'))
              }}
            >
              复制文案
            </Button>
          </div>

        )}
      </div>

      {/* 海报预览：桌面「下载图片」，触屏设备才有「系统分享」。
          放在 view 条件块外：Modal 自带开关，不该跟着列表一起被条件卸载 */}
      <Modal
        open={!!posterUrl}
        title="行程海报"
        width={420}
        onCancel={() => setPosterUrl(null)}
        footer={[
          canNativeShare() ? (
            <Button
              key="share"
              type="primary"
              onClick={() => {
                sharePoster(shown)
                  .then((outcome) => {
                    if (outcome === 'shared') message.success('已唤起分享')
                    setPosterUrl(null)
                  })
                  .catch((err: Error) => message.error(err.message))
              }}
            >
              系统分享
            </Button>
          ) : null,
          <Button
            key="download"
            type={canNativeShare() ? 'default' : 'primary'}
            onClick={() => {
              if (!posterUrl) return
              downloadPoster(posterUrl)
              trackShare()
              message.success('海报已保存到下载')
            }}
          >
            下载图片
          </Button>,
          <Button key="close" onClick={() => setPosterUrl(null)}>
            关闭
          </Button>,
        ]}
      >
        {posterUrl && <img src={posterUrl} alt="行程海报" style={{ width: '100%' }} />}
      </Modal>

      {view === 'note' ? (
        <NotePanel />
      ) : loading ? (
        <div className="jp-card" style={{ padding: 24 }}>
          <LoadingState
            text="正在加载你的行程…"
            hint="会同时比对每段行程当天的天气，通常 1~2 秒"
          />
        </div>
      ) : failed ? (
        <div className="jp-card" style={{ padding: 20 }}>
          <EmptyState
            type="error"
            text="行程没能加载出来"
            hint="这不是「你没有行程」，而是这次请求失败了；网络恢复后重试即可"
            onRetry={() => void load()}
          />
        </div>
      ) : items.length === 0 ? (
        <div className="jp-card" style={{ padding: '40px 20px' }}>
          <Empty description="还没有行程，点击右上角「添加行程」开始安排吧" />
        </div>
      ) : groups.length === 0 ? (
        // 有行程、但当前筛选下没有：必须说清是筛选的问题，而不是"你把行程删光了"
        <div className="jp-card" style={{ padding: '32px 20px' }}>
          <Empty description={`「${RANGE_OPTIONS.find((o) => o.value === range)?.label}」里没有行程`}>
            <Button size="small" onClick={() => setRange('all')}>
              看全部 {items.length} 段
            </Button>
          </Empty>
        </div>
      ) : (
        <Space direction="vertical" size={14} style={{ width: '100%' }}>
          {/* 按日期分组：一天一张卡、当天按时间排成时间轴。
              原来一天几段就堆几张一样的卡片，翻两屏也看不出哪条是哪天 */}
          {groups.map((group) => {
            const groupPast = dayjs(group.date).isBefore(dayjs().startOf('day'), 'day')
            return (
              <div key={group.date} className="jp-card" style={{ padding: '14px 18px' }}>
                <div
                  style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}
                >
                  <span
                    className="jp-serif"
                    style={{
                      fontSize: 17,
                      fontWeight: 700,
                      color: groupPast ? 'var(--jp-ink-3)' : 'var(--jp-ink)',
                    }}
                  >
                    {dateLabel(group.date)}
                  </span>
                  <Text style={{ fontSize: 12, color: 'var(--jp-ink-3)' }}>
                    {group.date} {WEEK_LABEL[dayjs(group.date).day()]} · {group.items.length} 段
                  </Text>
                  {/* 日期组头直接加一条：省掉"打开弹窗再选日期"这一步 */}
                  <Button
                    type="link"
                    size="small"
                    icon={<PlusOutlined />}
                    style={{ padding: 0 }}
                    onClick={() => {
                      setEditingId(null)
                      form.resetFields()
                      form.setFieldsValue({ date: dayjs(group.date) })
                      setOpen(true)
                    }}
                  >
                    加一条
                  </Button>
                </div>

                <div>
                  {group.items.map((it, index) => {
                    const pastItem = isPast(it)
                    const isNew = it.id === justSaved
                    // 风险优先于"会不会提醒"：同一处只显示最要紧的那个徽标，
                    // 两个并排反而让人抓不住重点
                    const risk = pastItem ? undefined : risks[String(it.id)]
                    const reminder = pastItem || risk ? null : reminderStateOf(it)
                    return (
                      <div
                        key={it.id}
                        data-itinerary-id={it.id}
                        data-just-saved={isNew ? '1' : undefined}
                        style={{
                          display: 'flex',
                          gap: 12,
                          padding: '10px 0',
                          borderTop: index === 0 ? 'none' : '1px dashed var(--jp-border)',
                          background: isNew ? 'var(--jp-panel-2)' : undefined,
                          borderRadius: isNew ? 8 : undefined,
                        }}
                      >
                        {/* 时间轴左列：同一天的先后顺序一眼可见 */}
                        <div style={{ width: 46, flexShrink: 0, textAlign: 'right' }}>
                          <div
                            style={{
                              fontSize: it.start_time ? 15 : 12,
                              fontWeight: 600,
                              lineHeight: 1.5,
                              color: pastItem ? 'var(--jp-ink-3)' : 'var(--jp-indigo)',
                            }}
                          >
                            {it.start_time ?? '全天'}
                          </div>
                        </div>

                        <div style={{ flex: 1, minWidth: 0 }}>
                          <Space size={6} wrap align="center">
                            {/* 标题可点开地图：库里没存坐标，走"按地名搜索"这一档 */}
                            <span
                              style={{
                                fontSize: 15,
                                fontWeight: 600,
                                color: pastItem ? 'var(--jp-ink-3)' : 'var(--jp-ink)',
                              }}
                            >
                              <MapLink name={it.location || it.title}>{it.title}</MapLink>
                            </span>
                            {isNew && (
                              <Tag color="green" style={{ margin: 0 }}>
                                刚添加
                              </Tag>
                            )}
                            {it.id === nextId && (
                              <Tag color="geekblue" style={{ margin: 0 }}>
                                下一段
                              </Tag>
                            )}
                            {pastItem && <Tag style={{ margin: 0 }}>已过去</Tag>}
                            {/* 行程天气冲突：悬停给出**具体建议**（改到哪天／为什么要改），
                                而不是只说"有风险"——只给结论不给做法等于没帮上忙 */}
                            {risk && (
                              <Tooltip title={risk.body}>
                                <Tag
                                  color={risk.level === 'danger' ? 'red' : 'orange'}
                                  style={{ margin: 0, cursor: 'help' }}
                                >
                                  {risk.level === 'danger' ? '⚠️ 天气冲突' : '天气提醒'}
                                </Tag>
                              </Tooltip>
                            )}
                            {/* 会不会提醒，直接标在这条上：光靠保存时一闪而过的提示，
                                用户回到列表是看不到状态的 */}
                            {reminder && (
                              <Tooltip title={reminder.tip}>
                                <Tag
                                  color={reminder.color}
                                  style={{ margin: 0, cursor: 'help' }}
                                >
                                  {reminder.label}
                                </Tag>
                              </Tooltip>
                            )}
                            {it.activity && <Tag style={{ margin: 0 }}>{it.activity}</Tag>}
                          </Space>
                          {/* 地点与标题不同才单独列出：相同就是同一句话显示两遍 */}
                          {it.location && it.location !== it.title && (
                            <div style={{ marginTop: 2, fontSize: 12, color: 'var(--jp-ink-3)' }}>
                              <MapLink name={it.location} />
                            </div>
                          )}
                          {it.note && (
                            <Paragraph
                              style={{ margin: '4px 0 0', fontSize: 12, color: 'var(--jp-ink-3)' }}
                              ellipsis={{ rows: 2, tooltip: it.note }}
                            >
                              {it.note}
                            </Paragraph>
                          )}
                        </div>

                        <Space size={0} style={{ alignSelf: 'flex-start' }}>
                          <Button
                            type="text"
                            size="small"
                            icon={<EditOutlined />}
                            onClick={() => openEdit(it)}
                          />
                          <Popconfirm title="确定删除这条行程？" onConfirm={() => handleDelete(it.id)}>
                            <Button type="text" size="small" danger icon={<DeleteOutlined />} />
                          </Popconfirm>
                        </Space>
                      </div>
                    )
                  })}
                </div>
              </div>
            )
          })}
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
            {/* 用选择器而不是文本框：手输「9点」「09：00」这类写法会让行程收不到出发提醒
                （提醒任务按 HH:MM 解析），选择器从源头杜绝格式问题 */}
            <TimePicker
              style={{ width: '100%' }}
              format="HH:mm"
              minuteStep={5}
              needConfirm={false}
              placeholder="选择开始时间"
            />
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
