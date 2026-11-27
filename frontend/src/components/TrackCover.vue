<template>
  <div class="track-cover" :style="{ width: size + 'px', height: size + 'px', borderRadius: radius + 'px' }">
    <img v-if="src && !failed" :src="src" alt="" loading="lazy" @error="failed = true" />
    <div v-else class="fallback" :style="{ background: gradient, fontSize: Math.max(11, Math.round(size * 0.36)) + 'px' }">
      {{ initial }}
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  src: { type: String, default: '' },
  title: { type: String, default: '' },
  size: { type: Number, default: 38 },
  radius: { type: Number, default: 10 }
})

const failed = ref(false)
watch(
  () => props.src,
  () => {
    failed.value = false
  }
)

const initial = computed(() => {
  const text = (props.title || '♪').trim()
  return (text.slice(0, 1) || '♪').toUpperCase()
})

const gradient = computed(() => {
  const text = props.title || 'music'
  let hash = 0
  for (let i = 0; i < text.length; i += 1) hash = (hash * 31 + text.charCodeAt(i)) % 360
  const hue = Math.abs(hash)
  return `linear-gradient(135deg, hsl(${hue}, 72%, 58%), hsl(${(hue + 48) % 360}, 78%, 50%))`
})
</script>
