<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import {
  listCleanTasks,
  getCleanTask,
  uploadCsv,
  downloadClean,
  type CleanTaskDetail,
  type CleanTaskItem,
} from '../api/clean'

const loading = ref(false)
const rows = ref<CleanTaskItem[]>([])
const uploading = ref(false)
const uploadInput = ref<HTMLInputElement | null>(null)

// 日志弹窗
const logVisible = ref(false)
const logLoading = ref(false)
const currentLog = ref('')
const currentFileName = ref('')

const STATUS_TAG: Record<string, { label: string; type: string }> = {
  pending: { label: '排队中', type: 'info' },
  running: { label: '清洗中', type: 'warning' },
  success: { label: '成功', type: 'success' },
  failed: { label: '失败', type: 'danger' },
}

async function load() {
  loading.value = true
  try {
    const res = await listCleanTasks(30)
    rows.value = res.items
  } catch {
    rows.value = []
  } finally {
    loading.value = false
  }
}

async function onPickFile(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  uploading.value = true
  try {
    const res = await uploadCsv(file)
    ElMessage.success(`已提交清洗任务：${res.filename}`)
    setTimeout(load, 2000)
  } catch {
    /* 拦截器提示 */
  } finally {
    uploading.value = false
    input.value = ''
  }
}

async function viewLog(task: CleanTaskItem) {
  logVisible.value = true
  logLoading.value = true
  currentFileName.value = task.filename
  currentLog.value = '加载中...'
  try {
    const detail: CleanTaskDetail = await getCleanTask(task.task_id)
    currentLog.value = detail.log || '（无日志）'
  } catch {
    currentLog.value = '获取日志失败'
  } finally {
    logLoading.value = false
  }
}

async function doDownload(task: CleanTaskItem) {
  try {
    await downloadClean(task.task_id, `cleaned_${task.filename}`)
  } catch {
    ElMessage.error('下载失败')
  }
}

onMounted(() => {
  load()
  setInterval(() => {
    const hasActive = rows.value.some((r) => r.status === 'running' || r.status === 'pending')
    if (hasActive) load()
  }, 4000)
})
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <div class="hd">
        <b>原始数据清洗管理</b>
        <el-button :loading="uploading" :icon="UploadFilled" type="primary" @click="uploadInput?.click()">
          上传 CSV 触发清洗
        </el-button>
        <input ref="uploadInput" type="file" accept=".csv" style="display: none" @change="onPickFile" />
      </div>
    </template>

    <el-alert
      type="info"
      show-icon
      :closable="false"
      title="上传 .csv 原始气象数据，后台自动执行「去重 / 缺失填充 / 异常过滤 / 单位标准化」清洗并入库"
      style="margin-bottom: 16px"
    />

    <el-table v-loading="loading" :data="rows" border stripe>
      <el-table-column prop="filename" label="文件名" min-width="200" show-overflow-tooltip />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="(STATUS_TAG[row.status]?.type as any) || 'info'" size="small">
            {{ STATUS_TAG[row.status]?.label || row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="清洗统计" min-width="180">
        <template #default="{ row }">
          <span v-if="row.cleaned_rows != null" style="font-size: 12px; color: #606266">
            总 {{ row.total_rows }} → {{ row.cleaned_rows }} 行
          </span>
          <span v-else style="color: #c0c4cc">--</span>
        </template>
      </el-table-column>
      <el-table-column label="去重" prop="duplicated_removed" width="70" align="center" />
      <el-table-column label="填充" prop="filled_missing" width="70" align="center" />
      <el-table-column label="异常过滤" prop="filtered_outliers" width="90" align="center" />
      <el-table-column label="单位标准化" prop="unit_standardized" width="100" align="center" />
      <el-table-column prop="triggered_by" label="触发人" width="100" />
      <el-table-column label="时间" width="160">
        <template #default="{ row }">{{ String(row.created_at).replace('T', ' ').slice(0, 16) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="viewLog(row)">日志</el-button>
          <el-button v-if="row.status === 'success'" link type="success" @click="doDownload(row)">下载</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && !rows.length" description="暂无清洗任务" />

    <!-- 日志弹窗 -->
    <el-dialog v-model="logVisible" :title="`清洗日志 - ${currentFileName}`" width="720px">
      <pre v-loading="logLoading" class="log-box">{{ currentLog }}</pre>
    </el-dialog>
  </el-card>
</template>

<style scoped>
.hd {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.uploader :deep(.el-upload-dragger) {
  width: 100%;
}
.log-box {
  background: #0f172a;
  color: #a5f3fc;
  padding: 16px;
  border-radius: 8px;
  max-height: 420px;
  overflow: auto;
  font-size: 12.5px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
