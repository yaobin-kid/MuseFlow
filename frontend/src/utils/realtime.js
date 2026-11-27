import { appendLog, realtime } from '../stores/realtime'

let socket = null
let retryTimer = null
let closedByUser = false
const listeners = new Map()

export function onRealtime(type, handler) {
  if (!listeners.has(type)) listeners.set(type, new Set())
  listeners.get(type).add(handler)
  return () => listeners.get(type)?.delete(handler)
}

function emit(type, data) {
  listeners.get(type)?.forEach((fn) => {
    try {
      fn(data)
    } catch (e) {
      console.error(e)
    }
  })
}

function handle(message) {
  const { type, data } = message
  if (type === 'init') {
    if (data.rate_limit) realtime.rateLimit = data.rate_limit
    if (data.cooldown) realtime.cooldown = data.cooldown
    if (data.navidrome) realtime.navidrome = data.navidrome
    realtime.pipeline = { phase: data.pipeline_running ? 'running' : 'idle' }
    if (Array.isArray(data.logs)) {
      realtime.logs = data.logs.slice(-300)
    }
    emit('init', data)
    return
  }
  if (type === 'log') {
    appendLog(data)
    emit('log', data)
    return
  }
  if (type === 'rate_limit') {
    realtime.rateLimit = { ...realtime.rateLimit, ...data }
    emit('rate_limit', realtime.rateLimit)
    return
  }
  if (type === 'cooldown') {
    realtime.cooldown = { ...realtime.cooldown, [data.platform]: data }
    emit('cooldown', data)
    return
  }
  if (type === 'pipeline') {
    realtime.pipeline = data
    emit('pipeline', data)
    return
  }
  emit(type, data)
}

export function connectRealtime() {
  const token = localStorage.getItem('mf_token')
  if (!token) return
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) return
  closedByUser = false
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  socket = new WebSocket(`${proto}://${location.host}/ws?token=${encodeURIComponent(token)}`)
  socket.onopen = () => {
    realtime.connected = true
    emit('connection', true)
  }
  socket.onmessage = (event) => {
    try {
      handle(JSON.parse(event.data))
    } catch (e) {
      console.error('ws message parse failed', e)
    }
  }
  socket.onclose = () => {
    realtime.connected = false
    emit('connection', false)
    if (!closedByUser) {
      clearTimeout(retryTimer)
      retryTimer = setTimeout(connectRealtime, 4000)
    }
  }
  socket.onerror = () => {
    socket?.close()
  }
}

export function disconnectRealtime() {
  closedByUser = true
  clearTimeout(retryTimer)
  if (socket) {
    socket.close()
    socket = null
  }
  realtime.connected = false
}
