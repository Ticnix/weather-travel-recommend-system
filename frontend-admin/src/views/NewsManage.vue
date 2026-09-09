<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listNews, createNews, updateNews, deleteNews, type NewsItem } from '../api/news'

const loading = ref(false)
const rows = ref<NewsItem[]>([])
const total = ref(0)

const query = reactive({
  page: 1,
  page_size: 20,
  category: '' as 'news' | 'notice' | '',
  keyword: '',
})

const dialogVisible = ref(false)
const editing = ref(false)
const form = reactive({
  id: 0,
  title: '',
  content: '',
  category: 'news' as 'news' | 'notice',
  is_top: false,
  is_published: false,
})

function emptyForm() {
  form.id = 0
  form.title = ''
  form.content = ''
  form.category = 'news'
  form.is_top = false
  form.is_published = false
}

async function load() {
  loading.value = true
  try {
    const res = await listNews({
      page: query.page,
      page_size: query.page_size,
      category: query.category || undefined,
      keyword: query.keyword || undefined,
    })
    rows.value = res.items
    total.value = res.total
  } catch {
    rows.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function onSearch() {
  query.page = 1
  load()
}

function openCreate() {
  editing.value = false
  emptyForm()
  dialogVisible.value = true
}

function openEdit(row: NewsItem) {
  editing.value = true
  form.id = row.id
  form.title = row.title
  form.content = row.content
  form.category = row.category
  form.is_top = row.is_top
  form.is_published = row.is_published
  dialogVisible.value = true
}

async function submit() {
  if (!form.title.trim() || !form.content.trim()) {
    ElMessage.warning('标题和内容不能为空')
    return
  }
  const payload = {
    title: form.title,
    content: form.content,
    category: form.category,
    is_top: form.is_top,
    is_published: form.is_published,
  }
  if (editing.value) {
    await updateNews(form.id, payload)
    ElMessage.success('更新成功')
  } else {
    await createNews(payload)
    ElMessage.success('创建成功')
  }
  dialogVisible.value = false
  load()
}

async function onDelete(row: NewsItem) {
  await ElMessageBox.confirm(`确认删除「${row.title}」？`, '删除确认', { type: 'warning' })
  await deleteNews(row.id)
  ElMessage.success('删除成功')
  load()
}

async function togglePublish(row: NewsItem) {
  await updateNews(row.id, { is_published: !row.is_published })
  ElMessage.success(row.is_published ? '已取消发布' : '已发布')
  load()
}

async function toggleTop(row: NewsItem) {
  await updateNews(row.id, { is_top: !row.is_top })
  ElMessage.success(row.is_top ? '已取消置顶' : '已置顶')
  load()
}

onMounted(load)
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <div class="hd">
        <b>资讯公告管理</b>
        <div>
          <el-button type="primary" @click="openCreate">新增</el-button>
        </div>
      </div>
    </template>

    <!-- 筛选 -->
    <el-form inline class="filter-bar">
      <el-form-item label="类型">
        <el-select v-model="query.category" style="width: 130px" clearable>
          <el-option label="全部" value="" />
          <el-option label="气象资讯" value="news" />
          <el-option label="官方公告" value="notice" />
        </el-select>
      </el-form-item>
      <el-form-item label="关键字">
        <el-input v-model="query.keyword" placeholder="搜索标题" clearable style="width: 200px" @keyup.enter="onSearch" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="onSearch">查询</el-button>
      </el-form-item>
    </el-form>

    <el-table v-loading="loading" :data="rows" border stripe>
      <el-table-column type="index" width="50" />
      <el-table-column prop="title" label="标题" min-width="220" show-overflow-tooltip />
      <el-table-column label="类型" width="100">
        <template #default="{ row }">
          <el-tag :type="row.category === 'notice' ? 'danger' : 'primary'" size="small">
            {{ row.category === 'notice' ? '公告' : '资讯' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="置顶" width="80" align="center">
        <template #default="{ row }">
          <el-switch :model-value="row.is_top" @change="toggleTop(row)" />
        </template>
      </el-table-column>
      <el-table-column label="发布" width="80" align="center">
        <template #default="{ row }">
          <el-switch :model-value="row.is_published" @change="togglePublish(row)" />
        </template>
      </el-table-column>
      <el-table-column prop="view_count" label="阅读" width="80" align="center" />
      <el-table-column label="作者" prop="author" width="110" />
      <el-table-column label="发布时间" width="160">
        <template #default="{ row }">{{ String(row.created_at).replace('T', ' ').slice(0, 16) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      class="pager"
      background
      layout="total, sizes, prev, pager, next"
      :total="total"
      :current-page="query.page"
      :page-size="query.page_size"
      :page-sizes="[10, 20, 50]"
      @current-change="(p: number) => { query.page = p; load() }"
      @size-change="(s: number) => { query.page_size = s; query.page = 1; load() }"
    />

    <!-- 新增/编辑 -->
    <el-dialog v-model="dialogVisible" :title="editing ? '编辑' : '新增'" width="640px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="类型">
          <el-radio-group v-model="form.category">
            <el-radio-button value="news">气象资讯</el-radio-button>
            <el-radio-button value="notice">官方公告</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="标题">
          <el-input v-model="form.title" placeholder="请输入标题" maxlength="120" show-word-limit />
        </el-form-item>
        <el-form-item label="内容">
          <el-input v-model="form.content" type="textarea" :rows="8" placeholder="请输入正文内容" />
        </el-form-item>
        <el-form-item label="属性">
          <el-checkbox v-model="form.is_top">置顶</el-checkbox>
          <el-checkbox v-model="form.is_published">立即发布</el-checkbox>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submit">保存</el-button>
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
.filter-bar :deep(.el-form-item) {
  margin-bottom: 12px;
}
.pager {
  margin-top: 16px;
  justify-content: flex-end;
}
</style>
