/**
 * 上传前把图片压到合适体积。
 *
 * **为什么必须在前端压**：手机拍的原图、微信「原图」普遍 5~12MB，而后端单文件上限
 * 是 8MB（视觉模型那边也要按 base64 传，太大既慢也容易被上游拒）。
 * 实测用户发一张微信原图，**上传阶段就 400「文件超过 8MB 上限」**——
 * 一次点选直接失败，是最容易被当成"功能坏了"的体验。
 *
 * 这里统一压到长边 1600px + JPEG q0.85，通常落到 200~600KB：
 * 手机上肉眼几乎看不出差别，而上传速度和成功率都上一个台阶。
 */

export interface PreparedUpload {
  file: File
  /** 压缩说明（给用户看的一句话），没压缩时为 null */
  note: string | null
}

const MAX_EDGE = 1600
const QUALITY = 0.85
/** 小于这个体积不压：省一次 canvas 编码，也避免无意义的二次损失 */
const SKIP_BELOW = 900 * 1024

/**
 * 单个附件上限，**必须与后端 ATTACHMENT_MAX_BYTES 保持一致**
 * （backend/app/core/config.py，默认 8MB）。
 * 放在前端是为了在用户点选文件的那一刻就给出反馈，
 * 而不是等传完一轮再收到 400——手机上上行慢，这个差别很明显。
 */
export const MAX_UPLOAD_BYTES = 8 * 1024 * 1024

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)}KB`
  return `${(bytes / 1024 / 1024).toFixed(bytes < 1024 * 1024 ? 2 : 1)}MB`
}

async function loadBitmap(file: File): Promise<{ drawable: CanvasImageSource; w: number; h: number }> {
  // createImageBitmap 更省内存（不会把原图整份解码进 DOM），iOS 15+ / Chrome 都支持
  if (typeof createImageBitmap === 'function') {
    const bitmap = await createImageBitmap(file)
    return { drawable: bitmap, w: bitmap.width, h: bitmap.height }
  }
  const url = URL.createObjectURL(file)
  try {
    const img = await new Promise<HTMLImageElement>((resolve, reject) => {
      const el = new Image()
      el.onload = () => resolve(el)
      el.onerror = () => reject(new Error('图片解码失败'))
      el.src = url
    })
    return { drawable: img, w: img.naturalWidth, h: img.naturalHeight }
  } finally {
    URL.revokeObjectURL(url)
  }
}

export async function prepareUpload(file: File): Promise<PreparedUpload> {
  // 只处理位图：GIF（动图）压了会丢动画，SVG 是矢量、不该栅格化
  if (!file.type.startsWith('image/') || file.type === 'image/gif' || file.type === 'image/svg+xml') {
    return { file, note: null }
  }
  if (file.size <= SKIP_BELOW) return { file, note: null }

  try {
    const { drawable, w: srcW, h: srcH } = await loadBitmap(file)
    const scale = Math.min(1, MAX_EDGE / Math.max(srcW, srcH))
    const w = Math.max(1, Math.round(srcW * scale))
    const h = Math.max(1, Math.round(srcH * scale))

    const canvas = document.createElement('canvas')
    canvas.width = w
    canvas.height = h
    const ctx = canvas.getContext('2d')
    if (!ctx) return { file, note: null }
    // 铺白底：JPEG 不支持透明，手机截图/带透明的 PNG 直接转会把透明区变黑
    ctx.fillStyle = '#ffffff'
    ctx.fillRect(0, 0, w, h)
    ctx.drawImage(drawable, 0, 0, w, h)

    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, 'image/jpeg', QUALITY),
    )
    // 压完反而更大（小图、或本来就是高质量 JPEG）就用原图，别做负优化
    if (!blob || blob.size >= file.size) return { file, note: null }

    const name = file.name.replace(/\.[^.]+$/, '') || 'image'
    return {
      file: new File([blob], `${name}.jpg`, { type: 'image/jpeg' }),
      note: `已压缩：${formatFileSize(file.size)} → ${formatFileSize(blob.size)}（长边 ${w}px）`,
    }
  } catch {
    // 压缩失败不该挡住上传：原样交给后端，由后端给出准确原因
    return { file, note: null }
  }
}
