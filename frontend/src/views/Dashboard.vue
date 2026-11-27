<template>
  <div>
    <div v-if="data.system?.demo_mode" class="info-banner">
      <el-icon><Warning /></el-icon>
      当前为演示模式：采集任务将使用内置示例榜单数据。设置环境变量 DEMO_MODE=false 可启用真实平台抓取。
    </div>

    <div class="stat-grid">
      <StatCard label="聚合曲目" :value="fmtNumber(funnel.collected)" hint="本次聚合窗口内去重后的曲目数" accent="#7c5cff" icon="Headset" />
      <StatCard label="高分达标" :value="fmtNumber(funnel.high_score)" :hint="`准入阈值 ${data.threshold ?? 75} 分`" accent="#22d3ee" icon="TrendCharts" />
      <StatCard label="库内已跳过" :value="fmtNumber(funnel.skipped)" hint="Navidrome 已存在，不消耗上游配额" accent="#fbbf24" icon="CircleCheck" />
      <StatCard label="实际入库" :value="fmtNumber(funnel.downloaded)" :hint="`已下载 ${taskCounts.COMPLETED || 0} 个任务`" accent="#34d399" icon="Download" />
    </div>

    <div class="section-grid grid-dash" style="margin-top: 18px">
      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title"><span class="dot"></span>抓取与去重漏斗</div>
            <div class="card-sub">采集 → 高分准入 → 库内去重 → 实际入库</div>
          </div>
          <span class="pill" style="color:#a78bfa;background:rgba(124,92,255,.12)">实时</span>
        </div>
        <div class="card-body">
          <EChart :option="funnelOption" height="292px" />
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title"><span class="dot"></span>上游 API 滑动窗口配额</div>
            <div class="card-sub">任意 {{ rate.window_sec }} 秒内最多 {{ rate.max }} 次请求</div>
          </div>
          <span class="pill" :style="quotaPillStyle">{{ rate.waiting ? '等待恢复' : '正常' }}</span>
        </div>
        <div class="card-body">
          <EChart :option="gaugeOption" height="176px" />
          <div class="grid-3" style="gap: 10px; margin-top: 6px">
            <div class="bd-item" style="padding: 10px 12px">
              <div class="row" style="margin: 0"><span>已用</span><b>{{ rate.used }}</b></div>
            </div>
            <div class="bd-item" style="padding: 10px 12px">
              <div class="row" style="margin: 0"><span>剩余</span><b style="color:#34d399">{{ rate.remaining }}</b></div>
            </div>
            <div class="bd-item" style="padding: 10px 12px">
              <div class="row" style="margin: 0"><span>恢复</span><b style="color:#fbbf24">{{ rate.reset_in }}s</b></div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="section-grid grid-2" style="margin-top: 18px">
      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title"><span class="dot"></span>跨平台交叉重合度</div>
            <div class="card-sub">出现平台数越多，交叉乘数越高（防刷量降权）</div>
          </div>
        </div>
        <div class="card-body">
          <EChart :option="crossOption" height="236px" />
        </div>
      </div>
      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title"><span class="dot"></span>入库音质分布</div>
            <div class="card-sub">已完成任务按音质统计</div>
          </div>
        </div>
        <div class="card-body">
          <EChart :option="qualityOption" height="236px" />
        </div>
      </div>
    </div>

    <div class="card" style="margin-top: 18px">
      <div class="card-head">
        <div>
          <div class="card-title"><span class="dot"></span>采集任务趋势</div>
          <div class="card-sub">最近运行批次的抓取、高分、去重与入库数量</div>
        </div>
        <el-button text @click="loadAll">
          <el-icon><Refresh /></el-icon>&nbsp;刷新
        </el-button>
      </div>
      <div class="card-body">
        <EChart v-if="trend.runs.length" :option="trendOption" height="260px" />
        <div v-else class="loading-block">暂无采集任务运行记录，点击「数据源」页的立即采集开始</div>
      </div>
    </div>

    <div class="section-grid grid-2" style="margin-top: 18px">
      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title"><span class="dot"></span>最新任务</div>
            <div class="card-sub">最近进入下载与后处理流水线的任务</div>
          </div>
          <RouterLink to="/queue" style="font-size:12px;color:#a78bfa;text-decoration:none">查看全部 →</RouterLink>
        </div>
        <div class="card-body tight">
          <el-table :data="data.recent_tasks || []" class="mf-table" size="small" :show-header="true">
            <el-table-column label="曲目" min-width="200">
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
            <el-table-column label="来源" width="100">
              <template #default="{ row }">
                <span class="pill" :style="modeStyle(row.mode)">{{ row.mode === 'manual' ? '手动直下' : '自动' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="110">
              <template #default="{ row }"><StatusTag :status="row.status" /></template>
            </el-table-column>
            <el-table-column label="时间" width="96">
              <template #default="{ row }"><span class="dim">{{ fmtTime(row.created_at) }}</span></template>
            </el-table-column>
          </el-table>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title"><span class="dot"></span>实时日志</div>
            <div class="card-sub">WebSocket 实时推流</div>
          </div>
          <span class="pill" :style="realtime.connected ? 'color:#34d399;background:rgba(52,211,153,.12)' : 'color:#fb7185;background:rgba(251,113,133,.12)'">
            {{ realtime.connected ? '已连接' : '未连接' }}
          </span>
        </div>
        <div class="card-body">
          <LogConsole :logs="logs" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'
import EChart from '../components/EChart.vue'
import LogConsole from '../components/LogConsole.vue'
import StatCard from '../components/StatCard.vue'
import StatusTag from '../components/StatusTag.vue'
import TrackCover from '../components/TrackCover.vue'
import { realtime } from '../stores/realtime'
import { CHART_COLORS, fmtNumber, fmtTime } from '../utils/constants'
import { onRealtime } from '../utils/realtime'

const data = ref({ funnel: {}, task_counts: {}, system: {} })
const trend = ref({ runs: [] })
const loading = ref(false)
let timer = null
let offs = []

const funnel = computed(() => data.value.funnel || {})
const taskCounts = computed(() => data.value.task_counts || {})
const rate = computed(() => realtime.rateLimit)
const logs = computed(() => (realtime.logs.length ? realtime.logs.slice(-120) : data.value.recent_logs || []))

const quotaPillStyle = computed(() =>
  rate.value.waiting
    ? 'color:#fbbf24;background:rgba(251,191,36,.12)'
    : 'color:#34d399;background:rgba(52,211,153,.1)'
)

function modeStyle(mode) {
  return mode === 'manual'
    ? 'color:#22d3ee;background:rgba(34,211,238,.12)'
    : 'color:#a78bfa;background:rgba(124,92,255,.12)'
}

const axisText = { color: '#64748b', fontSize: 11 }
const tooltipStyle = { backgroundColor: '#ffffff', borderColor: 'rgba(15,23,42,.08)', borderWidth: 1, textStyle: { color: '#0f172a' }, extraCssText: 'box-shadow:0 8px 24px rgba(15,23,42,.12);border-radius:10px;' }

const funnelOption = computed(() => {
  const f = funnel.value
  const eligible = Math.max((f.high_score || 0) - (f.skipped || 0), 0)
  const rows = [
    { name: '采集曲目', value: f.collected || 0 },
    { name: '高分达标', value: f.high_score || 0 },
    { name: '去重后候选', value: eligible },
    { name: '实际入库', value: f.downloaded || 0 }
  ]
  return {
    tooltip: { trigger: 'item', ...tooltipStyle },
    series: [
      {
        type: 'funnel',
        top: 10,
        bottom: 10,
        left: '6%',
        width: '88%',
        minSize: '22%',
        sort: 'none',
        gap: 6,
        label: {
          color: '#0f172a',
          fontSize: 12,
          formatter: (p) => `${p.name}  ${p.value}`
        },
        labelLine: { length: 14, lineStyle: { color: 'rgba(15,23,42,.2)' } },
        itemStyle: { borderWidth: 0, borderRadius: 6 },
        emphasis: { label: { fontSize: 13 } },
        data: rows.map((row, index) => ({
          ...row,
          itemStyle: { color: ['#7c5cff', '#6d7cff', '#22d3ee', '#34d399'][index] }
        }))
      }
    ]
  }
})

const gaugeOption = computed(() => {
  const used = rate.value.used || 0
  const max = rate.value.max || 50
  const percent = max ? Math.round((used / max) * 100) : 0
  return {
    series: [
      {
        type: 'gauge',
        startAngle: 210,
        endAngle: -30,
        min: 0,
        max,
        radius: '108%',
        center: ['50%', '62%'],
        progress: { show: true, width: 12, roundCap: true, itemStyle: { color: { type: 'linear', x: 0, y: 0, x2: 1, y2: 0, colorStops: [{ offset: 0, color: '#7c5cff' }, { offset: 1, color: '#22d3ee' }] } } },
        axisLine: { lineStyle: { width: 12, color: [[1, 'rgba(15,23,42,.08)']] } },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
        pointer: { show: false },
        anchor: { show: false },
        title: { show: false },
        detail: {
          valueAnimation: true,
          offsetCenter: [0, '4%'],
          fontSize: 30,
          fontWeight: 700,
          color: '#0f172a',
          formatter: `{value} / ${max}`
        },
        data: [{ value: used }]
      }
    ]
  }
})

const crossOption = computed(() => {
  const rows = data.value.cross_distribution || []
  const map = Object.fromEntries(rows.map((r) => [r.cross, r.count]))
  const labels = ['1 个平台', '2 个平台', '3 个平台', '4 个平台']
  const values = [1, 2, 3, 4].map((n) => map[n] || 0)
  return {
    grid: { left: 10, right: 16, top: 24, bottom: 8, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, ...tooltipStyle },
    xAxis: { type: 'category', data: labels, axisLabel: axisText, axisLine: { lineStyle: { color: 'rgba(15,23,42,.1)' } }, axisTick: { show: false } },
    yAxis: { type: 'value', axisLabel: axisText, splitLine: { lineStyle: { color: 'rgba(15,23,42,.06)' } } },
    series: [
      {
        type: 'bar',
        data: values,
        barWidth: 34,
        itemStyle: {
          borderRadius: [7, 7, 0, 0],
          color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: '#7c5cff' }, { offset: 1, color: 'rgba(34,211,238,.35)' }] }
        },
        label: { show: true, position: 'top', color: '#475569', fontSize: 11 }
      }
    ]
  }
})

const qualityOption = computed(() => {
  const rows = data.value.quality_distribution || []
  const source = rows.length ? rows : [{ quality: '暂无数据', count: 1 }]
  return {
    tooltip: { trigger: 'item', ...tooltipStyle },
    legend: { bottom: 0, textStyle: { color: '#64748b', fontSize: 11 }, icon: 'circle' },
    color: CHART_COLORS,
    series: [
      {
        type: 'pie',
        radius: ['48%', '70%'],
        center: ['50%', '45%'],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: '#ffffff', borderWidth: 3 },
        label: { show: false },
        data: source.map((r) => ({ name: r.quality, value: r.count }))
      }
    ]
  }
})

const trendOption = computed(() => {
  const runs = trend.value.runs || []
  return {
    grid: { left: 10, right: 18, top: 30, bottom: 10, containLabel: true },
    tooltip: { trigger: 'axis', ...tooltipStyle },
    legend: { top: 0, right: 0, textStyle: { color: '#64748b', fontSize: 11 }, icon: 'roundRect' },
    xAxis: {
      type: 'category',
      data: runs.map((r) => fmtTime(r.started_at).slice(6)),
      axisLabel: axisText,
      axisLine: { lineStyle: { color: 'rgba(15,23,42,.1)' } },
      axisTick: { show: false }
    },
    yAxis: { type: 'value', axisLabel: axisText, splitLine: { lineStyle: { color: 'rgba(15,23,42,.06)' } } },
    series: [
      { name: '抓取', type: 'line', smooth: true, symbolSize: 6, data: runs.map((r) => r.stats?.collected || 0), lineStyle: { color: '#7c5cff', width: 2.5 }, itemStyle: { color: '#7c5cff' }, areaStyle: { color: 'rgba(124,92,255,.12)' } },
      { name: '高分', type: 'line', smooth: true, symbolSize: 6, data: runs.map((r) => r.stats?.high_score || 0), lineStyle: { color: '#22d3ee', width: 2.5 }, itemStyle: { color: '#22d3ee' } },
      { name: '入库', type: 'line', smooth: true, symbolSize: 6, data: runs.map((r) => r.stats?.queued || 0), lineStyle: { color: '#34d399', width: 2.5 }, itemStyle: { color: '#34d399' } }
    ]
  }
})

async function loadAll() {
  loading.value = true
  try {
    const [overview, trendRes] = await Promise.all([api.get('/dashboard/overview'), api.get('/dashboard/trend')])
    data.value = overview.data
    trend.value = trendRes.data
  } catch (error) {
    ElMessage.error('看板数据加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadAll()
  timer = setInterval(loadAll, 30000)
  offs.push(
    onRealtime('pipeline', (payload) => {
      if (payload.phase === 'done' || payload.phase === 'idle') loadAll()
    }),
    onRealtime('task', () => loadAll())
  )
})

onBeforeUnmount(() => {
  clearInterval(timer)
  offs.forEach((off) => off())
})
</script>
