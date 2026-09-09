<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listFeedback, updateFeedback, type FeedbackItem } from '../api/feedback'

const STATUS_MAP: Record<string, { label: string; type: string }> = {
  pending: { label: '待处理', type: 'warning' },
  processing: { label: '处理中', type: 'primary' },
  resolved: { label: '已解决', type: 'success' },
  closed: { label: '已关闭', type: 'info' },
}

const loading = ref(false)
const rows = ref<FeedbackItem[]>([])
const total = ref(0)
const query = reactive({ page: 1, page_size: 20, status: '' })

// 回复弹窗
const dialogVisible = ref(false)
const current = ref<FeedbackItem | null>(null)
const reply = ref('')

async function load() {
  loading.value = true
  try {
    const res = await listFeedback(query.page, query.page_size, query.status || undefined)
    rows.value = res.items
    total.value = res.total
  } catch {
    rows.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function onStatusFilter(v: string) {
  query.status = v
  query.page = 1
  load()
}

async function changeStatus(row: FeedbackItem, s: string) {
  await updateFeedback(row.id, { status: s })
  row.status = s as FeedbackItem['status']
  ElMessage.success(`状态已更新为「${STATUS_MAP[s].label}」`)
}

function openReply(row: FeedbackItem) {
  current.value = row
  reply.value = row.reply || ''
  dialogVisible.value = true
}

async function submitReply() {
  if (!current.value) return
  await updateFeedback(current.value.id, {
    reply: reply.value,
    status: current.value.status === 'pending' ? 'processing' : current.value.status,
  })
  ElMessage.success('已回复')
  dialogVisible.value = false
  load()
}

onMounted(load)
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <div class="hd">
        <b>用户反馈管理</b>
        <el-radio-group :model-value="query.status" @change="onStatusFilter">
          <el-radio-button value="">全部</el-radio-button>
          <el-radio-button value="pending">待处理</el-radio-button>
          <el-radio-button value="processing">处理中</el-radio-button>
          <el-radio-button value="resolved">已解决</el-radio-button>
          <el-radio-button value="closed">已关闭</el-radio-button>
        </el-radio-group>
      </div>
    </template>

    <el-table v-loading="loading" :data="rows" border stripe>
      <el-table-column type="index" width="50" />
      <el-table-column prop="content" label="反馈内容" min-width="240" show-overflow-tooltip />
      <el-table-column label="提交人" width="100">
        <template #default="{ row }">{{ row.username || (row.user_id ? `用户#${row.user_id}` : '匿名') }}</template>
      </el-table-column>
      <el-table-column prop="contact" label="联系方式" width="140">
        <template #default="{ row }">{{ row.contact || '--' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="130">
        <template #default="{ row }">
          <el-select :model-value="row.status" size="small" style="width: 110px" @change="(v: string) => changeStatus(row, v)">
            <el-option v-for="(m, k) in STATUS_MAP" :key="k" :label="m.label" :value="k" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="回复" min-width="140">
        <template #default="{ row }">
          <el-tag v-if="row.reply" type="success" size="small" effect="plain">{{ row.reply }}</el-tag>
          <span v-else style="color: #c0c4cc">未回复</span>
        </template>
      </el-table-column>
      <el-table-column label="提交时间" width="160">
        <template #default="{ row }">{{ String(row.created_at).replace('T', ' ').slice(0, 16) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="90" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openReply(row)">回复</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      class="pager"
      background
      layout="total, prev, pager, next"
      :total="total"
      :current-page="query.page"
      :page-size="query.page_size"
      @current-change="(p: number) => { query.page = p; load() }"
    />

    <!-- 回复弹窗 -->
    <el-dialog v-model="dialogVisible" :title="`回复反馈 #${current?.id}`" width="520px">
      <el-form label-position="top">
        <el-form-item label="用户反馈">
          <div class="fb-content">{{ current?.content }}</div>
        </el-form-item>
        <el-form-item label="管理员回复">
          <el-input v-model="reply" type="textarea" :rows="4" placeholder="输入回复内容" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitReply">提交回复</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<style scoped>
.hd {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.pager {
  margin-top: 16px;
  justify-content: flex-end;
}
.fb-content {
  background: #f5f7fa;
  padding: 10px 14px;
  border-radius: 6px;
  color: #303133;
  line-height: 1.6;
  width: 100%;
}
</style>
