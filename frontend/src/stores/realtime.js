import { reactive } from 'vue'

export const realtime = reactive({
  connected: false,
  rateLimit: { used: 0, max: 50, remaining: 50, reset_in: 0, percent: 0, window_sec: 300, waiting: false },
  cooldown: {},
  logs: [],
  pipeline: { phase: 'idle' },
  navidrome: { enabled: false, index_size: 0 }
})

export function appendLog(entry) {
  realtime.logs.push(entry)
  if (realtime.logs.length > 400) realtime.logs.splice(0, realtime.logs.length - 400)
}
