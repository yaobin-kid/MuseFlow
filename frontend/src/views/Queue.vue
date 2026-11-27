<template>
  <div>
    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title"><span class="dot"></span>任务队列</div>
          <div class="card-sub">单工作线程串行消费，自动遵守滑动窗口限流；手动任务优先</div>
        </div>
        <div class="toolbar">
          <span class="pill" style="color:#a78bfa;background:rgba(124,92,255,.12)">排队 {{ counts.QUEUED || 0 }}</span>
          <span class="pill" style="color:#22d3ee;background:rgba(34,211,238,.12)">进行中 {{ (counts.DOWNLOADING || 0) + (counts.PROCESSING || 0) }}</span>
          <span class="pill" style="color:#34d399;background:rgba(52,211,153,.12)">已入库 {{ counts.COMPLETED || 0 }}</span>
          <span class="pill" style="color:#fb7185;background:rgba(251,113,133,.12)">失败 {{ counts.FAILED || 0 }}</span>
          <el-button text @click="load"><el-icon><Refresh /></el-icon>&nbsp;刷新</el-button>
        </div>
      </div>
      <div class="card-body">
        <div class="toolbar" style="margin-bottom: 14px">
          <div class="platform-tabs" style="max-width: 620px">
            <div
              v-for="item in STATUS_FILTERS"
              :key="item.value"
              class="platform-tab"
              :class="{ active: filter === item.value }"
              @click="switchFilter(item.value)"
            >{{ item.label }}</div>
          </div>
          <span class="spacer"></span>
          <div class="quota-pill">
            <span class="live-dot" :class="{ off: !realtime.connected }"></span>
            <span class="dim">配额</span>
            <b style="color:#0f172a">{{ realtime.rateLimit.used }}/{{ realtime.rateLimit.max }}</b>
            <span class="dim" v-if="realtime.rateLimit.waiting">等待 {{ realtime.rateLimit.wait_seconds || realtime.rateLimit.reset_in }}s</span>
          </div>
        </div>

        <el-table :data="tasks" class="mf-table" size="small" v-loading="loading">
          <el-table-column label="#" width="58">
            <template #default="{ row }"><span class="dim mono">#{{ row.id }}</span></template>
          </el-table-column>
          <el-table-column label="曲目" min-width="220">
            <template #default="{ row }">
              <div class="track-cell">
                <TrackCover :src="row.cover" :title="row.title" :size="36" />
                <div style="min-width:0">
                  <div class="t">{{ row.title }}</div>
                  <div class="a">{{ row.artist }}</div>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="通道" width="96">
            <template #default="{ row }">
              <span class="pill" :style="row.mode === 'manual' ? 'color:#22d3ee;background:rgba(34,211,238,.12)' : 'color:#a78bfa;background:rgba(124,92,255,.12)'">
                {{ row.mode === 'manual' ? '手动直下' : '自动' }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="112">
            <template #default="{ row }"><StatusTag :status="row.status" /></template>
          </el-table-column>
          <el-table-column label="进度" width="140">
            <template #default="{ row }">
              <el-progress
                :percentage="row.progress || (row.status === 'COMPLETED' ? 100 : 0)"
                :stroke-width="6"
                :show-text="false"
                :color="progressColor(row.status)"
              />
            </template>
          </el-table-column>
          <el-table-column label="音质" width="88">
            <template #default="{ row }"><span class="dim">{{ row.quality || '—' }}</span></template>
          </el-table-column>
          <el-table-column label="信息" min-width="200">
            <template #default="{ row }">
              <span :style="{ fontSize: '11px', color: row.status === 'FAILED' ? '#dc2626' : '#64748b' }">{{ row.message || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="更新时间" width="120">
            <template #default="{ row }"><span class="dim">{{ fmtTime(row.updated_at) }}</span></template>
          </el-table-column>
          <el-table-column label="操作" width="180" align="right">
            <template #default="{ row }">
              <el-button
                v-if="['FAILED', 'CANCELLED', 'COMPLETED'].includes(row.status)"
                size="small"
                text
                @click="retry(row)"
              >重试</el-button>
              <el-button
                v-if="['QUEUED', 'WAITING'].includes(row.status)"
                size="small"
                text
                type="danger"
                @click="cancel(row)"
              >取消</el-button>
              <el-button
                v-if="!['DOWNLOADING', 'PROCESSING'].includes(row.status)"
                size="small"
                text
                type="danger"
                @click="remove(row)"
              >删除</el-button>
            </template>
          </el-table-column>
          <template #empty><span class="dim" style="font-size:12px">暂无任务</span></template>
        </el-table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'
import StatusTag from '../components/StatusTag.vue'
import TrackCover from '../components/TrackCover.vue'
import { realtime } from '../stores/realtime'
import { STATUS_FILTERS, fmtTime } from '../utils/constants'
import { onRealtime } from '../utils/realtime'

const tasks = ref([])
const counts = ref({})
const filter = ref('')
const loading = ref(false)
let timer = null
let reloadTimer = null
let offs = []

function progressColor(status) {
  if (status === 'COMPLETED') return '#34d399'
  if (status === 'FAILED') return '#fb7185'
  if (status === 'PROCESSING') return '#22d3ee'
  return '#7c5cff'
}

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/tasks', { params: { status: filter.value, limit: 200 } })
    tasks.value = data.tasks
    counts.value = data.counts
  } catch (e) {
    ElMessage.error('任务加载失败')
  } finally {
    loading.value = false
  }
}

function switchFilter(value) {
  filter.value = value
  load()
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`确定删除任务 #${row.id} 的记录？`, '删除记录', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await api.delete(`/tasks/${row.id}`)
    ElMessage.success(`任务 #${row.id} 记录已删除`)
    load()
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '删除失败')
  }
}

async function retry(row) {
  try {
    await api.post(`/tasks/${row.id}/retry`)
    ElMessage.success(`任务 #${row.id} 已重新入队`)
    load()
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '重试失败')
  }
}

async function cancel(row) {
  try {
    await api.post(`/tasks/${row.id}/cancel`)
    ElMessage.success(`任务 #${row.id} 已取消`)
    load()
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '取消失败')
  }
}

onMounted(() => {
  load()
  timer = setInterval(load, 10000)
  offs.push(
    onRealtime('task', () => {
      clearTimeout(reloadTimer)
      reloadTimer = setTimeout(load, 600)
    }),
    onRealtime('rate_limit', () => {})
  )
})

onBeforeUnmount(() => {
  clearInterval(timer)
  clearTimeout(reloadTimer)
  offs.forEach((off) => off())
})
</script>
