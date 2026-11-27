import dayjs from 'dayjs'

// 上游搜索/下载 API 支持的 source（与后端 SUPPORTED_UPSTREAM_SOURCES 保持一致）
export const UPSTREAM_SOURCES = [
  { value: 'netease', label: 'netease（网易云 1）' },
  { value: 'netease2', label: 'netease2（网易云 2）' },
  { value: 'bilibili', label: 'bilibili（B 站）' },
  { value: 'joox', label: 'joox（JOOX）' },
  { value: 'kuwo', label: 'kuwo（酷我）' }
]

export const PLATFORM_META = {  netease: { name: '网易云音乐', short: '网易云', color: '#d81e3f', bg: 'rgba(216,30,63,.1)' },
  qq: { name: 'QQ 音乐', short: 'QQ音乐', color: '#0f9f63', bg: 'rgba(15,159,99,.1)' },
  spotify: { name: 'Spotify', short: 'Spotify', color: '#0d9b45', bg: 'rgba(13,155,69,.1)' },
  apple: { name: 'Apple Music', short: 'Apple', color: '#e11d48', bg: 'rgba(225,29,72,.1)' }
}

export const STATUS_META = {
  PENDING: { label: '待处理', color: '#64748b', bg: 'rgba(100,116,139,.12)' },
  FILTERED_LOW_SCORE: { label: '低分过滤', color: '#64748b', bg: 'rgba(100,116,139,.12)' },
  SKIPPED_EXISTS: { label: '库内已存在', color: '#b45309', bg: 'rgba(217,119,6,.12)' },
  QUEUED_DOWNLOAD: { label: '待下载', color: '#6d4df2', bg: 'rgba(109,77,242,.12)' },
  WAITING: { label: '限流等待', color: '#b45309', bg: 'rgba(217,119,6,.12)' },
  DOWNLOADING: { label: '下载中', color: '#0e7490', bg: 'rgba(8,145,178,.12)' },
  PROCESSING: { label: '整理中', color: '#0369a1', bg: 'rgba(3,105,161,.12)' },
  COMPLETED: { label: '已入库', color: '#047857', bg: 'rgba(5,150,105,.12)' },
  FAILED: { label: '失败', color: '#dc2626', bg: 'rgba(220,38,38,.1)' },
  CANCELLED: { label: '已取消', color: '#64748b', bg: 'rgba(100,116,139,.12)' }
}

export function statusMeta(status) {
  return STATUS_META[status] || { label: status || '未知', color: '#94a3b8', bg: 'rgba(148,163,184,.15)' }
}

export const STATUS_FILTERS = [
  { value: '', label: '全部' },
  { value: 'QUEUED_DOWNLOAD,WAITING', label: '排队中' },
  { value: 'DOWNLOADING,PROCESSING', label: '进行中' },
  { value: 'COMPLETED', label: '已入库' },
  { value: 'SKIPPED_EXISTS', label: '已跳过' },
  { value: 'FAILED', label: '失败' }
]

export function fmtTime(value) {
  if (!value) return '—'
  return dayjs(value).format('MM-DD HH:mm:ss')
}

export function fmtDate(value) {
  if (!value) return '—'
  return dayjs(value).format('YYYY-MM-DD HH:mm')
}

export function fmtNumber(value) {
  if (value === null || value === undefined) return '0'
  return Number(value).toLocaleString('zh-CN')
}

export function scoreColor(score, threshold = 75) {
  if (score >= threshold * 1.6) return '#22d3ee'
  if (score >= threshold) return '#34d399'
  if (score >= threshold * 0.6) return '#fbbf24'
  return '#64748b'
}

export const CHART_COLORS = ['#7c5cff', '#22d3ee', '#34d399', '#fbbf24', '#fb7185', '#f472b6']
