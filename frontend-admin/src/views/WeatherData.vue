<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminList, type HistoryRecord } from '../api/weather'

const loading = ref(false)
const rows = ref<HistoryRecord[]>([])
const total = ref(0)
const selection = ref<HistoryRecord[]>([])

const query = reactive({
  page: 1,
  page_size: 20,
  date_from: '',
  date_to: '',
  weather: '',
  forecast: '' as '' | 'true' | 'false',
})

async function load() {
  loading.value = true
  try {
    const res = await adminList({
      page: query.page,
      page_size: query.page_size,
      date_from: query.date_from || undefined,
      date_to: query.date_to || undefined,
      weather: query.weather || undefined,
      forecast: query.forecast || undefined,
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

function onReset() {
  query.date_from = ''
  query.date_to = ''
  query.weather = ''
  query.forecast = ''
  onSearch()
}

function handleSelectionChange(val: HistoryRecord[]) {
  selection.value = val
}

// 导出 CSV（导出当前全部筛选结果）
async function exportCsv() {
  let target: HistoryRecord[]
  if (selection.value.length) {
    target = selection.value
  } else {
    const res = await adminList({ ...query, page: 1, page_size: total.value })
    target = res.items
  }
  if (!target.length) {
    ElMessage.warning('没有可导出的数据')
    return
  }
  const headers = ['时间', '天气', '温度°C', '体感°C', '湿度%', '气压hPa', '风速km/h', '风向', '降水mm', '能见度km', '类型']
  const lines = target.map((r) =>
    [
      String(r.time).replace('T', ' ').slice(0, 19),
      r.weather_desc ?? '',
      r.temperature ?? '',
      r.feels_like ?? '',
      r.humidity ?? '',
      r.pressure ?? '',
      r.wind_speed ?? '',
      r.wind_direction ?? '',
      r.precipitation ?? '',
      r.visibility ?? '',
      r.is_forecast ? '预报' : '实测',
    ].join(','),
  )
  const csv = '\uFEFF' + [headers.join(','), ...lines].join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `广州气象数据_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(a.href)
  ElMessage.success(`已导出 ${target.length} 条`)
}

// 行详情
function showDetail(r: HistoryRecord) {
  ElMessageBox.alert(
    `
      时间：${String(r.time).replace('T', ' ').slice(0, 19)}<br/>
      天气：${r.weather_desc ?? '--'} / 类型：${r.is_forecast ? '预报' : '实测'}<br/>
      温度：${r.temperature ?? '--'}°C · 体感：${r.feels_like ?? '--'}°C<br/>
      湿度：${r.humidity ?? '--'}% · 气压：${r.pressure ?? '--'} hPa<br/>
      风速：${r.wind_speed ?? '--'} km/h · 风向：${r.wind_direction ?? '--'}<br/>
      降水：${r.precipitation ?? '--'} mm · 能见度：${r.visibility ?? '--'} km
    `,
    '气象详情',
    { dangerouslyUseHTMLString: true, confirmButtonText: '知道了' },
  )
}

onMounted(load)
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <div class="hd">
        <b>气象大数据管理</b>
        <div>
          <el-button type="primary" @click="onSearch">查询</el-button>
          <el-button @click="onReset">重置</el-button>
          <el-button @click="exportCsv" :disabled="!rows.length">导出 CSV</el-button>
        </div>
      </div>
    </template>

    <!-- 筛选栏 -->
    <el-form inline class="filter-bar">
      <el-form-item label="开始日期">
        <el-date-picker v-model="query.date_from" type="date" placeholder="开始" value-format="YYYY-MM-DD" style="width: 140px" />
      </el-form-item>
      <el-form-item label="结束日期">
        <el-date-picker v-model="query.date_to" type="date" placeholder="结束" value-format="YYYY-MM-DD" style="width: 140px" />
      </el-form-item>
      <el-form-item label="天气">
        <el-input v-model="query.weather" placeholder="如：雨 / 晴" clearable style="width: 130px" />
      </el-form-item>
      <el-form-item label="类型">
        <el-select v-model="query.forecast" style="width: 120px" clearable>
          <el-option label="全部" value="" />
          <el-option label="实测" value="false" />
          <el-option label="预报" value="true" />
        </el-select>
      </el-form-item>
    </el-form>

    <!-- 表格 -->
    <el-table
      v-loading="loading"
      :data="rows"
      border
      stripe
      @selection-change="handleSelectionChange"
    >
      <el-table-column type="selection" width="46" />
      <el-table-column label="时间" width="170">
        <template #default="{ row }">{{ String(row.time).replace('T', ' ').slice(0, 19) }}</template>
      </el-table-column>
      <el-table-column prop="weather_desc" label="天气" width="90">
        <template #default="{ row }">
          <el-tag :type="row.is_forecast ? 'info' : 'success'" size="small">
            {{ row.weather_desc || '--' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="温度°C" width="110">
        <template #default="{ row }">
          <template v-if="row.temp_max != null">
            {{ row.temp_max }} / {{ row.temp_min }}
          </template>
          <template v-else>{{ row.temperature ?? '--' }}</template>
        </template>
      </el-table-column>
      <el-table-column prop="humidity" label="湿度%" width="80" />
      <el-table-column prop="wind_speed" label="风速 km/h" width="100" />
      <el-table-column prop="wind_direction" label="风向" width="70" />
      <el-table-column prop="precipitation" label="降水 mm" width="90" />
      <el-table-column label="类型" width="80">
        <template #default="{ row }">
          <el-tag :type="row.is_forecast ? 'warning' : 'primary'" size="small">
            {{ row.is_forecast ? '预报' : '实测' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="80" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="showDetail(row)">详情</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <el-pagination
      class="pager"
      background
      layout="total, sizes, prev, pager, next"
      :total="total"
      :current-page="query.page"
      :page-size="query.page_size"
      :page-sizes="[10, 20, 50, 100]"
      @current-change="(p: number) => { query.page = p; load() }"
      @size-change="(s: number) => { query.page_size = s; query.page = 1; load() }"
    />
  </el-card>
</template>

<style scoped>
.hd {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.filter-bar {
  margin-bottom: 4px;
}
.filter-bar :deep(.el-form-item) {
  margin-right: 14px;
  margin-bottom: 12px;
}
.pager {
  margin-top: 16px;
  justify-content: flex-end;
}
</style>
