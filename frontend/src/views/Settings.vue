<template>
  <div v-if="config">
    <div class="toolbar" style="margin-bottom: 16px">
      <el-button type="primary" :loading="saving" @click="save">
        <el-icon><Check /></el-icon>&nbsp;保存全部配置
      </el-button>
      <el-button :loading="loading" @click="loadAll">重新加载</el-button>
      <el-button @click="reset">恢复环境变量默认值</el-button>
      <span class="spacer"></span>
      <span class="dim" style="font-size:11.5px">控制台修改将持久化至 SQLite，优先级高于环境变量默认值</span>
    </div>

    <div class="section-grid grid-2">
      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title"><span class="dot"></span>网络与代理</div>
            <div class="card-sub">支持 HTTP / HTTPS / SOCKS5 代理与平台分流</div>
          </div>
        </div>
        <div class="card-body">
          <el-form label-position="top" size="default">
            <el-form-item label="代理地址">
              <el-input v-model="config.network.proxy_url" placeholder="socks5://127.0.0.1:7890（留空表示直连）" />
            </el-form-item>
            <el-form-item label="代理连通性测试">
              <div style="display: flex; gap: 8px; width: 100%">
                <el-input v-model="proxyTestUrl" placeholder="https://www.google.com/generate_204" />
                <el-button :loading="testingProxy" style="flex: 0 0 auto" @click="testProxy">测试代理</el-button>
              </div>
              <div class="dim" style="font-size:11.5px; margin-top: 6px">
                使用已保存的代理配置；默认访问 Google 204 接口，也可填写任意网址
              </div>
              <div
                v-if="proxyResult"
                style="font-size: 12px; margin-top: 6px; width: 100%"
                :style="proxyResult.ok ? 'color:#16a34a' : 'color:#dc2626'"
              >
                {{ proxyResult.text }}
              </div>
            </el-form-item>
            <el-form-item label="按平台启用代理">
              <div class="grid-2" style="gap: 8px; width: 100%">
                <div v-for="key in ['netease', 'qq', 'spotify', 'apple']" :key="key" class="bd-item" style="padding: 9px 12px">
                  <div class="row" style="margin: 0">
                    <span><PlatformBadge :platform="key" /> {{ platformName(key) }}</span>
                    <el-switch v-model="config.network.platform_use_proxy[key]" />
                  </div>
                </div>
              </div>
            </el-form-item>
            <el-divider />
            <el-form-item label="FlareSolverr 过盾">
              <div style="display: flex; align-items: center; gap: 12px; width: 100%">
                <el-switch v-model="config.network.flaresolverr_enabled" />
                <el-input v-model="config.network.flaresolverr_url" placeholder="http://flaresolverr:8191/v1" />
              </div>
            </el-form-item>
            <el-form-item label="FlareSolverr 超时（秒）">
              <el-input-number v-model="config.network.flaresolverr_timeout_sec" :min="5" :max="300" style="width: 100%" />
            </el-form-item>
            <el-form-item label="FlareSolverr 连通性测试">
              <div style="display: flex; gap: 8px; width: 100%">
                <el-input v-model="flareTestUrl" placeholder="https://www.google.com/generate_204" />
                <el-button :loading="testingFlare" style="flex: 0 0 auto" @click="testFlare">测试过盾</el-button>
              </div>
              <div class="dim" style="font-size:11.5px; margin-top: 6px">
                使用已保存的地址与开关；测试请求不携带代理，仅验证 FlareSolverr 服务本身是否正常
              </div>
              <div
                v-if="flareResult"
                style="font-size: 12px; margin-top: 6px; width: 100%"
                :style="flareResult.ok ? 'color:#16a34a' : 'color:#dc2626'"
              >
                {{ flareResult.text }}
              </div>
            </el-form-item>
            <el-alert type="info" :closable="false" show-icon style="margin-bottom: 14px">
              <template #title>代理与 FlareSolverr 的协作规则</template>
              <div style="font-size: 12px; line-height: 1.9">
                <div>• <b>只走代理</b>：代理已填写 + 该平台「按平台启用代理」开启，且平台接口正常返回；过盾不会介入。</div>
                <div>• <b>只走 FlareSolverr</b>：该平台代理开关关闭（或代理地址为空），但过盾开启且请求遇到 403 / 429 / 503 或异常。</div>
                <div>• <b>两者同时使用</b>：代理、该平台开关、过盾都开启时，先用代理直连；被拦截后由 FlareSolverr 携带同一代理和原始查询参数重试。</div>
                <div>• <b>代理作用范围</b>：仅网易云 / QQ / Spotify / Apple 的榜单采集；上游搜索下载、封面代理和 Navidrome 请求始终直连。过盾只接管平台 JSON 接口，普通请求不会经过它。</div>
              </div>
            </el-alert>
            <el-divider />
            <div class="grid-2" style="gap: 12px">
              <el-form-item label="同平台冷却基础时间（秒）">
                <el-input-number v-model="config.network.cooldown_base_sec" :min="0" :max="600" style="width: 100%" />
              </el-form-item>
              <el-form-item label="随机抖动上限（秒）">
                <el-input-number v-model="config.network.cooldown_jitter_sec" :min="0" :max="300" style="width: 100%" />
              </el-form-item>
            </div>
          </el-form>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title"><span class="dot"></span>限流与调度</div>
            <div class="card-sub">保护上游 API 的滑动窗口与自动任务周期</div>
          </div>
        </div>
        <div class="card-body">
          <el-form label-position="top">
            <div class="grid-2" style="gap: 12px">
              <el-form-item label="滑动窗口（秒）">
                <el-input-number v-model="config.rate_limit.window_sec" :min="10" :max="3600" style="width: 100%" />
              </el-form-item>
              <el-form-item label="窗口内最大请求数">
                <el-input-number v-model="config.rate_limit.max_requests" :min="1" :max="1000" style="width: 100%" />
              </el-form-item>
            </div>
            <el-divider />
            <el-form-item label="启用定时调度">
              <el-switch v-model="config.scheduler.enabled" />
            </el-form-item>
            <div class="grid-2" style="gap: 12px">
              <el-form-item label="自动采集间隔（分钟）">
                <el-input-number v-model="config.scheduler.collect_interval_minutes" :min="1" :max="10080" style="width: 100%" />
              </el-form-item>
              <el-form-item label="索引同步间隔（分钟）">
                <el-input-number v-model="config.scheduler.navidrome_sync_interval_minutes" :min="1" :max="10080" style="width: 100%" />
              </el-form-item>
            </div>
            <el-divider />
            <el-form-item label="上游音源搜索顺序">
              <el-select v-model="config.upstream.source_order" multiple filterable allow-create default-first-option style="width: 100%">
                <el-option v-for="s in UPSTREAM_SOURCES" :key="s.value" :label="s.label" :value="s.value" />
              </el-select>
              <div class="dim" style="font-size:11.5px; margin-top: 6px">
                上游仅支持 netease、netease2、bilibili、joox、kuwo，按从左到右的顺序依次尝试
              </div>
            </el-form-item>
          </el-form>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title"><span class="dot"></span>Navidrome 曲库去重</div>
            <div class="card-sub">通过 Subsonic API 同步本地索引，命中则跳过下载</div>
          </div>
          <span class="pill" :style="config.navidrome.enabled ? 'color:#34d399;background:rgba(52,211,153,.12)' : 'color:#94a3b8;background:rgba(148,163,184,.12)'">
            {{ config.navidrome.enabled ? '已启用' : '未启用' }}
          </span>
        </div>
        <div class="card-body">
          <el-form label-position="top">
            <el-form-item label="启用去重">
              <el-switch v-model="config.navidrome.enabled" />
            </el-form-item>
            <el-form-item label="Navidrome 地址">
              <el-input v-model="config.navidrome.url" placeholder="http://navidrome:4533" />
            </el-form-item>
            <div class="grid-2" style="gap: 12px">
              <el-form-item label="用户名">
                <el-input v-model="config.navidrome.username" />
              </el-form-item>
              <el-form-item label="密码">
                <el-input v-model="config.navidrome.password" type="password" show-password />
              </el-form-item>
            </div>
            <div class="grid-2" style="gap: 12px">
              <el-form-item label="匹配模式">
                <el-select v-model="config.navidrome.match_mode" style="width: 100%">
                  <el-option label="严格 strict（歌手+歌名）" value="strict" />
                  <el-option label="宽松 loose（歌名优先）" value="loose" />
                </el-select>
              </el-form-item>
              <el-form-item label="移动后自动扫库">
                <el-switch v-model="config.navidrome.auto_scan_after_move" />
              </el-form-item>
            </div>
            <el-form-item label="同步生成 Navidrome 歌单">
              <el-switch v-model="config.navidrome.sync_playlists" />
              <span class="dim" style="font-size:11.5px;margin-left:10px">
                采集与下载完成后，按平台创建/刷新一个歌单（合并该平台所有榜单并去重），仅保留最新曲目
              </span>
            </el-form-item>
            <div class="grid-2" style="gap: 12px">
              <el-form-item label="歌单名称前缀">
                <el-input v-model="config.navidrome.playlist_prefix" placeholder="MusicFlow" />
              </el-form-item>
              <el-form-item label="刷新延迟（秒）">
                <el-input-number v-model="config.navidrome.playlist_refresh_delay_sec" :min="5" :max="900" style="width: 100%" />
              </el-form-item>
            </div>
            <div class="toolbar">
              <el-button :loading="testing" @click="testNavidrome">测试连接</el-button>
              <el-button :loading="syncing" @click="syncNavidrome">立即同步索引</el-button>
              <el-button :loading="syncingPlaylists" @click="syncNavidromePlaylists">刷新歌单</el-button>
              <span class="dim" style="font-size:11.5px">
                索引 {{ system.navidrome?.index_size || 0 }} 首
                <span v-if="system.navidrome?.last_sync_at"> · {{ fmtTime(system.navidrome.last_sync_at) }}</span>
                <br />
                歌单 {{ system.navidrome?.playlists?.count || 0 }} 个 / {{ system.navidrome?.playlists?.tracks || 0 }} 首
                <span v-if="system.navidrome?.playlists?.last_sync_at"> · {{ fmtTime(system.navidrome.playlists.last_sync_at) }}</span>
              </span>
            </div>
          </el-form>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title"><span class="dot"></span>路径与上游服务</div>
            <div class="card-sub">整理暂存目录、最终音乐库目录与上游 API 地址</div>
          </div>
        </div>
        <div class="card-body">
          <el-form label-position="top">
            <el-form-item label="整理暂存目录">
              <el-input v-model="config.paths.temp_download_dir" placeholder="/data/downloads/temp" />
            </el-form-item>
            <el-form-item label="最终音乐目录">
              <el-input v-model="config.paths.final_music_dir" placeholder="/library" />
            </el-form-item>
            <el-alert type="info" :closable="false" show-icon style="margin-bottom: 14px">
              <template #title>三个目录的分工</template>
              <div style="font-size: 12px; line-height: 1.9">
                <div>• <b>上游下载目录 /music</b>：由上游服务固定写入，存放未整理的音频与歌词；MusicFlow 只读取，不写入。</div>
                <div>• <b>整理暂存目录</b>（上方设置）：写入前先把上游文件复制到这里，补全标签、嵌入封面；入库后自动清空。会短暂占用与音频等量的空间，不是上游的下载目录。</div>
                <div>• <b>最终音乐目录 /library</b>：整理完成后归档到 歌手/专辑 子目录，Navidrome 只扫描这里。</div>
                <div class="dim">因此「整理暂存目录」并非无用：它是标签与封面处理的工作区，避免修改上游目录里的原文件。</div>
              </div>
            </el-alert>
            <el-form-item label="上游 API 地址">
              <el-input v-model="config.upstream.base_url" placeholder="https://music.gdstudio.xyz" />
            </el-form-item>
            <div class="grid-2" style="gap: 12px">
              <el-form-item label="请求超时（秒）">
                <el-input-number v-model="config.upstream.timeout_sec" :min="5" :max="600" style="width: 100%" />
              </el-form-item>
              <el-form-item label="下载音质参数 br">
                <el-input v-model="config.upstream.preferred_bitrate" placeholder="999 表示最高音质" />
              </el-form-item>
            </div>
            <el-form-item label="上游音频文件路径模板">
              <el-input v-model="config.upstream.file_path_template" placeholder="/music/{filename}" />
            </el-form-item>
            <div class="grid-2" style="gap: 12px">
              <el-form-item label="歌曲封面 API 路径">
                <el-input v-model="config.upstream.cover_path" placeholder="/api/pic" />
              </el-form-item>
              <el-form-item label="仅歌词下载 API 路径">
                <el-input v-model="config.upstream.lyric_path" placeholder="/api/lyric" />
              </el-form-item>
            </div>
            <el-button :loading="testingUpstream" @click="testUpstream">测试上游连通性</el-button>
          </el-form>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title"><span class="dot"></span>Webhook 通知</div>
            <div class="card-sub">任务完成、手动下载与异常告警推送</div>
          </div>
          <el-switch v-model="config.webhook.enabled" />
        </div>
        <div class="card-body">
          <el-form label-position="top">
            <el-form-item label="通知类型">
              <el-select v-model="config.webhook.type" style="width: 100%">
                <el-option label="通用 JSON" value="generic" />
                <el-option label="Telegram" value="telegram" />
                <el-option label="Bark" value="bark" />
                <el-option label="企业微信" value="wecom" />
                <el-option label="钉钉" value="dingtalk" />
                <el-option label="Discord" value="discord" />
              </el-select>
            </el-form-item>
            <el-form-item label="Webhook 地址">
              <el-input v-model="config.webhook.url" placeholder="https://example.com/webhook" />
            </el-form-item>
            <el-form-item label="订阅事件">
              <el-checkbox-group v-model="config.webhook.events">
                <el-checkbox label="job_completed">采集完成</el-checkbox>
                <el-checkbox label="manual_download_completed">手动下载完成</el-checkbox>
                <el-checkbox label="download_completed">自动下载完成</el-checkbox>
                <el-checkbox label="error_alert">异常告警</el-checkbox>
              </el-checkbox-group>
            </el-form-item>
          </el-form>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div>
            <div class="card-title"><span class="dot"></span>系统信息</div>
            <div class="card-sub">运行环境与调度任务</div>
          </div>
          <span class="pill" :style="system.demo_mode ? 'color:#fbbf24;background:rgba(251,191,36,.12)' : 'color:#34d399;background:rgba(52,211,153,.12)'">
            {{ system.demo_mode ? '演示模式' : '生产模式' }}
          </span>
        </div>
        <div class="card-body">
          <div class="dash-list">
            <div class="dash-item"><span class="dim">应用版本</span><span>{{ system.app_name }} v{{ system.version }}</span></div>
            <div class="dash-item"><span class="dim">数据目录</span><span class="mono" style="font-size:11.5px">{{ system.data_dir }}</span></div>
            <div class="dash-item"><span class="dim">登录账号</span><span>{{ system.admin_username }}</span></div>
            <div class="dash-item"><span class="dim">时区</span><span>{{ system.timezone }}</span></div>
            <div class="dash-item">
              <span class="dim">调度任务</span>
              <span>
                <span v-for="job in system.scheduler?.jobs || []" :key="job.id" class="pill" style="color:#a78bfa;background:rgba(124,92,255,.12);margin-left:6px">
                  {{ job.id }} · {{ job.next_run ? fmtTime(job.next_run) : '未排期' }}
                </span>
                <span v-if="!system.scheduler?.jobs?.length" class="dim">未启用</span>
              </span>
            </div>
            <div class="dash-item"><span class="dim">WebSocket 客户端</span><span>{{ realtime.connected ? '已连接' : '未连接' }}</span></div>
          </div>
          <div class="info-banner" style="margin: 16px 0 0">
            <el-icon><Warning /></el-icon>
            演示模式由环境变量 DEMO_MODE 控制；设为 false 后使用真实平台采集器。
          </div>
        </div>
      </div>
    </div>
  </div>
  <div v-else class="loading-block">系统配置加载中…</div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api'
import PlatformBadge from '../components/PlatformBadge.vue'
import { realtime } from '../stores/realtime'
import { PLATFORM_META, UPSTREAM_SOURCES, fmtTime } from '../utils/constants'

const config = ref(null)
const system = ref({})
const saving = ref(false)
const loading = ref(false)
const testing = ref(false)
const syncing = ref(false)
const syncingPlaylists = ref(false)
const testingUpstream = ref(false)
const proxyTestUrl = ref('https://www.google.com/generate_204')
const testingProxy = ref(false)
const proxyResult = ref(null)
const flareTestUrl = ref('https://www.google.com/generate_204')
const testingFlare = ref(false)
const flareResult = ref(null)

function platformName(key) {
  return PLATFORM_META[key]?.name || key
}

async function loadAll() {
  loading.value = true
  try {
    const [cfg, sys] = await Promise.all([api.get('/settings/runtime'), api.get('/settings/system')])
    config.value = cfg.data
    system.value = sys.data
  } catch (error) {
    ElMessage.error('配置加载失败')
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    await api.put('/settings/runtime', config.value)
    ElMessage.success('配置已保存并立即生效')
    await loadAll()
  } catch (error) {
    ElMessage.error('保存失败：' + (error.response?.data?.detail || error.message))
  } finally {
    saving.value = false
  }
}

async function reset() {
  try {
    await ElMessageBox.confirm('将恢复为环境变量提供的默认配置，确定继续？', '恢复默认配置', { type: 'warning' })
  } catch (e) {
    return
  }
  try {
    const { data } = await api.post('/settings/reset')
    config.value = data.config
    ElMessage.success('已恢复默认配置')
    await loadAll()
  } catch (error) {
    ElMessage.error('恢复失败')
  }
}

async function testNavidrome() {
  testing.value = true
  try {
    const { data } = await api.post('/settings/test-navidrome')
    ElMessage.success(data.message)
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '连接失败')
  } finally {
    testing.value = false
  }
}

async function syncNavidrome() {
  syncing.value = true
  try {
    const { data } = await api.post('/settings/navidrome/sync')
    ElMessage.success(`索引同步完成，共 ${data.indexed} 首`)
    await loadAll()
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '同步失败')
  } finally {
    syncing.value = false
  }
}

async function syncNavidromePlaylists() {
  syncingPlaylists.value = true
  try {
    const { data } = await api.post('/settings/navidrome/playlists/sync')
    ElMessage.success(`歌单刷新完成：${data.playlists} 个歌单 / ${data.tracks} 首曲目`)
    await loadAll()
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '歌单刷新失败')
  } finally {
    syncingPlaylists.value = false
  }
}

async function testUpstream() {
  testingUpstream.value = true
  try {
    const { data } = await api.post('/settings/test-upstream')
    ElMessage.success(data.message)
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '上游连接失败')
  } finally {
    testingUpstream.value = false
  }
}

async function testFlare() {
  testingFlare.value = true
  flareResult.value = null
  try {
    const { data } = await api.post('/settings/test-flaresolverr', { url: flareTestUrl.value })
    flareResult.value = {
      ok: true,
      text: `FlareSolverr 正常：目标 HTTP ${data.status_code}，耗时 ${data.elapsed_ms} ms，返回 ${data.response_bytes} 字节${data.version ? `（${data.version}）` : ''}`,
    }
    ElMessage.success('FlareSolverr 正常')
  } catch (error) {
    const detail = error.response?.data?.detail || error.message || 'FlareSolverr 测试失败'
    flareResult.value = { ok: false, text: detail }
    ElMessage.error(detail)
  } finally {
    testingFlare.value = false
  }
}

async function testProxy() {
  testingProxy.value = true
  proxyResult.value = null
  try {
    const { data } = await api.post('/settings/test-proxy', { url: proxyTestUrl.value })
    proxyResult.value = {
      ok: true,
      text: `连接成功：HTTP ${data.status_code}，耗时 ${data.elapsed_ms} ms（代理 ${data.proxy}）`,
    }
    ElMessage.success('代理连接正常')
  } catch (error) {
    const detail = error.response?.data?.detail || error.message || '代理测试失败'
    proxyResult.value = { ok: false, text: detail }
    ElMessage.error(detail)
  } finally {
    testingProxy.value = false
  }
}

onMounted(loadAll)
</script>
