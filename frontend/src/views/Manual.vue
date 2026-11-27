<template>
  <div>
    <div class="info-banner cyan">
      <el-icon><InfoFilled /></el-icon>
      手动直下跳过打分过滤与 Navidrome 去重限制，直接消耗当前滑动窗口配额，优先于自动任务执行。
    </div>

    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title"><span class="dot"></span>上游音源检索</div>
          <div class="card-sub">调用上游聚合搜索接口，选择目标音源后一键下载</div>
        </div>
        <div class="pill" :style="realtime.rateLimit.remaining > 0 ? 'color:#34d399;background:rgba(52,211,153,.12)' : 'color:#fb7185;background:rgba(251,113,133,.12)'">
          剩余配额 {{ realtime.rateLimit.remaining }} / {{ realtime.rateLimit.max }}
        </div>
      </div>
      <div class="card-body">
        <div class="toolbar">
          <el-input v-model="keyword" placeholder="输入歌名 / 歌手，如：周杰伦 晴天" style="max-width: 420px" clearable @keyup.enter="search">
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
          <el-select v-model="source" style="width: 150px">
            <el-option label="聚合搜索" value="" />
            <el-option v-for="s in SOURCES" :key="s" :label="s" :value="s" />
          </el-select>
          <el-button type="primary" :loading="searching" @click="search">搜索</el-button>
          <span class="spacer"></span>
          <span class="dim" style="font-size:11.5px" v-if="lastSearchAt">上次搜索：{{ lastSearchAt }}</span>
        </div>

        <el-table :data="results" class="mf-table" size="small" style="margin-top: 16px" v-loading="searching">
          <el-table-column label="曲目" min-width="240">
            <template #default="{ row }">
              <div class="track-cell">
                <TrackCover :src="coverOf(row)" :title="row.name" :size="38" />
                <div style="min-width:0">
                  <div class="t">{{ row.name }}</div>
                  <div class="a">{{ artistText(row.artist) }}</div>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="专辑" min-width="160">
            <template #default="{ row }"><span class="dim">{{ row.album || '—' }}</span></template>
          </el-table-column>
          <el-table-column label="音源" width="110">
            <template #default="{ row }">
              <span class="pill" style="color:#a78bfa;background:rgba(124,92,255,.12)">{{ row.source || row._searched_source }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" align="right">
            <template #default="{ row }">
              <el-button size="small" type="primary" plain @click="download(row)">
                <el-icon><Download /></el-icon>&nbsp;下载
              </el-button>
            </template>
          </el-table-column>
          <template #empty>
            <span class="dim" style="font-size:12px">{{ searched ? '未找到匹配结果' : '输入关键词开始搜索上游音源' }}</span>
          </template>
        </el-table>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title"><span class="dot"></span>手动下载记录</div>
          <div class="card-sub">最近通过手动直下通道提交的任务</div>
        </div>
        <el-button text @click="loadManualTasks"><el-icon><Refresh /></el-icon>&nbsp;刷新</el-button>
      </div>
      <div class="card-body tight">
        <el-table :data="manualTasks" class="mf-table" size="small">
          <el-table-column prop="id" label="#" width="60">
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
          <el-table-column label="状态" width="110">
            <template #default="{ row }"><StatusTag :status="row.status" /></template>
          </el-table-column>
          <el-table-column label="音质" width="100">
            <template #default="{ row }"><span class="dim">{{ row.quality || '—' }}</span></template>
          </el-table-column>
          <el-table-column label="时间" width="120">
            <template #default="{ row }"><span class="dim">{{ fmtTime(row.created_at) }}</span></template>
          </el-table-column>
          <el-table-column label="信息" min-width="180">
            <template #default="{ row }"><span class="dim" style="font-size:11px">{{ row.message || '—' }}</span></template>
          </el-table-column>
          <template #empty><span class="dim" style="font-size:12px">暂无手动下载任务</span></template>
        </el-table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import api from '../api'
import StatusTag from '../components/StatusTag.vue'
import TrackCover from '../components/TrackCover.vue'
import { realtime } from '../stores/realtime'
import { fmtTime } from '../utils/constants'
import { onRealtime } from '../utils/realtime'

const SOURCES = ['netease', 'tencent', 'kugou', 'kuwo', 'migu', 'joox', 'spotify', 'apple']
const keyword = ref('周杰伦 晴天')
const source = ref('')
const searching = ref(false)
const searched = ref(false)
const results = ref([])
const manualTasks = ref([])
const lastSearchAt = ref('')
let offs = []

function artistText(artist) {
  if (Array.isArray(artist)) return artist.join(' / ')
  return artist || '—'
}

function coverOf(row) {
  const platformSource = row.source || row._searched_source
  const coverId = row.pic_id || row.id
  if (platformSource && coverId) {
    return `/api/cover?source=${encodeURIComponent(platformSource)}&id=${encodeURIComponent(coverId)}`
  }
  return row.cover || ''
}

async function search() {
  if (!keyword.value.trim()) {
    ElMessage.warning('请输入搜索关键词')
    return
  }
  searching.value = true
  searched.value = false
  try {
    const { data } = await api.get('/manual/search', { params: { q: keyword.value.trim(), source: source.value, pages: 1 } })
    results.value = data.items
    searched.value = true
    lastSearchAt.value = dayjs().format('HH:mm:ss')
    if (!data.items.length) ElMessage.info('上游未返回匹配结果')
  } catch (error) {
    const detail = error.response?.data?.detail
    ElMessage.error(detail || '搜索失败')
    if (error.response?.status === 429) {
      results.value = []
    }
  } finally {
    searching.value = false
  }
}

async function download(row) {
  try {
    await api.post('/manual/download', { item: row })
    ElMessage.success(`已提交下载：${row.name}`)
    loadManualTasks()
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '提交下载失败')
  }
}

async function loadManualTasks() {
  try {
    const { data } = await api.get('/tasks', { params: { mode: 'manual', limit: 20 } })
    manualTasks.value = data.tasks
  } catch (e) {
    /* 忽略 */
  }
}

onMounted(() => {
  loadManualTasks()
  offs.push(onRealtime('task', (task) => {
    if (task.mode === 'manual') loadManualTasks()
  }))
})

onBeforeUnmount(() => offs.forEach((off) => off()))
</script>
