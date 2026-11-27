<template>
  <div v-if="config" class="section-grid grid-2">
    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title"><span class="dot"></span>平台权重与交叉乘数</div>
          <div class="card-sub">总得分 = (Σ 权重 × 排名分) × 交叉乘数 + 加分 - 扣分</div>
        </div>
        <span class="pill" :style="weightSumStyle">权重和 {{ weightSum.toFixed(2) }}</span>
      </div>
      <div class="card-body">
        <div v-for="(_, key) in config.scoring.platform_weights" :key="key" class="slider-row">
          <span class="label"><PlatformBadge :platform="key" /> {{ platformName(key) }}</span>
          <el-slider v-model="config.scoring.platform_weights[key]" :min="0" :max="1" :step="0.05" />
          <span class="val">{{ Number(config.scoring.platform_weights[key]).toFixed(2) }}</span>
        </div>

        <el-divider style="margin: 8px 0 18px" />

        <div class="grid-2" style="gap: 12px">
          <div v-for="n in 4" :key="n" class="bd-item">
            <div class="row" style="margin: 0 0 8px">
              <span>{{ n }} 个平台出现</span>
              <span class="dim">乘数</span>
            </div>
            <el-input-number v-model="config.scoring.cross_multiplier[String(n)]" :min="0" :max="5" :step="0.05" size="small" style="width: 100%" />
          </div>
        </div>

        <el-divider style="margin: 20px 0 18px" />

        <div class="slider-row">
          <span class="label">高分准入阈值</span>
          <el-slider v-model="config.scoring.min_download_score" :min="0" :max="200" :step="1" />
          <span class="val">{{ config.scoring.min_download_score }}</span>
        </div>
        <div class="slider-row">
          <span class="label">黑名单扣分</span>
          <el-slider v-model="config.scoring.blacklist_penalty" :min="-500" :max="0" :step="10" />
          <span class="val" style="color:#fb7185">{{ config.scoring.blacklist_penalty }}</span>
        </div>
        <div class="bd-tags" style="margin-top: 8px">
          <el-tag
            v-for="kw in config.scoring.blacklist_keywords"
            :key="kw"
            closable
            type="danger"
            effect="dark"
            @close="removeKeyword(kw)"
          >{{ kw }}</el-tag>
          <el-input
            v-model="newKeyword"
            size="small"
            placeholder="+ 关键词"
            style="width: 120px"
            @keyup.enter="addKeyword"
          />
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title"><span class="dot"></span>基础排名分与加减分规则</div>
          <div class="card-sub">名次越靠前基础分越高；条件规则命中后直接加减分</div>
        </div>
        <el-button size="small" @click="addRule">
          <el-icon><Plus /></el-icon>&nbsp;新增规则
        </el-button>
      </div>
      <div class="card-body">
        <div class="grid-2" style="gap: 10px; margin-bottom: 18px">
          <div class="bd-item">
            <div class="row" style="margin: 0"><span>名次区间</span><span class="dim">基础分 P</span></div>
            <div v-for="(tier, index) in config.scoring.base_score_tiers" :key="index" class="row">
              <span>Top {{ tier.max_rank }}</span>
              <el-input-number v-model="tier.score" :min="0" :max="200" size="small" controls-position="right" style="width: 92px" />
            </div>
          </div>
          <div class="bd-item">
            <div class="row" style="margin: 0"><span>跨平台规则</span><span class="dim">说明</span></div>
            <div class="row"><span>单平台</span><span class="dim">× {{ config.scoring.cross_multiplier['1'] }} 大幅降权</span></div>
            <div class="row"><span>双平台</span><span class="dim">× {{ config.scoring.cross_multiplier['2'] }} 正常</span></div>
            <div class="row"><span>三平台</span><span class="dim">× {{ config.scoring.cross_multiplier['3'] }} 加权</span></div>
            <div class="row"><span>四平台</span><span class="dim">× {{ config.scoring.cross_multiplier['4'] }} 全满贯</span></div>
          </div>
        </div>

        <div v-for="rule in config.scoring.bonus_rules" :key="rule.id" class="rule-row">
          <el-switch v-model="rule.enabled" size="small" />
          <el-select v-model="rule.field" size="small">
            <el-option label="歌名" value="title" />
            <el-option label="歌手" value="artist" />
            <el-option label="专辑" value="album" />
          </el-select>
          <el-input v-model="rule.value" size="small" placeholder="命中关键词" />
          <el-input-number v-model="rule.delta" size="small" :step="5" controls-position="right" />
          <el-button text type="danger" size="small" @click="removeRule(rule)">
            <el-icon><Delete /></el-icon>
          </el-button>
        </div>
        <div v-if="!config.scoring.bonus_rules.length" class="dim" style="font-size:12px;padding: 8px 0">
          暂无自定义规则，例如「歌名包含 翻唱 → -100」。
        </div>
      </div>
    </div>

    <div class="card" style="grid-column: 1 / -1">
      <div class="card-head">
        <div>
          <div class="card-title"><span class="dot"></span>保存与实时预览</div>
          <div class="card-sub">保存后立即对所有已聚合曲目按新规则重算</div>
        </div>
        <div class="toolbar">
          <el-button @click="loadConfig">重新加载</el-button>
          <el-button type="primary" :loading="saving" @click="saveAndPreview">保存并重算</el-button>
        </div>
      </div>
      <div class="card-body">
        <div v-if="summary" class="grid-4" style="gap: 12px; margin-bottom: 16px">
          <div class="bd-item">
            <div class="row" style="margin: 0"><span>参与打分</span><b>{{ summary.total }}</b></div>
          </div>
          <div class="bd-item">
            <div class="row" style="margin: 0"><span>高分达标</span><b style="color:#34d399">{{ summary.high_score }}</b></div>
          </div>
          <div class="bd-item">
            <div class="row" style="margin: 0"><span>库内跳过</span><b style="color:#fbbf24">{{ summary.skipped }}</b></div>
          </div>
          <div class="bd-item">
            <div class="row" style="margin: 0"><span>平均得分</span><b style="color:#22d3ee">{{ summary.avg_score }}</b></div>
          </div>
        </div>

        <el-table :data="previewTracks" class="mf-table" size="small" max-height="360">
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
          <el-table-column label="平台" width="150">
            <template #default="{ row }">
              <div style="display:flex;gap:4px;flex-wrap:wrap">
                <PlatformBadge v-for="s in [...new Set(row.sources.map((x) => x.platform))]" :key="s" :platform="s" />
              </div>
            </template>
          </el-table-column>
          <el-table-column label="得分" width="90">
            <template #default="{ row }"><b style="color:#a78bfa">{{ row.score }}</b></template>
          </el-table-column>
          <el-table-column label="状态" width="112">
            <template #default="{ row }"><StatusTag :status="row.status" /></template>
          </el-table-column>
        </el-table>
        <div v-if="!summary" class="dim" style="font-size:12px">保存后展示重算结果。</div>
      </div>
    </div>
  </div>
  <div v-else class="loading-block">规则配置加载中…</div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'
import PlatformBadge from '../components/PlatformBadge.vue'
import StatusTag from '../components/StatusTag.vue'
import TrackCover from '../components/TrackCover.vue'
import { PLATFORM_META } from '../utils/constants'

const config = ref(null)
const saving = ref(false)
const summary = ref(null)
const previewTracks = ref([])
const newKeyword = ref('')

const weightSum = computed(() => {
  if (!config.value) return 0
  return Object.values(config.value.scoring.platform_weights).reduce((sum, v) => sum + Number(v || 0), 0)
})

const weightSumStyle = computed(() => {
  const sum = weightSum.value
  if (Math.abs(sum - 1) < 0.001) return 'color:#34d399;background:rgba(52,211,153,.12)'
  return 'color:#fbbf24;background:rgba(251,191,36,.12)'
})

function platformName(key) {
  return PLATFORM_META[key]?.name || key
}

async function loadConfig() {
  const { data } = await api.get('/scoring/config')
  config.value = data
}

function addKeyword() {
  const value = newKeyword.value.trim()
  if (!value) return
  if (!config.value.scoring.blacklist_keywords.includes(value)) {
    config.value.scoring.blacklist_keywords.push(value)
  }
  newKeyword.value = ''
}

function removeKeyword(keyword) {
  config.value.scoring.blacklist_keywords = config.value.scoring.blacklist_keywords.filter((item) => item !== keyword)
}

function addRule() {
  config.value.scoring.bonus_rules.push({
    id: `rule_${Date.now()}`,
    name: '自定义规则',
    enabled: true,
    field: 'title',
    op: 'contains',
    value: '',
    delta: 10
  })
}

function removeRule(rule) {
  config.value.scoring.bonus_rules = config.value.scoring.bonus_rules.filter((item) => item !== rule)
}

async function saveAndPreview() {
  saving.value = true
  try {
    await api.put('/scoring/config', config.value)
    const { data } = await api.post('/scoring/preview', { playlist_id: null })
    summary.value = data.summary
    previewTracks.value = data.tracks.slice(0, 20)
    ElMessage.success('规则已保存并完成重算预览')
    await loadConfig()
  } catch (error) {
    ElMessage.error('保存失败：' + (error.response?.data?.detail || error.message))
  } finally {
    saving.value = false
  }
}

onMounted(loadConfig)
</script>
