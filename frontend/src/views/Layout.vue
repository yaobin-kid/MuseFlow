<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">
          <svg viewBox="0 0 24 24" fill="none">
            <path d="M9 18V6l10-2v12" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
            <circle cx="6.5" cy="18" r="2.5" fill="white" />
            <circle cx="16.5" cy="16" r="2.5" fill="white" />
          </svg>
        </div>
        <div class="brand-text">
          <div class="brand-name">MusicFlow</div>
          <div class="brand-sub">Music Automation</div>
        </div>
      </div>

      <nav class="nav">
        <RouterLink v-for="item in navItems" :key="item.path" :to="item.path" class="nav-item" :class="{ active: route.path === item.path }">
          <span class="nav-icon"><el-icon><component :is="item.icon" /></el-icon></span>
          <span class="nav-text">{{ item.label }}</span>
        </RouterLink>
      </nav>

      <div class="sidebar-footer">
        <div class="label">Upstream Quota</div>
        <div class="value">
          <span class="live-dot" :class="{ off: !realtime.connected }"></span>
          {{ realtime.rateLimit.used }} / {{ realtime.rateLimit.max }} 次
        </div>
        <div class="quota-bar" style="width:100%;margin-top:9px">
          <span :style="{ width: Math.min(100, realtime.rateLimit.percent || 0) + '%' }"></span>
        </div>
      </div>
    </aside>

    <div class="main-wrap">
      <header class="topbar">
        <div>
          <h1 class="page-title">{{ route.meta.title || '控制台' }}</h1>
          <div class="page-sub">{{ route.meta.subtitle || '' }}</div>
        </div>
        <div class="top-actions">
          <span v-if="system.demo_mode" class="pill" style="color:#fbbf24;background:rgba(251,191,36,.12)">演示模式</span>
          <div class="quota-pill" :title="`滑动窗口 ${realtime.rateLimit.window_sec}s`">
            <span class="live-dot" :class="{ off: !realtime.connected }"></span>
            <span class="dim">配额</span>
            <div class="quota-bar"><span :style="{ width: Math.min(100, realtime.rateLimit.percent || 0) + '%' }"></span></div>
            <b style="color:#0f172a">{{ realtime.rateLimit.used }}/{{ realtime.rateLimit.max }}</b>
          </div>
          <el-dropdown trigger="click" @command="onCommand">
            <div class="user-chip">
              <div class="avatar">{{ username.slice(0, 1).toUpperCase() }}</div>
              <span>{{ username }}</span>
              <el-icon><ArrowDown /></el-icon>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item disabled>{{ system.app_name }} v{{ system.version }}</el-dropdown-item>
                <el-dropdown-item divided command="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>

      <main class="content">
        <div class="page">
          <RouterView />
        </div>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'
import { realtime } from '../stores/realtime'
import { disconnectRealtime } from '../utils/realtime'

const route = useRoute()
const router = useRouter()
const username = ref(localStorage.getItem('mf_user') || 'admin')
const system = ref({ app_name: 'MusicFlow', version: '1.0.0', demo_mode: false })

const navItems = [
  { path: '/dashboard', label: '数据看板', icon: 'DataLine' },
  { path: '/sources', label: '数据源与打分', icon: 'Files' },
  { path: '/rules', label: '动态规则配置', icon: 'Operation' },
  { path: '/manual', label: '手动搜索直下', icon: 'Search' },
  { path: '/queue', label: '下载队列', icon: 'Tickets' },
  { path: '/settings', label: '系统设置', icon: 'Setting' }
]

onMounted(async () => {
  try {
    const { data } = await api.get('/settings/system')
    system.value = { ...system.value, ...data }
  } catch (e) {
    /* 忽略 */
  }
})

function onCommand(command) {
  if (command === 'logout') {
    disconnectRealtime()
    localStorage.removeItem('mf_token')
    localStorage.removeItem('mf_user')
    router.replace('/login')
  }
}
</script>
