<template>
  <div class="login-wrap">
    <section class="login-visual">
      <div class="login-grid"></div>
      <div class="login-brand">
        <div class="brand-mark" style="width:44px;height:44px">
          <svg viewBox="0 0 24 24" fill="none" style="width:24px;height:24px">
            <path d="M9 18V6l10-2v12" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
            <circle cx="6.5" cy="18" r="2.5" fill="white" />
            <circle cx="16.5" cy="16" r="2.5" fill="white" />
          </svg>
        </div>
        <div>
          <div class="brand-name" style="font-size:19px">MuseFlow</div>
          <div class="brand-sub">Music Automation Platform</div>
        </div>
      </div>

      <div class="login-hero">
        <h1>让每一次<br /><span>热门旋律</span>自动入库</h1>
        <p>
          多平台榜单防风控采集 · 跨平台交叉打分防垃圾 · Navidrome 曲库存在性去重 ·
          限流保护的上游音源检索 · 标准化刮削归档，全链路自动闭环。
        </p>
      </div>

      <div class="login-features">
        <span class="login-feature"><i class="spark"></i>四大平台榜单聚合</span>
        <span class="login-feature"><i class="spark"></i>5 分钟 50 次滑动限流</span>
        <span class="login-feature"><i class="spark"></i>透明化得分拆解</span>
        <span class="login-feature"><i class="spark"></i>Navidrome 自动扫库</span>
      </div>
    </section>

    <section class="login-panel">
      <div class="login-card">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:22px">
          <div>
            <h2>欢迎回来</h2>
            <div class="hint">登录以查看采集、打分与下载数据</div>
          </div>
          <span class="pill" style="color:#67e8f9;background:rgba(34,211,238,.1)">SECURE</span>
        </div>

        <el-form @submit.prevent="submit">
          <el-form-item>
            <el-input v-model="form.username" size="large" placeholder="账号" autocomplete="username">
              <template #prefix><el-icon><User /></el-icon></template>
            </el-input>
          </el-form-item>
          <el-form-item>
            <el-input
              v-model="form.password"
              size="large"
              type="password"
              show-password
              placeholder="密码"
              autocomplete="current-password"
              @keyup.enter="submit"
            >
              <template #prefix><el-icon><Lock /></el-icon></template>
            </el-input>
          </el-form-item>
          <el-button type="primary" class="login-submit" :loading="loading" @click="submit">
            进入控制台
          </el-button>
        </el-form>

        <div class="login-foot">
          默认账号 admin / admin123 · 可通过环境变量 ADMIN_USERNAME、ADMIN_PASSWORD 修改
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../api'
import { connectRealtime } from '../utils/realtime'

const router = useRouter()
const loading = ref(false)
const form = reactive({ username: 'admin', password: '' })

async function submit() {
  if (!form.username || !form.password) {
    ElMessage.warning('请输入账号和密码')
    return
  }
  loading.value = true
  try {
    const { data } = await api.post('/auth/login', { ...form })
    localStorage.setItem('mf_token', data.access_token)
    localStorage.setItem('mf_user', data.username)
    connectRealtime()
    ElMessage.success('登录成功')
    router.replace('/dashboard')
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '登录失败，请检查账号密码')
  } finally {
    loading.value = false
  }
}
</script>
