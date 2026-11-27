<template>
  <span class="status-tag" :style="{ color: meta.color, background: meta.bg }">
    <span class="status-dot"></span>{{ meta.label }}
  </span>
</template>

<script setup>
import { computed } from 'vue'
import { statusMeta } from '../utils/constants'

const props = defineProps({ status: String })
const meta = computed(() => statusMeta(props.status))
</script>
