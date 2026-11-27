<template>
  <router-view />
</template>

<script setup>
import { onMounted } from 'vue'
import { realtime } from './stores/realtime'
import { connectRealtime } from './utils/realtime'

onMounted(() => {
  if (localStorage.getItem('mf_token')) connectRealtime()
})
</script>
