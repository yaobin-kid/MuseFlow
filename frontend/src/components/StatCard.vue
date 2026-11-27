<template>
  <div class="stat-card" :style="{ '--accent': accent }">
    <div class="stat-top">
      <span class="stat-label">{{ label }}</span>
      <span class="stat-icon">
        <el-icon><component :is="icon" /></el-icon>
      </span>
    </div>
    <div class="stat-value">{{ value }}</div>
    <div class="stat-hint">{{ hint }}</div>
  </div>
</template>

<script setup>
defineProps({
  label: String,
  value: [String, Number],
  hint: { type: String, default: '' },
  accent: { type: String, default: '#7c5cff' },
  icon: { type: String, default: 'DataLine' }
})
</script>
