<template>
  <div>
    <div class="toolbar" style="margin-bottom: 16px">
      <el-button type="primary" :loading="collecting" @click="collectNow">
        <el-icon><VideoPlay /></el-icon>&nbsp;立即采集
      </el-button>
      <el-button :loading="loading" @click="reloadTracks(true)">
        <el-icon><Refresh /></el-icon>&nbsp;按当前规则重算
      </el-button>
      <span v-if="pipeline.phase && pipeline.phase !== 'idle'" class="pill" style="color:#22d3ee;background:rgba(34,211,238,.1)">
        <el-icon class="is-loading"><Loading /></el-icon>&nbsp;
        {{ pipeline.phase === 'collecting' ? `采集中 ${pipeline.platform} · ${pipeline.playlist}` : pipeline.phase === 'scoring' ? '聚合打分中' : '处理中' }}
      </span>
      <span class="spacer"></span>
      <el-input v-model="query" placeholder="搜索当前歌单曲目" clearable style="width: 220px">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
    </div>

    <div class="source-layout">
      <div class="card">
        <div class="card-head" style="padding: 14px 16px">
          <div class="card-title"><span class="dot"></span>平台与歌单</div>
          <span class="dim" style="font-size:11px">{{ scheduledCount }} / {{ totalPlaylists }} 已勾选</span>
        </div>
        <div class="card-body" style="padding: 14px 16px">
          <div class="platform-tabs" style="margin-bottom: 14px">
            <div
              v-for="p in platforms"
              :key="p.key"
              class="platform-tab"
              :class="{ active: p.key === activePlatform }"
              @click="activePlatform = p.key"
            >
              {{ p.name.replace('音乐', '').replace(' 港台', '') }}
            </div>
          </div>

          <div class="playlist-list">
            <div
              v-for="pl in currentPlaylists"
              :key="pl.id"
              class="playlist-item"
              :class="{ active: pl.id === selectedId }"
              @click="selectPlaylist(pl)"
            >
              <div class="name">
                <span>{{ pl.name }}</span>
                <el-switch
                  :model-value="pl.is_scheduled"
                  size="small"
                  @click.stop
                  @change="(val) => toggleSchedule(pl, val)"
                />
              </div>
              <div class="meta">
                <span>{{ pl.track_count || 0 }} 首</span>
                <span v-if="pl.last_fetched_at">上次 {{ fmtTime(pl.last_fetched_at) }}</span>
                <span v-else class="dim">未采集</span>
                <span v-if="isCooling(pl.platform)" style="color:#fbbf24">冷却 {{ cooldownOf(pl.platform) }}s</span>
              </div>
              <div v-if="isCooling(pl.platform)" class="mini-progress">
                <span :style="{ width: cooldownPercent(pl.platform) + '%' }"></span>
              </div>
              <div v-if="pl.last_error" class="error">抓取失败：{{ pl.last_error }}</div>
            </div>
            <div v-if="!currentPlaylists.length" class="dim" style="padding: 20px 0;text-align:center;font-size:12px">该平台暂无歌单</div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title">
              <span class="dot"></span>{{ selected?.name || '歌单曲目与实时评分' }}
              <span v-if="selected" class="pill" :style="platformPillStyle(selected.platform)">{{ platformName(selected.platform) }}</span>
            </div>
            <div class="card-sub">{{ selected?.description || '选择一个歌单查看完整曲目、得分拆解与准入状态' }}</div>
          </div>
          <div class="toolbar" v-if="tracks.length">
            <span class="pill" style="color:#a78bfa;background:rgba(124,92,255,.12)">共 {{ tracks.length }}</span>
            <span class="pill" style="color:#34d399;background:rgba(52,211,153,.12)">待下载 {{ stats.queued }}</span>
            <span class="pill" style="color:#fbbf24;background:rgba(251,191,36,.12)">已存在 {{ stats.skipped }}</span>
            <span class="pill" style="color:#94a3b8;background:rgba(148,163,184,.12)">低分 {{ stats.filtered }}</span>
          </div>
        </div>
        <div class="card-body tight">
          <el-table
            v-if="filteredTracks.length"
            :data="filteredTracks"
            class="mf-table"
            size="small"
            row-key="id"
            :expand-row-keys="expanded"
            :default-sort="{ prop: 'score', order: 'descending' }"
            :row-style="rowStyle"
            @expand-change="onExpandChange"
            @row-click="onRowClick"
          >
            <el-table-column type="expand">
              <template #default="{ row }">
                <ScoreBreakdown :track="row" />
              </template>
            </el-table-column>
            <el-table-column label="#" width="52">
              <template #default="{ row }"><span class="dim mono">{{ row.playlist_rank }}</span></template>
            </el-table-column>
            <el-table-column label="曲目" min-width="190">
              <template #default="{ row }">
                <div class="track-cell">
                  <TrackCover :src="row.cover" :title="row.title" :size="36" />
                  <div style="min-width:0">
                    <div class="t">{{ row.title }}</div>
                    <div class="a">{{ row.artist }}<span v-if="row.album"> · {{ row.album }}</span></div>
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="最终得分" width="104" prop="score" sortable>
              <template #default="{ row }">
                <span class="score-badge" :style="scoreStyle(row)">{{ row.final_score ?? row.score }}</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="108" prop="status" sortable :sort-method="sortByStatus">
              <template #default="{ row }">
                <StatusTag :status="row.status" />
              </template>
            </el-table-column>
            <el-table-column label="平台来源" width="146">
              <template #default="{ row }">
                <div style="display:flex;flex-wrap:wrap;gap:4px;align-items:center">
                  <PlatformBadge v-for="s in uniquePlatforms(row)" :key="s" :platform="s" />
                  <span class="dim" style="font-size:10.5px">×{{ row.cross_count }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="得分构成" width="116">
              <template #default="{ row }">
                <span class="dim mono" style="font-size:10.5px">{{ (row.weighted_total ?? 0) }} × {{ row.cross_multiplier ?? 1 }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="88" align="right">
              <template #default="{ row }">
                <el-button
                  v-if="canDownload(row)"
                  size="small"
                  text
                  type="primary"
                  @click.stop="downloadNow(row)"
                >下载</el-button>
                <span v-else class="dim" style="font-size:11px">—</span>
              </template>
            </el-table-column>
          </el-table>
          <div v-else class="loading-block">
            {{ loading ? '加载中…' : selected ? '暂无曲目，点击「立即采集」抓取榜单数据' : '请选择左侧歌单' }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'
import PlatformBadge from '../components/PlatformBadge.vue'
import ScoreBreakdown from '../components/ScoreBreakdown.vue'
import StatusTag from '../components/StatusTag.vue'
import TrackCover from '../components/TrackCover.vue'
import { realtime } from '../stores/realtime'
import { PLATFORM_META, fmtTime } from '../utils/constants'
import { onRealtime } from '../utils/realtime'

const platforms = ref([])
const activePlatform = ref('netease')
const selected = ref(null)
const tracks = ref([])
const loading = ref(false)
const collecting = ref(false)
const query = ref('')
const pipeline = ref({ phase: 'idle' })
let offs = []

const currentPlaylists = computed(() => platforms.value.find((p) => p.key === activePlatform.value)?.playlists || [])
const totalPlaylists = computed(() => platforms.value.reduce((sum, p) => sum + p.playlists.length, 0))
const scheduledCount = computed(() =>
  platforms.value.reduce((sum, p) => sum + p.playlists.filter((item) => item.is_scheduled).length, 0)
)

const stats = computed(() => {
  const result = { queued: 0, skipped: 0, filtered: 0 }
  tracks.value.forEach((t) => {
    if (t.status === 'QUEUED_DOWNLOAD') result.queued += 1
    else if (t.status === 'SKIPPED_EXISTS') result.skipped += 1
    else if (t.status === 'FILTERED_LOW_SCORE') result.filtered += 1
  })
  return result
})

const filteredTracks = computed(() => {
  if (!query.value) return tracks.value
  const q = query.value.toLowerCase()
  return tracks.value.filter((t) => `${t.title}${t.artist}`.toLowerCase().includes(q))
})

const expanded = ref([])

function onExpandChange(row, rows) {
  expanded.value = (rows || []).map((item) => item.id)
}

function rowStyle() {
  return { cursor: 'pointer' }
}

function onRowClick(row, column, event) {
  // 点击展开箭头时交给表格自身处理，避免重复切换
  if (event?.target?.closest?.('.el-table__expand-icon')) return
  const id = row.id
  expanded.value = expanded.value.includes(id)
    ? expanded.value.filter((key) => key !== id)
    : [...expanded.value, id]
}

const STATUS_SORT_ORDER = [
  'QUEUED_DOWNLOAD',
  'WAITING',
  'DOWNLOADING',
  'PROCESSING',
  'COMPLETED',
  'SKIPPED_EXISTS',
  'FILTERED_LOW_SCORE',
  'FAILED',
  'CANCELLED',
  'PENDING'
]

function sortByStatus(a, b) {
  const indexOf = (row) => {
    const index = STATUS_SORT_ORDER.indexOf(row.status)
    return index < 0 ? STATUS_SORT_ORDER.length : index
  }
  return indexOf(a) - indexOf(b)
}

function platformName(key) {
  return PLATFORM_META[key]?.name || key
}

function platformPillStyle(key) {
  const meta = PLATFORM_META[key] || { color: '#94a3b8', bg: 'rgba(148,163,184,.12)' }
  return `color:${meta.color};background:${meta.bg}`
}

function scoreStyle(row) {
  const score = row.final_score ?? row.score ?? 0
  const threshold = row.threshold || 75
  if (score >= threshold * 1.6) return 'color:#22d3ee;background:rgba(34,211,238,.12);border-color:rgba(34,211,238,.3)'
  if (score >= threshold) return 'color:#34d399;background:rgba(52,211,153,.12);border-color:rgba(52,211,153,.3)'
  if (score >= threshold * 0.6) return 'color:#fbbf24;background:rgba(251,191,36,.12);border-color:rgba(251,191,36,.3)'
  return 'color:#94a3b8;background:rgba(148,163,184,.12);border-color:rgba(148,163,184,.2)'
}

function uniquePlatforms(row) {
  return [...new Set((row.sources || []).map((s) => s.platform))]
}

const ACTIVE_STATUSES = ['QUEUED_DOWNLOAD', 'WAITING', 'DOWNLOADING', 'PROCESSING', 'COMPLETED', 'SKIPPED_EXISTS']

function canDownload(row) {
  if (row.downloaded_path) return false
  return !ACTIVE_STATUSES.includes(row.status)
}

async function downloadNow(row) {
  try {
    const { data } = await api.post(`/sources/tracks/${row.id}/download`)
    row.status = 'QUEUED_DOWNLOAD'
    ElMessage.success(`已加入下载队列：${row.title}（任务 #${data.task_id}）`)
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '加入下载队列失败')
  }
}

function isCooling(platform) {
  const state = realtime.cooldown?.[platform]
  return state && state.active && state.remaining > 0
}

function cooldownOf(platform) {
  return realtime.cooldown?.[platform]?.remaining || 0
}

function cooldownPercent(platform) {
  const state = realtime.cooldown?.[platform]
  if (!state || !state.total) return 0
  return Math.round((state.remaining / state.total) * 100)
}

async function loadPlaylists() {
  const { data } = await api.get('/sources/playlists')
  platforms.value = data.platforms
  realtime.cooldown = data.cooldown || {}
  collecting.value = data.running
  if (data.running) pipeline.value = { phase: 'collecting', platform: '任务', playlist: '运行中' }
  if (!selected.value) {
    const pool = platforms.value.flatMap((p) => p.playlists)
    if (pool.length) {
      activePlatform.value = pool[0].platform
      await selectPlaylist(pool[0])
    }
  }
}

async function selectPlaylist(playlist) {
  selected.value = playlist
  activePlatform.value = playlist.platform
  await reloadTracks()
}

async function reloadTracks(recalculate = true) {
  if (!selected.value) return
  loading.value = true
  try {
    const { data } = await api.get(`/sources/playlists/${selected.value.id}/tracks`, {
      params: { recalculate }
    })
    tracks.value = data.tracks
    if (data.tracks.length && !expanded.value.length) expanded.value = [data.tracks[0].id]
    const target = platforms.value.flatMap((p) => p.playlists).find((p) => p.id === selected.value.id)
    if (target) target.track_count = data.tracks.length
  } catch (error) {
    ElMessage.error('曲目加载失败')
  } finally {
    loading.value = false
  }
}

async function toggleSchedule(playlist, value) {
  playlist.is_scheduled = value
  try {
    await api.patch(`/sources/playlists/${playlist.id}`, { is_scheduled: value })
    ElMessage.success(value ? `已纳入调度：${playlist.name}` : `已取消调度：${playlist.name}`)
  } catch (error) {
    playlist.is_scheduled = !value
    ElMessage.error('更新调度状态失败')
  }
}

async function collectNow() {
  try {
    const { data } = await api.post('/sources/collect')
    if (data.status === 'busy') {
      ElMessage.warning(data.message)
      return
    }
    collecting.value = true
    ElMessage.success('采集任务已启动')
  } catch (error) {
    ElMessage.error('启动采集失败')
  }
}

onMounted(async () => {
  await loadPlaylists()
  offs.push(
    onRealtime('pipeline', (payload) => {
      pipeline.value = payload
      if (payload.phase === 'collecting' || payload.phase === 'scoring') collecting.value = true
      if (payload.phase === 'done' || payload.phase === 'idle') {
        collecting.value = false
        loadPlaylists()
        if (payload.phase === 'done') reloadTracks()
      }
    }),
    onRealtime('cooldown', () => {
      // 触发视图更新
      realtime.cooldown = { ...realtime.cooldown }
    })
  )
})

onBeforeUnmount(() => offs.forEach((off) => off()))
</script>
