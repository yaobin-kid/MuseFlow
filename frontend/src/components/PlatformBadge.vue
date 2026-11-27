<template>
  <span class="platform-badge" :style="{ color: meta.color, background: meta.bg }">{{ meta.short }}</span>
</template>

<script setup>
import { computed } from 'vue'
import { PLATFORM_META } from '../utils/constants'

const props = defineProps({ platform: String })
const meta = computed(
  () => PLATFORM_META[props.platform] || { short: props.platform || '—', color: '#94a3b8', bg: 'rgba(148,163,184,.15)' }
)
</script>
