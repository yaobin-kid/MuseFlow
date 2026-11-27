<template>
  <div class="log-console" ref="box">
    <div v-if="!logs.length" class="dim" style="padding: 8px">暂无日志</div>
    <div v-for="(item, index) in logs" :key="index" class="log-line" :class="(item.level || 'info').toLowerCase()">
      <span class="log-ts">{{ shortTime(item.ts) }}</span>
      <span class="log-scope">[{{ item.scope }}]</span>
      <span class="log-msg">{{ item.message }}</span>
    </div>
  </div>
</template>

<script setup>
import { nextTick, ref, watch } from 'vue'
import dayjs from 'dayjs'

const props = defineProps({
  logs: { type: Array, default: () => [] }
})
const box = ref(null)

function shortTime(ts) {
  return ts ? dayjs(ts).format('HH:mm:ss') : '--:--:--'
}

watch(
  () => props.logs.length,
  async () => {
    await nextTick()
    if (box.value) box.value.scrollTop = box.value.scrollHeight
  }
)
</script>
