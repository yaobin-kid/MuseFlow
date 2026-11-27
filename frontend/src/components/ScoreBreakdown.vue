<template>
  <div class="breakdown">
    <div class="bd-formula">
      <span>最终得分</span>
      <b>{{ track.final_score }}</b>
      <span class="dim">=</span>
      <span>({{ track.weighted_total }} × {{ track.cross_multiplier }})</span>
      <span class="dim">+</span>
      <span :style="{ color: (track.bonus_total || 0) < 0 ? '#dc2626' : (track.bonus_total || 0) > 0 ? '#047857' : '#64748b' }">
        {{ track.bonus_total > 0 ? '+' : '' }}{{ track.bonus_total || 0 }}
      </span>
      <span class="dim">|</span>
      <span>准入阈值 {{ track.threshold }}</span>
      <span
        class="pill"
        :style="{
          color: (track.final_score || 0) >= (track.threshold || 0) ? '#34d399' : '#94a3b8',
          background: (track.final_score || 0) >= (track.threshold || 0) ? 'rgba(52,211,153,.14)' : 'rgba(148,163,184,.14)'
        }"
      >
        {{ (track.final_score || 0) >= (track.threshold || 0) ? '达到准入' : '未达准入' }}
      </span>
      <span
        v-if="track.exists_in_library"
        class="pill"
        style="color:#fbbf24;background:rgba(251,191,36,.14)"
      >Navidrome 已存在</span>
    </div>

    <div class="bd-grid">
      <div v-for="p in track.platforms || []" :key="p.platform" class="bd-item">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:8px">
          <PlatformBadge :platform="p.platform" />
          <span class="dim" style="font-size:11px">第 {{ p.rank }} 名</span>
        </div>
        <div class="row"><span>基础排名分 P</span><b>{{ p.base_score }}</b></div>
        <div class="row"><span>平台权重 W</span><b>{{ p.weight }}</b></div>
        <div class="row"><span>贡献 W × P</span><b style="color:#a78bfa">{{ p.contribution }}</b></div>
        <div class="row" v-if="p.playlist_name"><span>来源歌单</span><span class="dim">{{ p.playlist_name }}</span></div>
      </div>
      <div v-if="!(track.platforms || []).length" class="bd-item">
        <div class="dim">暂无平台来源</div>
      </div>
    </div>

    <div class="bd-tags">
      <span class="pill" style="color:#a78bfa;background:rgba(124,92,255,.14)">
        跨平台 {{ track.cross_count }} 个 · 乘数 ×{{ track.cross_multiplier }}
      </span>
      <span
        v-for="b in track.bonuses || []"
        :key="b.id"
        class="pill"
        :style="{
          color: b.delta < 0 ? '#fb7185' : '#34d399',
          background: b.delta < 0 ? 'rgba(251,113,133,.13)' : 'rgba(52,211,153,.13)'
        }"
      >
        {{ b.name }} {{ b.delta > 0 ? '+' : '' }}{{ b.delta }}
      </span>
      <span v-if="!(track.bonuses || []).length" class="pill" style="color:#64748b;background:rgba(100,116,139,.1)">
        未命中加减分规则
      </span>
    </div>
  </div>
</template>

<script setup>
import PlatformBadge from './PlatformBadge.vue'
defineProps({ track: { type: Object, required: true } })
</script>
